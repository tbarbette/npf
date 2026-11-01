"""Creates the small proof-of-concept testbed of examples/docker-web.npf as a GNS3 project, through the REST API.

    client-1 --- dut --- server          10.0.1.0/24 and 10.0.2.0/24, the DUT routes between them
                  |
                 NAT                      uplink to the Internet (libvirt's virbr0), for --tags real

    python examples/gns3/poc.py [--url http://127.0.0.1:3080] [--name npf-poc] [--image npf-node] [--recreate]
    npf --test examples/docker-web.npf local --gns3 npf-poc --gns3-start

Node names give the NPF roles. Addresses are set by the start command of each node, the same way you would set them in
the GNS3 GUI (Edit config / start command of a Docker node).

Every node first sets the MTU to 1500 and turns off TSO/GSO/GRO on its interfaces. Without it, a TCP transfer of a few
MB makes the kernel hand ubridge frames of up to 64 KB that its UDP tunnel cannot carry: ubridge logs "send: Message
too long" and the links of that node stay dead until it is restarted.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from npf.cluster.gns3 import GNS3Client, GNS3Error  # noqa: E402

COMMON = ("for i in $(ls /sys/class/net | grep '^eth'); do ip link set dev $i mtu 1500; "
          "ethtool -K $i tso off gso off gro off lro off > /dev/null 2>&1; done; ip link set lo up; ")
CLIENT = COMMON + ("ip addr add 10.0.1.2/24 dev eth0; ip link set eth0 up; ip route add default via 10.0.1.1; "
                   "echo nameserver 192.168.122.1 > /etc/resolv.conf; exec sleep infinity")
SERVER = COMMON + ("ip addr add 10.0.2.2/24 dev eth0; ip link set eth0 up; ip route add default via 10.0.2.1; "
                   "exec nginx -g 'daemon off;'")
DUT = COMMON + ("ip addr add 10.0.1.1/24 dev eth0; ip addr add 10.0.2.1/24 dev eth1; "
                "ip link set eth0 up; ip link set eth1 up; ip link set eth2 up; "
                "sysctl -q -w net.ipv4.ip_forward=1; "
                "udhcpc -i eth2 -q -n -t 10 || echo 'No DHCP lease on eth2 (NAT)'; "
                "iptables -t nat -A POSTROUTING -o eth2 -j MASQUERADE; exec sleep infinity")


def label(text, x, y, color="#000000", size=14):
    return {"x": x, "y": y, "z": 2, "svg": '<svg width="%d" height="%d"><text font-family="TypeWriter" font-size="%d" '
                                           'fill="%s">%s</text></svg>' % (len(text) * size, size * 2, size, color, text)}


def docker(name, image, adapters, start, x, y, symbol):
    return {"name": name, "node_type": "docker", "compute_id": "local", "x": x, "y": y, "symbol": symbol,
            "properties": {"image": image, "adapters": adapters, "start_command": 'sh -c "%s"' % start.replace('"', '\\"'),
                           "console_type": "telnet", "environment": ""}}


def build(client, name, image, recreate):
    for p in client.projects():
        if p["name"] == name:
            if not recreate:
                raise GNS3Error("Project %s already exists, use --recreate" % name)
            if p.get("status") == "opened":
                client.request("POST", "/projects/%s/nodes/stop" % p["project_id"], {})
            client.request("DELETE", "/projects/%s" % p["project_id"])
    # auto_close off: else closing the web UI closes the project and stops the nodes, during a test too
    pid = client.request("POST", "/projects", {"name": name, "auto_close": False})["project_id"]
    path = "/projects/%s" % pid

    def add_node(spec):
        return client.request("POST", path + "/nodes", spec)["node_id"]

    c = add_node(docker("client-1", image, 1, CLIENT, -320, 0, ":/symbols/computer.svg"))
    d = add_node(docker("dut", image, 3, DUT, 0, 0, ":/symbols/router.svg"))
    s = add_node(docker("server", image, 1, SERVER, 320, 0, ":/symbols/server.svg"))
    n = add_node({"name": "NAT", "node_type": "nat", "compute_id": "local", "x": 0, "y": 200,
                  "symbol": ":/symbols/cloud.svg"})

    def link(a, ai, b, bi):
        client.request("POST", path + "/links", {"nodes": [{"node_id": a, "adapter_number": ai, "port_number": 0},
                                                           {"node_id": b, "adapter_number": bi, "port_number": 0}]})

    link(c, 0, d, 0)
    link(d, 1, s, 0)
    link(d, 2, n, 0)

    for spec in (label("10.0.1.0/24", -215, -45), label("10.0.2.0/24", 125, -45),
                 label("NPF role: client", -355, 70, "#1f5fbf"), label("NPF role: dut", -35, 70, "#1f5fbf"),
                 label("NPF role: server", 285, 70, "#1f5fbf"), label("to the Internet (real sites)", 170, 225, "#555555")):
        client.request("POST", path + "/drawings", spec)
    return pid


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=None, help="GNS3 server (default $GNS3_URL or http://127.0.0.1:3080)")
    parser.add_argument("--name", default="npf-poc")
    parser.add_argument("--image", default="npf-node", help="Docker image of the nodes (see examples/docker-testbed)")
    parser.add_argument("--recreate", action="store_true", help="delete the project first if it exists")
    args = parser.parse_args()
    client = GNS3Client(args.url)
    try:
        pid = build(client, args.name, args.image, args.recreate)
    except GNS3Error as e:
        print(e, file=sys.stderr)
        return 1
    print("Project %s created (%s)" % (args.name, pid))
    print("Web UI: %s/static/web-ui/bundled" % client.base.rsplit("/v", 1)[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
