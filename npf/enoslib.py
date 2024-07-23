import logging
from typing import Dict, List
import enoslib as en

from npf.grapher import Grapher
from npf.test_driver import Comparator, group_series
from npf.node import Node
from npf import npf
import argparse
from npf import repository

def run(npf_script, roles:Dict[str,en.Host], argsv:List[str]=[]):
    logging.getLogger('fontTools.subset').level = logging.WARN
    parser = argparse.ArgumentParser(description='NPF Test runner through enoslib')
    v = npf.add_verbosity_options(parser)
    b = npf.add_building_options(parser)
    t = npf.add_testing_options(parser, regression=False)
    a = npf.add_graph_options(parser)
    parser.add_argument('repos', metavar='repo', type=str, nargs='+', help='names of the repositories to compares. Use a format such as repo+VAR=VAL:Title to overwrite variables and serie name.')
    parser.add_argument('--graph-title', type=str, nargs='?', help='Graph title')

    full_args = ["--test", npf_script]
    full_args.extend(argsv)
    args = parser.parse_args(full_args)
    npf.initialize(args)
    npf.create_local()
    
    #en.set_config(ansible_stdout="regular")

    for r, eno_obj in roles.items():
        from npf.executor.enoslibexecutor import EnoslibExecutor
        ex = EnoslibExecutor(eno_obj)
        
        node = Node(eno_obj.address, executor=ex, tags=args.tags)
        if r in npf.roles:
            npf.roles[r].append(node)
        else:
            npf.roles[r] = [node]
    
    repo_list = []
    for repo_name in args.repos:
        repo = repository.Repository.get_instance(repo_name, args)
        repo_list.append(repo)
    
    comparator = Comparator(repo_list)
    
    
    series, time_series = comparator.run(test_name=args.test_files,
                                         tags=args.tags,
                                         options=args,
                                         do_regress=False)

    filename = npf.build_output_filename(args, repo_list)

    group_series(filename, args, series, time_series, options=args)