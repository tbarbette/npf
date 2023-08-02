import npf.npf
from npf.node import *
import types
import argparse
from collections import OrderedDict

from npf.repository import Repository
from npf.test import Test
from npf.build import Build
from npf.variable import dtype, numeric_dict
from npf.types.dataset import Run

def get_args():
    parser = argparse.ArgumentParser(description='NPF Tester')
    npf.add_verbosity_options(parser)
    npf.add_building_options(parser)
    npf.add_graph_options(parser)
    npf.add_testing_options(parser)
    args = parser.parse_args(args = "")
    args.tags = {}
    npf.set_args(args)
    npf.parse_nodes(args)
    return args

def test_args():
    assert(get_args())

def get_repo():
    args = get_args()
    r = Repository('click-2022', args)
    assert r.branch == '2022'
    return r

def test_repo():
    assert(get_repo())

def test_node():
    args = get_args()
    args.do_test = False
    n1 = Node.makeSSH(addr="cluster01.sample.node", user=None, path=None, options=args)
    n2 = Node.makeSSH(addr="cluster01.sample", user=None, path=None, options=args)

    assert n1.executor.addr == "cluster01.example.com" == n2.executor.addr
    assert n1.executor.user == "user01" == n2.executor.user

def test_paths():

    args = get_args()
    args.do_test = False
    args.do_conntest = False
    args.experiment_folder = "test_root"


    local = Node.makeLocal(args,test_access=False)
    ssh = Node.makeSSH(addr="cluster01.sample", user=None, path=None, options=args)
    ssh2 = Node.makeSSH(addr="cluster01.sample", user=None, path=None, options=args)
    ssh.executor.path = "/different/path/to/root/"
    ssh2.executor.path = npf.experiment_path() + os.sep

    #Test the constants are correct

    test = Test("tests/examples/math.npf", options=args, tags=args.tags)
    repo = get_repo()
    build = Build(repo, "version")
    v={}
    test.update_constants(v, build, ssh.experiment_path() + "/test-1/", out_path=None)
    v2={}
    test.update_constants(v2, build, ssh2.experiment_path() + "/test-1/", out_path=None)
    vl={}
    test.update_constants(vl, build, local.experiment_path() + "/test-1/", out_path=None)
    for d in [vl,v,v2]:
        assert v['NPF_REPO'] == 'Click_2022'
        assert v['NPF_ROOT_PATH'] == '../..'
        assert v['NPF_SCRIPT_PATH'] == '../../tests/examples'
        assert v['NPF_RESULT_PATH'] == '../../results/click-2022'

def test_type():
    assert dtype('0') == int
    assert dtype('') == str
    assert dtype('1') == int
    assert dtype(' ') == str

def test_runequality():
    ra = OrderedDict()
    ra["A"] = 1
    ra["B"] = "2"
    assert type(numeric_dict(ra)["B"] is int)
    a = Run(ra)
    rb = OrderedDict()
    rb["B"] = 2
    rb["A"] = 1
    b = Run(rb)
    assert a == b
    assert a.inside(b)
    assert b.inside(a)
    assert a.__hash__() == b.__hash__()
    h = a.__hash__()
    a.write_variables()["A"] = 3
    assert a.__hash__() != h
    assert a != b

def test_local_executor():
    l = LocalExecutor()
    pid, stdout, stderr, ret = l.exec("echo TEST")
    assert pid > 0
    assert stdout == "TEST\n"
    assert stderr == ""
    assert ret == 0

    pid, stdout, stderr, ret = l.exec("echo -n TEST")
    assert pid > 0
    assert stdout == "TEST"
    assert stderr == ""
    assert ret == 0

    pid, stdout, stderr, ret = l.exec("echo -n TEST 1>&2")
    assert pid > 0
    assert stdout == ""
    assert stderr == "TEST"
    assert ret == 0

    pid, stdout, stderr, ret = l.exec("exit 1")
    assert pid > 0
    assert stdout == ""
    assert stderr == ""
    assert ret == 1
