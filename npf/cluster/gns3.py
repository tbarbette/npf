"""Use a GNS3 project as the testbed of an NPF test.

The GNS3 REST API gives the nodes of a project. Docker nodes are mapped to NPF roles from their names (client-1 and
client2 both become role "client"; --gns3-map overrides) and are then used as docker:// cluster nodes.

    npf --test my.npf local --gns3 my-project
    python -m npf.cluster.gns3 list my-project        # shows nodes, roles, and the equivalent --cluster
"""
import argparse
import atexit
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

DEFAULT_URL = "http://127.0.0.1:3080"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
ROLE_REGEX = re.compile(r"^([A-Za-z][A-Za-z0-9]*?)(?:[-_.]?\d+)?$")


class GNS3Error(Exception):
    pass


class GNS3Client:
    def __init__(self, url=None, user=None, password=None, api=2, timeout=60):
        url = url or os.environ.get("GNS3_URL") or DEFAULT_URL
        if "://" not in url:
            url = "http://" + url
        parts = urllib.parse.urlsplit(url)
        self.hostname = parts.hostname
        self.user = user or parts.username or os.environ.get("GNS3_USER")
        self.password = password or parts.password or os.environ.get("GNS3_PASSWORD")
        netloc = parts.hostname + (":%d" % parts.port if parts.port else ":3080")
        if ":" in parts.hostname:
            netloc = "[%s]:%d" % (parts.hostname, parts.port or 3080)
        self.base = "%s://%s/v%d" % (parts.scheme, netloc, int(api))
        self.api = int(api)
        self.timeout = timeout
        self._token = None

    def _headers(self):
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api >= 3:
            if self._token is None and self.user:
                data = urllib.parse.urlencode({"username": self.user, "password": self.password or ""}).encode()
                req = urllib.request.Request(self.base + "/access/users/login", data=data, method="POST")
                self._token = self._send(req)["access_token"]
            if self._token:
                h["Authorization"] = "Bearer " + self._token
        elif self.user:
            h["Authorization"] = "Basic " + base64.b64encode(("%s:%s" % (self.user, self.password or "")).encode()).decode()
        return h

    def _send(self, req):
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code == 401:
                raise GNS3Error("GNS3 server %s refused the credentials (401). Use --gns3-user and the GNS3_PASSWORD "
                                "environment variable." % self.base) from e
            raise GNS3Error("GNS3 API error %d on %s: %s" % (e.code, req.full_url, detail)) from e
        except (urllib.error.URLError, OSError) as e:
            raise GNS3Error("Cannot reach the GNS3 server at %s (%s). Is it running? Use --gns3-url." % (self.base, e)) from e
        return json.loads(body) if body else None

    def request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        return self._send(urllib.request.Request(self.base + path, data=data, method=method, headers=self._headers()))

    def projects(self) -> List[Dict]:
        return self.request("GET", "/projects")

    def project(self, name_or_id: str) -> Dict:
        projects = self.projects()
        found = [p for p in projects if name_or_id in (p["name"], p["project_id"])]
        if not found:
            raise GNS3Error("No GNS3 project named %s. Available: %s" % (name_or_id, ", ".join(p["name"] for p in projects) or "none"))
        if len(found) > 1:
            raise GNS3Error("Several GNS3 projects are named %s, use the project id." % name_or_id)
        return found[0]

    def open_project(self, pid):
        self.request("POST", "/projects/%s/open" % pid, {})

    def set_auto_close(self, pid, value: bool):
        self.request("PUT", "/projects/%s" % pid, {"auto_close": value})

    def nodes(self, pid) -> List[Dict]:
        return self.request("GET", "/projects/%s/nodes" % pid)

    def start_nodes(self, pid):
        self.request("POST", "/projects/%s/nodes/start" % pid, {})

    def stop_nodes(self, pid):
        self.request("POST", "/projects/%s/nodes/stop" % pid, {})


def role_of(name: str) -> Optional[str]:
    m = ROLE_REGEX.match(name)
    return m.group(1) if m else None


def map_roles(nodes: List[Dict], explicit: Optional[List[str]] = None) -> Tuple[List[Tuple[str, Dict]], List[Tuple[str, str]]]:
    """Maps GNS3 nodes to NPF roles.
    :param explicit: ["role=node name", ...] overrides of the name based mapping, one entry per node
    :return: ([(role, node)], [(node name, reason it is not usable)])
    """
    overrides = {}
    for e in explicit or []:
        role, sep, name = e.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z0-9]+", role) or not name:
            raise GNS3Error("Bad --gns3-map entry %r, expected role=node-name" % e)
        overrides[name] = role
    unknown = set(overrides) - {n["name"] for n in nodes}
    if unknown:
        raise GNS3Error("--gns3-map refers to nodes not in the project: %s" % ", ".join(sorted(unknown)))

    assigned, skipped = [], []
    for node in sorted(nodes, key=lambda n: n["name"]):
        name = node["name"]
        role = overrides.get(name) or role_of(name)
        if node.get("node_type") != "docker":
            skipped.append((name, "type %s is not supported, only docker nodes" % node.get("node_type")))
        elif not role:
            skipped.append((name, "name does not give a role, use --gns3-map role=%s" % name))
        elif not (node.get("properties") or {}).get("container_id"):
            skipped.append((name, "no container yet (is the node started?)"))
        else:
            assigned.append((role, node))
    return assigned, skipped


