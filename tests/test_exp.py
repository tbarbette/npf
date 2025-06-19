from . import logger

from collections import OrderedDict

from npf.models.dataset import Run
from npf.expdesign.gpexp import GPVariableExpander
from npf.expdesign.multiexp import MultiVariableExpander
from npf.expdesign.twokexp import TWOKVariableExpander
from npf.expdesign.zltexp import ZLTVariableExpander
from npf.models.variables.RangeVariable import RangeVariable

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
    vlist = {'RATE' : RangeVariable("RATE",1,20,log=False)} #From 1 to 10 included
    results = OrderedDict()
    zlt = ZLTVariableExpander(vlist, results, {}, "RATE", "PPS", 1.01, all=all, monotonic=monotonic)
    it = iter(zlt)
    run = next(it)
    assert run["RATE"] == 20
    results[Run({'RATE' : 20})] = {'PPS':[6.0]}
    run = next(it)
    assert run["RATE"] == 6
    results[Run({'RATE' : 6})] = {'PPS':[6.0]}
    if all == 1:
        for i in range(5,0,-1):
            print("all",i)
            run = next(it)
            assert run["RATE"] == i
            results[Run({'RATE' : i})] = {'PPS':[i]}
    if all == 2:
        for i in [5,4,2,1]:
            print("all",i)
            run = next(it)
            assert run["RATE"] == i
            results[Run({'RATE' : i})] = {'PPS':[i]}
    if not monotonic:
        run = next(it)
        print("mono",run)
        assert run["RATE"] == 7
        results[Run({'RATE' : 7})] = {'PPS':[6.1]}
    try:
        run = next(it)
        print("last", run)
        assert False
    except StopIteration:
        pass
    logger.error(run)


def test_multi():
    vlist = {'RATE' : RangeVariable("RATE",1,10,log=False)}
    results = OrderedDict()
    twok = MultiVariableExpander([TWOKVariableExpander(vlist, results),TWOKVariableExpander(vlist, results)])
    it = iter(twok)
    run = next(it)
    assert run["RATE"] == 1
    run = next(it)
    assert run["RATE"] == 10
    run = next(it)
    assert run["RATE"] == 1
    run = next(it)
    assert run["RATE"] == 10
    try:
        next(it)
        assert False
    except StopIteration:
        pass



def test_gp():

    vlist = {'RATE' : RangeVariable("RATE",1,10,log=False)}
    results = OrderedDict()
    def fake_run(val):
        results[Run({'RATE' : val})] = {'PPS':[val if val < 7 else val / 0.9]}
    twok = TWOKVariableExpander(vlist, results)
    it = iter(twok)
    run = next(it)
    assert run["RATE"] == 1
    fake_run(1)
    run = next(it)
    assert run["RATE"] == 10
    fake_run(10)
    try:
        next(it)
        assert False
    except StopIteration:
        pass
    gp = GPVariableExpander(vlist,{}, results,ci=0.95)
    it = iter(gp)
    run = next(it)
    assert run["RATE"] == 2
    fake_run(2)
    try:
        run = next(it)
        assert False
    except StopIteration:
        pass

def test_allzlt():
    for a in (0,1,2):
        _test_allzlt(monotonic=True, all=a)
        _test_allzlt(monotonic=False, all=a)


def test_2K():
    vlist = {'RATE' : RangeVariable("RATE",1,10,log=False)}
    results = OrderedDict()
    twok = TWOKVariableExpander(vlist, results)
    it = iter(twok)
    run = next(it)
    assert run["RATE"] == 1
    run = next(it)
    assert run["RATE"] == 10
    try:
        next(it)
        assert False
    except StopIteration:
        pass