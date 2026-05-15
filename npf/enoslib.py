import logging
from typing import Dict, Iterable, List
import enoslib as en

import npf.cmdline as _cmdline
import npf.globals as _globals
import npf.parsing as _parsing
from npf.repo.repository import Repository
from npf.repo.factory import get_default_repository
from npf.cluster.node import Node
from npf.output import generate_outputs
from npf.output.grapher import Grapher
from npf.tests.test_driver import Comparator
import npf
import argparse

def run(npf_script, series:List[str] = [], roles:Dict[str,en.Host] = {"localhost":en.LocalHost}, argsv: List[str] = None, extra_vars: Dict[str, str] = {}):
    if argsv is None:
        argsv = []
    logging.getLogger('fontTools.subset').level = logging.WARN
    parser = argparse.ArgumentParser(description='NPF Test runner through enoslib')
    v = _cmdline.add_verbosity_options(parser)
    b = _cmdline.add_building_options(parser)
    t = _cmdline.add_testing_options(parser, regression=False)
    a = _cmdline.add_graph_options(parser)
    parser.add_argument('repos', metavar='repo', type=str, nargs='*', help='names of the repositories to compares. Use a format such as repo+VAR=VAL:Title to overwrite variables and serie name.')
    parser.add_argument('--graph-title', type=str, nargs='?', help='Graph title')

    full_args = ["--test", npf_script, *argsv]
    args = parser.parse_args(full_args)

    #The repo argument is just a trick to have the API look more pytonish
    args.repos.extend(series)

    _parsing.initialize(args)

    # Clear stale roles from previous calls (important in Jupyter where cells run multiple times)
    _globals.roles.clear()

    _parsing.create_local()

    #en.set_config(ansible_stdout="regular")

    for r, eno_objs in roles.items():
        from npf.executor.enoslibexecutor import EnoslibExecutor

        if not isinstance(eno_objs, Iterable):
            eno_objs=[eno_objs]
        for eno_obj in eno_objs:
            ex = EnoslibExecutor(eno_obj, extra_vars=extra_vars)
            node = Node(eno_obj.address, executor=ex, tags=args.tags)
            # Make ${role:ip} and ${role:addr} work for inter-node communication
            node.ip = eno_obj.address
            node.addr = eno_obj.address
            if r in _globals.roles:
                _globals.roles[r].append(node)
            else:
                _globals.roles[r] = [node]

    repo_list = []
    for repo_name in args.repos:
        repo = Repository.get_instance(repo_name, args)
        repo_list.append(repo)
    if not repo_list:
        repo = get_default_repository(args)
        repo_list.append(repo)

    comparator = Comparator(repo_list)


    series, time_series = comparator.run(test_name=args.test_files,
                                         tags=args.tags,
                                         options=args,
                                         do_regress=False)

    filename = npf.build_output_filename(repo_list)

    generate_outputs(filename, series=series, time_series=time_series, options=args)

    return series, time_series