import unittest
import argparse


from npf import cmdline

from npf.expdesign.zltexp import ZLTVariableExpander
from npf.output.grapher import Grapher
from npf.tests import repository
from npf.tests.build import Build
from npf.tests.test_driver import Comparator
from npf.cluster.node import *

from collections import OrderedDict

from npf.tests.repository import Repository
from npf.tests.test import Test
from npf.tests.variable import RangeVariable, SimpleVariable, dtype
from npf.types.dataset import Run

import numpy as np
import logging

from npf.types.units import numeric_dict

logger = logging.getLogger()
logger.level = logging.DEBUG
stream_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(stream_handler)


def get_args():
    parser = argparse.ArgumentParser(description='NPF Tester')
    cmdline.add_verbosity_options(parser)
    cmdline.add_building_options(parser)
    cmdline.add_graph_options(parser)
    cmdline.add_testing_options(parser)
    args = parser.parse_args(args = "")
    args.tags = {}
    npf.globals.set_args(args)
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
    n1 = Node.makeSSH(addr="cluster01.sample.node", user=None, path=None)
    n2 = Node.makeSSH(addr="cluster01.sample", user=None, path=None)

    assert n1.executor.addr == "cluster01.example.com" == n2.executor.addr
    assert n1.executor.user == "user01" == n2.executor.user

def test_paths():

    args = get_args()
    args.do_test = False
    args.do_conntest = False
    args.experiment_folder = "test_root"


    local = Node.makeLocal(test_access=False)
    ssh = Node.makeSSH(addr="cluster01.sample", user=None, path=None)
    ssh2 = Node.makeSSH(addr="cluster01.sample", user=None, path=None)
    ssh.executor.path = "/different/path/to/root/"
    ssh2.executor.path = npf.experiment_path() + os.sep

    #Test the constants are correct

    test = Test("examples/math.npf", options=args, tags=args.tags)
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
        assert v['NPF_SCRIPT_PATH'] == '../../examples'
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
        v = cmdline.add_verbosity_options(parser)
        b = cmdline.add_building_options(parser)
        t = cmdline.add_testing_options(parser, regression=False)
        a = cmdline.add_graph_options(parser)
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


        filename = npf.build_output_filename(repo_list)
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


def _test_allzlt(monotonic,all=True):
    vlist = {'RATE' : RangeVariable("RATE",1,10,log=False)} #From 1 to 10 included
    results = OrderedDict()
    zlt = ZLTVariableExpander(vlist, results, {}, "RATE", "PPS", 1.01, all=all, monotonic=monotonic)
    it = iter(zlt)
    run = next(it)
    assert run["RATE"] == 10
    results[Run({'RATE' : 10})] = {'PPS':[3.0]}
    run = next(it)
    assert run["RATE"] == 3
    results[Run({'RATE' : 3})] = {'PPS':[3]}
    if all:
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
    _test_allzlt(monotonic=True, all=False)
    _test_allzlt(monotonic=False, all=False)

def test_test_main():
    t = Test("examples/iperf.npf", options = npf.globals.options)

def test_web():
    from npf.output import web

def test_notebook():
    from npf.output import notebook

def test_enoslib():
    try:
        import enoslib
        from npf.enoslib import run
        run('integration/sections.npf', roles={"localhost":"127.0.0.1"}, argsv=[])

    except ImportError as e:
        pass  # module doesn't exist, deal with it.

def test_import_mains():
    import npf
    import npf_regress
    import npf_watch