def docker_host_for(client: GNS3Client, override: Optional[str]) -> Optional[str]:
    """Where the docker daemon of the GNS3 server is: here if the server is, else through ssh to the server."""
    if override:
        return None if override == "local" else override
    return None if client.hostname in LOCAL_HOSTS else "ssh://" + client.hostname


def cluster_specs(assigned, docker_host) -> List[str]:
    return ["%s=docker://%s,nfs=0%s" % (role, n["properties"]["container_id"],
                                       ",dockerhost=" + docker_host if docker_host else "") for role, n in assigned]


def client_from_options(options) -> GNS3Client:
    return GNS3Client(getattr(options, "gns3_url", None), getattr(options, "gns3_user", None), None,
                      getattr(options, "gns3_api", 2))


def wait_started(client, pid, timeout=120):
    end = time.time() + timeout
    while True:
        nodes = client.nodes(pid)
        pending = [n["name"] for n in nodes if n["status"] != "started" and n["node_type"] != "cloud"]
        if not pending:
            return nodes
        if time.time() > end:
            raise GNS3Error("Nodes still not started after %ds: %s" % (timeout, ", ".join(pending)))
        time.sleep(1)


def discover(options) -> List[str]:
    """Returns the --cluster entries for the GNS3 project selected by --gns3."""
    client = client_from_options(options)
    project = client.project(options.gns3)
    pid = project["project_id"]
    if getattr(options, "gns3_start", False):
        if project.get("status") != "opened":
            client.open_project(pid)
        if project.get("auto_close"):
            # Else GNS3 closes the project, and stops its nodes, when the last web UI or GUI client disconnects
            client.set_auto_close(pid, False)
            atexit.register(_restore_auto_close, client, pid)
        if any(n["status"] != "started" and n["node_type"] != "cloud" for n in client.nodes(pid)):
            print("Starting the nodes of GNS3 project %s..." % project["name"])
            client.start_nodes(pid)
            if not getattr(options, "gns3_keep", False):
                atexit.register(_stop, client, pid, project["name"])
        nodes = wait_started(client, pid)
    else:
        nodes = client.nodes(pid)
        stopped = [n["name"] for n in nodes if n["status"] != "started" and n["node_type"] == "docker"]
        if stopped:
            raise GNS3Error("Nodes not started: %s. Start them in GNS3 or use --gns3-start." % ", ".join(stopped))

    assigned, skipped = map_roles(nodes, getattr(options, "gns3_map", None))
    for name, why in skipped:
        print("GNS3 node %s ignored: %s" % (name, why))
    if not assigned:
        raise GNS3Error("No usable docker node in GNS3 project %s." % project["name"])
    host = docker_host_for(client, getattr(options, "gns3_docker_host", None))
    specs = cluster_specs(assigned, host)
    print("GNS3 project %s%s: %s" % (project["name"], " (docker on %s)" % host if host else "",
                                    ", ".join("%s=%s" % (r, n["name"]) for r, n in assigned)))
    return specs


def _restore_auto_close(client, pid):
    try:
        client.set_auto_close(pid, True)
    except GNS3Error:
        pass


def _stop(client, pid, name):
    try:
        print("Stopping the nodes of GNS3 project %s..." % name)
        client.stop_nodes(pid)
    except GNS3Error as e:
        print("Could not stop the GNS3 nodes: %s" % e)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect a GNS3 project as an NPF testbed")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="show projects, or the nodes, roles and --cluster of one project")
    ls.add_argument("project", nargs="?")
    ls.add_argument("--url", dest="gns3_url", default=None)
    ls.add_argument("--user", dest="gns3_user", default=None)
    ls.add_argument("--api", dest="gns3_api", type=int, default=2)
    ls.add_argument("--map", dest="gns3_map", nargs="*", default=[])
    ls.add_argument("--docker-host", dest="gns3_docker_host", default=None)
    args = parser.parse_args(argv)
    client = client_from_options(args)
    try:
        if not args.project:
            for p in client.projects():
                print("%-30s %s (%s)" % (p["name"], p["project_id"], p.get("status")))
            return 0
        pid = client.project(args.project)["project_id"]
        nodes = client.nodes(pid)
        assigned, skipped = map_roles(nodes, args.gns3_map)
        for role, n in assigned:
            print("%-12s %-20s %s" % (role, n["name"], n["status"]))
        for name, why in skipped:
            print("%-12s %-20s ignored: %s" % ("-", name, why))
        host = docker_host_for(client, args.gns3_docker_host)
        print("\n--cluster " + " ".join(cluster_specs(assigned, host)))
    except GNS3Error as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
