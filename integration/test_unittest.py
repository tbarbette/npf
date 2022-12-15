import npf.npf
from npf.node import *
import types
import argparse
from collections import OrderedDict

from npf.repository import Repository
from npf.testie import Testie
from npf.build import Build
from npf.variable import dtype, numeric_dict
from npf.types.dataset import Run, ImmutableRun

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

def test_repo():
    args = test_args()
    r = Repository('click-2022', args)
    assert r.branch == '2022'
    return r

def test_node():
    args = test_args()
    args.do_test = False
    n1 = Node.makeSSH(addr="cluster01.sample.node", user=None, path=None, options=args)
    n2 = Node.makeSSH(addr="cluster01.sample", user=None, path=None, options=args)

    assert n1.executor.addr == "cluster01.example.com" == n2.executor.addr
    assert n1.executor.user == "user01" == n2.executor.user

def test_paths():

    args = test_args()
    args.do_test = False
    args.do_conntest = False
    args.experiment_folder = "test_root"


    local = Node.makeLocal(args,test_access=False)
    ssh = Node.makeSSH(addr="cluster01.sample", user=None, path=None, options=args)
    ssh2 = Node.makeSSH(addr="cluster01.sample", user=None, path=None, options=args)
    ssh.executor.path = "/different/path/to/root/"
    ssh2.executor.path = npf.experiment_path() + os.sep

    #Test the constants are correct

    testie = Testie("tests/examples/math.npf", options=args, tags=args.tags)
    repo = test_repo()
    build = Build(repo, "version")
    v={}
    testie.update_constants(v, build, ssh.experiment_path() + "/testie-1/", out_path=None)
    v2={}
    testie.update_constants(v2, build, ssh2.experiment_path() + "/testie-1/", out_path=None)
    vl={}
    testie.update_constants(vl, build, local.experiment_path() + "/testie-1/", out_path=None)
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
    assert ImmutableRun(ra) == ImmutableRun(rb)
    assert ImmutableRun(ra) == b
    assert a.inside(b)
    assert b.inside(a)
    assert a.__hash__() == b.__hash__()
