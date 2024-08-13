import unittest
from npf import repository
from npf.expdesign.zltexp import ZLTVariableExpander
from npf.grapher import Grapher
from npf.test_driver import Comparator
import npf.npf
from npf.node import *
import argparse
from collections import OrderedDict

from npf.repository import Repository
from npf.test import Test
from npf.build import Build
from npf.variable import RangeVariable, SimpleVariable, dtype, numeric_dict
from npf.types.dataset import Run

import numpy as np
import logging


logger = logging.getLogger()
logger.level = logging.DEBUG
stream_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(stream_handler)


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


def test_core():
        parser = argparse.ArgumentParser(description='NPF test')
        v = npf.add_verbosity_options(parser)
        b = npf.add_building_options(parser)
        t = npf.add_testing_options(parser, regression=False)
        a = npf.add_graph_options(parser)
        parser.add_argument('repo', metavar='repo name', type=str, nargs='?', help='name of the repo/group of builds', default=None)

        full_args = ["--test", "integration/sections.npf",'--force-retest']
        args = parser.parse_args(full_args)
        npf.initialize(args)
        npf.create_local()

        repo_list = [repository.Repository.get_instance("local", options=args)]

        comparator = Comparator(repo_list)

        series, time_series = comparator.run(test_name=args.test_files,
                                             tags=args.tags,
                                             options=args)
        assert len(series) == 1
        r = series[0][2]
        assert len(r.items()) == 1
        run,results = list(r.items())[0]
        assert run.variables["N"] == 1
        assert np.all(np.array(results["SCRIPT"]) == 42)
        assert np.all(np.array(results["CLEANUP"]) == 1)
        assert np.all(np.array(results["PY"]) == 1)


        filename = npf.build_output_filename(args, repo_list)
        grapher = Grapher()

        print("Generating graphs...")
        g = grapher.graph(series=series,
                          filename=filename,
                          options=args
                          )

def test_zlt():
    vlist = {'RATE' : RangeVariable("RATE",1,10,log=False)}
    results = OrderedDict()
    zlt = ZLTVariableExpander(vlist, results, {}, "RATE", "PPS", 1.01)
    it = iter(zlt)
    run = next(it)
    assert run["RATE"] == 10
    results[Run({'RATE' : 10})] = {'PPS':[3.0]}
    run = next(it)
    assert run["RATE"] == 3
    results[Run({'RATE' : 3})] = {'PPS':[1.5]}
    run = next(it)
    assert run["RATE"] == 1
    results[Run({'RATE' : 1})] = {'PPS':[1]}
    run = next(it)
    assert run["RATE"] == 2
    results[Run({'RATE' : 2})] = {'PPS':[1.5]}
    try:
        next(it)
        assert False
    except StopIteration:
        pass
    logger.error(run)


def _test_allzlt(monotonic):
    vlist = {'RATE' : RangeVariable("RATE",1,10,log=False)}
    results = OrderedDict()
    zlt = ZLTVariableExpander(vlist, results, {}, "RATE", "PPS", 1.01,all=True,monotonic=monotonic)
    it = iter(zlt)
    run = next(it)
    assert run["RATE"] == 10
    results[Run({'RATE' : 10})] = {'PPS':[3.0]}
    run = next(it)
    assert run["RATE"] == 3
    results[Run({'RATE' : 3})] = {'PPS':[3]}
    run = next(it)
    assert run["RATE"] == 2
    results[Run({'RATE' : 2})] = {'PPS':[2]}
    run = next(it)
    assert run["RATE"] == 1
    results[Run({'RATE' : 1})] = {'PPS':[1]}
    if not monotonic:
        run = next(it)
        assert run["RATE"] == 4
        results[Run({'RATE' : 4})] = {'PPS':[3.1]}
    try:
        next(it)
        assert False
    except StopIteration:
        pass
    logger.error(run)

def test_allzlt():
    _test_allzlt(monotonic=True)
    _test_allzlt(monotonic=False)