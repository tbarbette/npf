import argparse
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from npf.cluster import gns3

PID = "11111111-2222-3333-4444-555555555555"


def node(name, ntype="docker", status="started", cid="c0ffee"):
    n = {"name": name, "node_type": ntype, "status": status, "properties": {}}
    if ntype == "docker":
        n["properties"]["container_id"] = cid + name
    return n


class FakeGNS3(BaseHTTPRequestHandler):
    state = {}

    def log_message(self, *a):
        pass

    def _reply(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        st = self.state
        st["auth"] = self.headers.get("Authorization")
        if self.path == "/v2/projects":
            return self._reply([{"name": "poc", "project_id": PID, "status": st["project_status"]}])
        if self.path == "/v2/projects/%s/nodes" % PID:
            return self._reply(st["nodes"])
        self.send_error(404)

    def do_POST(self):
        st = self.state
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        st["calls"].append(self.path)
        if self.path.endswith("/open"):
            st["project_status"] = "opened"
        elif self.path.endswith("/nodes/start"):
            for x in st["nodes"]:
                x["status"] = "started"
        elif self.path.endswith("/nodes/stop"):
            for x in st["nodes"]:
                x["status"] = "stopped"
        else:
            return self.send_error(404)
        self._reply({})


class TestRoles(unittest.TestCase):
    def test_role_of(self):
        for name, role in [("client-1", "client"), ("client2", "client"), ("dut", "dut"), ("web_03", "web"),
                           ("srv.1", "srv"), ("1abc", None)]:
            self.assertEqual(gns3.role_of(name), role, name)

    def test_map_roles(self):
        nodes = [node("client-1"), node("client-2"), node("dut"), node("sw", "ethernet_switch"),
                 node("nginx-a"), node("lonely", cid="")]
        nodes[-1]["properties"]["container_id"] = ""
        assigned, skipped = gns3.map_roles(nodes, ["server=nginx-a"])
        self.assertEqual([(r, n["name"]) for r, n in assigned],
                         [("client", "client-1"), ("client", "client-2"), ("dut", "dut"), ("server", "nginx-a")])
        self.assertEqual({n for n, _ in skipped}, {"sw", "lonely"})

    def test_bad_map(self):
        with self.assertRaises(gns3.GNS3Error):
            gns3.map_roles([node("a")], ["nonsense"])
        with self.assertRaises(gns3.GNS3Error):
            gns3.map_roles([node("a")], ["x=missing"])

    def test_specs_and_host(self):
        assigned, _ = gns3.map_roles([node("client-1")])
        self.assertEqual(gns3.cluster_specs(assigned, None), ["client=docker://c0ffeeclient-1,nfs=0"])
        self.assertEqual(gns3.cluster_specs(assigned, "ssh://h"),
                         ["client=docker://c0ffeeclient-1,nfs=0,dockerhost=ssh://h"])
        local = gns3.GNS3Client("http://127.0.0.1:3080")
        remote = gns3.GNS3Client("lab.example.com:3080")
        self.assertIsNone(gns3.docker_host_for(local, None))
        self.assertEqual(gns3.docker_host_for(remote, None), "ssh://lab.example.com")
        self.assertIsNone(gns3.docker_host_for(remote, "local"))
        self.assertEqual(gns3.docker_host_for(local, "ssh://u@x"), "ssh://u@x")


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), FakeGNS3)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        FakeGNS3.state = {"project_status": "closed", "calls": [],
                          "nodes": [node("client-1", status="stopped"), node("server", status="stopped"),
                                    node("cloud", "cloud", status="started")]}
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]

    def opts(self, **kw):
        d = dict(gns3="poc", gns3_url=self.url, gns3_user=None, gns3_api=2, gns3_start=False, gns3_keep=False,
                 gns3_map=[], gns3_docker_host=None)
        d.update(kw)
        return argparse.Namespace(**d)

    def test_stopped_nodes_refused(self):
        with self.assertRaisesRegex(gns3.GNS3Error, "not started"):
            gns3.discover(self.opts())

    def test_start(self):
        specs = gns3.discover(self.opts(gns3_start=True, gns3_keep=True))
        self.assertEqual(sorted(specs), ["client=docker://c0ffeeclient-1,nfs=0", "server=docker://c0ffeeserver,nfs=0"])
        calls = FakeGNS3.state["calls"]
        self.assertIn("/v2/projects/%s/open" % PID, calls)
        self.assertIn("/v2/projects/%s/nodes/start" % PID, calls)
        self.assertNotIn("/v2/projects/%s/nodes/stop" % PID, calls)

    def test_unknown_project_and_auth(self):
        with self.assertRaisesRegex(gns3.GNS3Error, "No GNS3 project named nope"):
            gns3.discover(self.opts(gns3="nope"))
        FakeGNS3.state["nodes"][0]["status"] = "started"
        FakeGNS3.state["nodes"][1]["status"] = "started"
        gns3.discover(self.opts(gns3_url="http://u:p@" + self.url[len("http://"):]))
        self.assertTrue(FakeGNS3.state["auth"].startswith("Basic "))

    def test_unreachable(self):
        with self.assertRaisesRegex(gns3.GNS3Error, "Cannot reach"):
            gns3.discover(self.opts(gns3_url="http://127.0.0.1:1"))


if __name__ == '__main__':
    unittest.main()
