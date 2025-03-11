import logging
from typing import Dict, Iterable, List
import enoslib as en

import npf.cmdline
import npf.globals
import npf.parsing
from npf.repo.repository import Repository
from npf.repo.factory import get_default_repository
from npf.cluster.node import Node
from npf.output import generate_outputs
from npf.output.grapher import Grapher
from npf.tests.test_driver import Comparator
import npf
import argparse

def run(npf_script, series:List[str] = [], roles:Dict[str,en.Host] = {"localhost":en.LocalHost}, argsv: List[str] = None):
    if argsv is None:
        argsv = []
    logging.getLogger('fontTools.subset').level = logging.WARN
    parser = argparse.ArgumentParser(description='NPF Test runner through enoslib')
    v = npf.cmdline.add_verbosity_options(parser)
    b = npf.cmdline.add_building_options(parser)
    t = npf.cmdline.add_testing_options(parser, regression=False)
    a = npf.cmdline.add_graph_options(parser)
    parser.add_argument('repos', metavar='repo', type=str, nargs='*', help='names of the repositories to compares. Use a format such as repo+VAR=VAL:Title to overwrite variables and serie name.')
    parser.add_argument('--graph-title', type=str, nargs='?', help='Graph title')

    full_args = ["--test", npf_script, *argsv]
    args = parser.parse_args(full_args)

    #The repo argument is just a trick to have the API look more pytonish
    args.repos.extend(series)

    npf.parsing.initialize(args)
    npf.parsing.create_local()

    #en.set_config(ansible_stdout="regular")

    for r, eno_objs in roles.items():
        from npf.executor.enoslibexecutor import EnoslibExecutor

        if not isinstance(eno_objs, Iterable):
            eno_objs=[eno_objs]
        for eno_obj in eno_objs:
            ex = EnoslibExecutor(eno_obj)
            node = Node(eno_obj.address, executor=ex, tags=args.tags)
            if r in npf.globals.roles:
                npf.globals.roles[r].append(node)
            else:
                npf.globals.roles[r] = [node]

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