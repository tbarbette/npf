import argparse
import os
from argparse import ArgumentParser
from typing import Dict

import regex

from npf.node import Node
from .variable import VariableFactory

class ExtendAction(argparse.Action):
     def __init__(self, option_strings, dest, nargs=None, **kwargs):
         super(ExtendAction, self).__init__(option_strings, dest, nargs, **kwargs)

     def __call__(self, parser, namespace, values, option_string=None):
         setattr(namespace, self.dest, getattr(namespace,self.dest) + values)

def add_verbosity_options(parser: ArgumentParser):
    v = parser.add_argument_group('Verbosity options')
    v.add_argument('--show-full', help='Show full execution results',
                   dest='show_full', action='store_true',
                   default=False)
    v.add_argument('--show-files', help='Show content of created files',
                   dest='show_files', action='store_true',
                   default=False)
    v.add_argument('--show-cmd', help='Show the executed script',
                   dest='show_cmd', action='store_true',
                   default=False)

    v.add_argument('--quiet', help='Quiet mode', dest='quiet', action='store_true', default=False)
    vf = v.add_mutually_exclusive_group()
    vf.add_argument('--quiet-build', help='Do not tell about the build process', dest='quiet_build', action='store_true', default=False)
    vf.add_argument('--show-build-cmd', help='Show build commands', dest='show_build_cmd', action='store_true', default=False)
    return v


def add_graph_options(parser: ArgumentParser):

    o = parser.add_argument_group('Output data')
    o.add_argument('--output',
                   help='Output data to CSV', dest='output', type=str, default=None)


    g = parser.add_argument_group('Graph options')
    g.add_argument('--graph-size', metavar='INCH', type=float, nargs=2, default=[],
                   help='Size of graph', dest="graph_size")
    g.add_argument('--graph-filename', metavar='graph_filename', type=str,  default=None, dest='graph_filename',
                   help='path to the file to output the graph')
    g.add_argument('--graph-reject-outliers', dest='graph_reject_outliers', action='store_true', default=False)

    return g

def add_testing_options(parser: ArgumentParser, regression: bool = False):
    t = parser.add_argument_group('Testing options')
    tf = t.add_mutually_exclusive_group()
    tf.add_argument('--no-test',
                    help='Do not run any tests, use previous results', dest='do_test', action='store_false',
                    default=True)
    tf.add_argument('--force-test',
                    help='Force re-doing all tests even if data for the given version and '
                         'variables is already known', dest='force_test', action='store_true',
                    default=False)
    tf.add_argument('--no-init',
                    help='Do not run any init scripts', dest='do_init', action='store_false',
                    default=True)

    t.add_argument('--tags', metavar='tag', type=str, nargs='+', help='list of tags', default=[], action=ExtendAction)
    t.add_argument('--variables', metavar='variable=value', type=str, nargs='+', action=ExtendAction,
                   help='list of variables values to override', default=[])
    t.add_argument('--config', metavar='config=value', type=str, nargs='+', action=ExtendAction,
                   help='list of config values to override', default=[])

    t.add_argument('--testie', metavar='path or testie', type=str, nargs='?', default='tests',
                   help='script or script folder. Default is tests')

    t.add_argument('--cluster', metavar='user@address:path', type=str, nargs='*', default=[],
                   help='role to node mapping for remote execution of tests')

    t.add_argument('--build-folder', metavar='path', type=str, default=None, dest='build_folder')

    return t


nodePattern = regex.compile(
    "(?P<role>[a-zA-Z0-9]+)=(:?(?P<user>[a-zA-Z0-9]+)@)?(?P<addr>[a-zA-Z0-9.]+)(:?[:](?P<path>path))?")
roles = {}


def node(role,selfRole = None):
    if role is None or role == '':
        role = 'default'
    if role=='self':
        if selfRole:
            role = selfRole
        else:
            raise Exception("Using self without a role context. Usually, this happens when self is used in a %file")
    return roles.get(role, roles['default'])


def executor(role):
    """
    Return the executor for a given role as associated by the cluster configuration
    :param role: A role name
    :return: The executor
    """
    return node(role).executor


def parse_nodes(options):
    roles['default'] = Node.makeLocal(options)

    for mapping in options.cluster:
        match = nodePattern.match(mapping)
        if not match:
            raise Exception("Bad definition of node : %s" % mapping)
        node = Node.makeSSH(user=match.group('user'), addr=match.group('addr'), path=match.group('path'), options=options)
        roles[match.group('role')] = node


def parse_variables(args_variables) -> Dict:
    variables = {}
    for variable in args_variables:
        var, val = variable.split('=', 1)
        variables[var] = VariableFactory.build(var, val)
    return variables


def override(args, testies):
    overriden_variables = parse_variables(args.variables)
    overriden_config = parse_variables(args.config)
    for testie in testies:
        testie.variables.override_all(overriden_variables)
        testie.config.override_all(overriden_config)
    return testies


def add_building_options(parser):
    b = parser.add_argument_group('Building options')
    bf = b.add_mutually_exclusive_group()
    bf.add_argument('--use-local',
                    help='Use a local version of the program instead of the autmatically builded one', dest='use_local',
                    default=None)
    bf.add_argument('--no-build',
                    help='Do not build the last master', dest='no_build', action='store_true', default=False)
    bf.add_argument('--force-build',
                    help='Force to rebuild Click even if the git current version is matching the regression versions '
                         '(see --version or --history).', dest='force_build',
                    action='store_true', default=False)
    return b


def find_local(path):
    if not os.path.exists(path):
        return os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + '/' + path
    return path

def build_filename(testie, build,hint,variables,def_ext,type_str=''):
    var_str = '_'.join(["%s=%s" % (k,(val[1] if type(val) is tuple else val)) for k,val in variables.items()]).replace(' ','')
    if hint is None:
        return build.result_path(testie.filename, def_ext, suffix=var_str + ('-' + type_str if type_str else ''))
    else:
        dirname,c_filename = os.path.split(hint)
        if c_filename == '':
            basename = ''
            ext = ''
        else:
            basename, ext = os.path.splitext(c_filename)
            if not ext and basename.startswith('.'):
                ext = basename
                basename = ''

        if ext is None or ext == '':
            ext = '.' + def_ext

        if basename is None or basename is '':
            basename = var_str
        return (dirname + '/' if dirname else '') + basename + (('-' if basename else '') + type_str if type_str else '') + ext
