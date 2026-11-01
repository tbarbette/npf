"""Figures for the GNS3 demo (see README.md in this folder).

    python figures.py topology PROJECT out.png [--url http://127.0.0.1:3080] [--title TEXT]
        Draws a GNS3 project (nodes, links, interface names, status, text labels) from the GNS3 REST API. This is a
        rendering of the project data, not a capture of the GNS3 GUI.
    python figures.py terminal text.log out.png [--title TEXT] [--lines FIRST:LAST]
        Renders captured output as a terminal window.
"""
import argparse
import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Polygon  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from npf.cluster.gns3 import GNS3Client  # noqa: E402

COLORS = {"docker": "#2b6cb0", "nat": "#718096", "cloud": "#718096", "ethernet_switch": "#2f855a"}
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def topology(args):
    client = GNS3Client(args.url)
    pid = client.project(args.project)["project_id"]
    nodes = client.request("GET", "/projects/%s/nodes" % pid)
    links = client.request("GET", "/projects/%s/links" % pid)
    drawings = client.request("GET", "/projects/%s/drawings" % pid)
    by_id = {n["node_id"]: n for n in nodes}
    size = 60

    def center(n):
        return n["x"] + size / 2, n["y"] + size / 2

    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=130)
    fig.patch.set_facecolor("#eef1f5")
    ax.set_facecolor("#f8fafc")
    ax.grid(color="#e2e8f0", linewidth=0.6)
    ax.set_axisbelow(True)

    for link in links:
        (a, b) = link["nodes"]
        (x1, y1), (x2, y2) = center(by_id[a["node_id"]]), center(by_id[b["node_id"]])
        up = by_id[a["node_id"]]["status"] == "started" and by_id[b["node_id"]]["status"] == "started"
        ax.plot([x1, x2], [y1, y2], color="#38a169" if up else "#a0aec0", linewidth=2, zorder=1)
        for end, other, ep in ((a, (x2, y2), (x1, y1)), (b, (x1, y1), (x2, y2))):
            t = 0.36
            lx, ly = ep[0] + (other[0] - ep[0]) * t, ep[1] + (other[1] - ep[1]) * t
            ax.text(lx, ly - 7, (end.get("label") or {}).get("text") or "e%d" % end["adapter_number"],
                    fontsize=7, ha="center", color="#2d3748", zorder=3,
                    bbox=dict(boxstyle="round,pad=0.15", fc="#f8fafc", ec="none", alpha=0.9))

    for n in nodes:
        cx, cy = center(n)
        color = COLORS.get(n["node_type"], "#4a5568")
        if n["node_type"] in ("nat", "cloud"):
            for dx, dy, r in ((-13, 4, 14), (0, -6, 18), (14, 4, 14)):
                ax.add_patch(Circle((cx + dx, cy + dy), r, fc=color, ec="none", zorder=2))
        elif "router" in (n.get("symbol") or ""):
            ax.add_patch(Circle((cx, cy), 28, fc=color, ec="white", lw=2, zorder=2))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ax.annotate("", (cx + dx * 20, cy + dy * 20), (cx + dx * 6, cy + dy * 6),
                            arrowprops=dict(arrowstyle="-|>", color="white", lw=1.6), zorder=3)
        elif "server" in (n.get("symbol") or ""):
            for i in range(3):
                ax.add_patch(FancyBboxPatch((cx - 22, cy - 28 + i * 19), 44, 16, boxstyle="round,pad=0,rounding_size=3",
                                            fc=color, ec="white", lw=1.5, zorder=2))
                ax.add_patch(Circle((cx + 14, cy - 20 + i * 19), 2, fc="#9ae6b4", ec="none", zorder=3))
        else:
            ax.add_patch(FancyBboxPatch((cx - 26, cy - 22), 52, 34, boxstyle="round,pad=0,rounding_size=4", fc=color,
                                        ec="white", lw=2, zorder=2))
            ax.add_patch(Polygon([(cx - 14, cy + 22), (cx + 14, cy + 22), (cx + 8, cy + 14), (cx - 8, cy + 14)],
                                 fc=color, ec="white", lw=1.5, zorder=2))
        ax.add_patch(Circle((cx - 30, cy - 28), 5, fc="#38a169" if n["status"] == "started" else "#e53e3e", ec="white",
                            lw=1.2, zorder=4))
        ax.text(cx, cy - 44, n["name"], ha="center", va="center", fontsize=10, fontweight="bold", color="#1a202c",
                zorder=4)

    for d in drawings:
        m = re.search(r">([^<]+)</text>", d["svg"])
        c = re.search(r'fill="(#[0-9a-fA-F]+)"', d["svg"])
        if m:
            ax.text(d["x"], d["y"] + 12, m.group(1), fontsize=9, color=c.group(1) if c else "#000", family="monospace",
                    zorder=3)

    xs = [n["x"] for n in nodes]
    ys = [n["y"] for n in nodes]
    ax.set_xlim(min(xs) - 90, max(xs) + 160)
    ax.set_ylim(max(ys) + 130, min(ys) - 80)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#cbd5e0")
    ax.set_title(args.title or "GNS3 project %s (%s)" % (args.project, client.hostname), fontsize=11, loc="left",
                 color="#2d3748")
    fig.text(0.99, 0.01, "rendered from the GNS3 API", ha="right", fontsize=7, color="#718096")
    fig.tight_layout()
    fig.savefig(args.out)


def terminal(args):
    with open(args.text, errors="replace") as f:
        lines = [ANSI.sub("", l.rstrip("\n")) for l in f]
    if args.lines:
        a, _, b = args.lines.partition(":")
        lines = lines[int(a or 1) - 1:int(b) if b else None]
    width = 118
    wrapped = []
    for l in lines:
        wrapped += [l[i:i + width] for i in range(0, max(len(l), 1), width)]
    h = 0.2 * len(wrapped) + 0.75
    fig = plt.figure(figsize=(11.5, h), dpi=130)
    fig.patch.set_facecolor("#1e1e2e")
    for i, c in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        fig.patches.append(Circle((0.018 + i * 0.016, 1 - 0.28 / h), 0.006, transform=fig.transFigure, fc=c,
                                  ec="none"))
    if args.title:
        fig.text(0.5, 1 - 0.28 / h, args.title, ha="center", va="center", color="#a6adc8", fontsize=9)
    y = 1 - 0.6 / h
    for l in wrapped:
        color = "#cdd6f4"
        if l.startswith("$ "):
            color = "#a6e3a1"
        elif "RESULT-" in l:
            color = "#89b4fa"
        elif re.search(r"WARNING|ignored|Could not|error", l):
            color = "#f9e2af"
        fig.text(0.012, y, l, family="monospace", fontsize=7.6, color=color, va="top")
        y -= 0.2 / h
    fig.savefig(args.out, facecolor=fig.get_facecolor())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("topology")
    t.add_argument("project")
    t.add_argument("out")
    t.add_argument("--url", default=None)
    t.add_argument("--title", default=None)
    t.set_defaults(func=topology)
    c = sub.add_parser("terminal")
    c.add_argument("text")
    c.add_argument("out")
    c.add_argument("--title", default=None)
    c.add_argument("--lines", default=None, help="FIRST:LAST (1-based)")
    c.set_defaults(func=terminal)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
