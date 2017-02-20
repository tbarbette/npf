from argparse import ArgumentParser

from .variable import VariableFactory,Variable

from typing import Dict


def add_verbosity_options(parser: ArgumentParser):
    v = parser.add_argument_group('Verbosity options')
    v.add_argument( '--show-full', help='Show full execution results',
                    dest='show_full', action='store_true',
                    default=False)

    v.add_argument( '--show-cmd', help='Show the executed script',
                    dest='show_cmd', action='store_true',
                    default=False)

    v.add_argument('--quiet', help='Quiet mode', dest='quiet', action='store_true', default=False)
    v.add_argument('--quiet-build', help='Quiet build mode', dest='quiet_build', action='store_true', default=False)
    return v


def add_graph_options(parser: ArgumentParser):
    g = parser.add_argument_group('Graph options')
    g.add_argument('--graph-size', metavar='INCH', type=int, nargs=2, default=[],
                   help='Size of graph', dest="graph_size");
    g.add_argument('--graph-filename', metavar='graph_filename', type=str, nargs=1, default=None,
                        help='path to the file to output the graph');
    g.add_argument('--graph-reject-outliers',dest='graph_reject_outliers', action='store_true', default=False)

    return g

def add_testing_options(parser: ArgumentParser, regression : bool = False):
    t = parser.add_argument_group('Testing options')
    tf = t.add_mutually_exclusive_group()
    tf.add_argument('--no-test',
                    help='Do not run any tests, use previous results', dest='do_test', action='store_false',
                    default=True)
    tf.add_argument('--force-test',
                    help='Force re-doing all tests even if data for the given version and '
                         'variables is already known', dest='force_test', action='store_true',
                    default=False)


    t.add_argument('--tags', metavar='tag', type=str, nargs='+', help='list of tags', default=[]);
    t.add_argument('--variables', metavar='variable=value', type=str, nargs='+',
                   help='list of variables values to override', default=[]);
    t.add_argument('--config', metavar='config=value', type=str, nargs='+',
                   help='list of config values to override', default=[]);

    t.add_argument('--testie', metavar='path or testie', type=str, nargs='?', default='tests',
                   help='script or script folder. Default is tests');

    return t


def parse_variables(args_variables) -> Dict:
    variables = {}
    for variable in args_variables:
        var, val = variable.split('=',1)
        variables[var] = VariableFactory.build(var,val)
    return variables

def override(args, testies):
    overriden_variables = parse_variables(args.variables)
    overriden_config = parse_variables(args.config)
    for testie in testies:
        testie.variables.override_all(overriden_variables)
        testie.config.override_all(overriden_config)
    return testies
