import npf.npf
from npf.node import *
import types
import argparse

from npf.repository import Repository

def test_args():
    parser = argparse.ArgumentParser(description='NPF Tester')
    npf.add_verbosity_options(parser)
    npf.add_building_options(parser)
    npf.add_graph_options(parser)
    npf.add_testing_options(parser)
    args = parser.parse_args(args = "")
    args.tags = {}
    npf.set_args(args)
    return args

def test_node():
    args = test_args()
    n1 = Node("cluster01.sample.node", Node.makeLocal(args, test_access=False), args.tags)
    n2 = Node("cluster01.sample", Node.makeLocal(args, test_access=False), args.tags)
    assert n1.executor.addr == "cluster01.example.com" == n2.executor.addr
    assert n1.executor.user == "user01" == n2.executor.user

def test_repo():
    args = test_args()
    r = Repository('click-2021', args)
    assert r.branch == '2021'
