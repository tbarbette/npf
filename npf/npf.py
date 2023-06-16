import sys
import argparse
import os
from argparse import ArgumentParser
from typing import Dict, List

import regex
import re
from decimal import Decimal

from npf.node import Node
from .variable import VariableFactory

import numpy as np

options = None
cwd = None

def get_valid_filename(s):
    s = str(s).strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '', s)

class ExtendAction(argparse.Action):
    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        super(ExtendAction, self).__init__(option_strings, dest, nargs, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, getattr(namespace, self.dest) + values)


def add_verbosity_options(parser: ArgumentParser):
    v = parser.add_argument_group('Verbosity options')
    v.add_argument('--show-full', '--show-all', help='Deprecated : show full execution results, this is now the default. Use --quiet instead.',
                   dest="deprecated_0", action='store_true',
                   default=False)
    v.add_argument('--show-files', help='Show content of created files',
                   dest='show_files', action='store_true',
                   default=False)
    v.add_argument('--show-cmd', help='Show the executed script',
                   dest='show_cmd', action='store_true',
                   default=False)
    v.add_argument('--show-time-results', help='Show time results',
                   dest='print_time_results', action='store_true',
                   default=False)

    v.add_argument('--quiet', help='Quiet mode', dest='quiet', action='store_true', default=False)
    v.add_argument('--quiet-regression', help='Do not tell about the regression process', dest='quiet_regression',
                    action='store_true', default=False)

    v.add_argument('--debug', help='Debug mode : show scripts execution and termination and more information about synchronization', dest='debug', action='store_true', default=False)

    vf = v.add_mutually_exclusive_group()
    vf.add_argument('--quiet-build', help='Do not tell about the build process', dest='quiet_build',
                    action='store_true', default=False)
    vf.add_argument('--show-build-cmd', help='Show build commands', dest='show_build_cmd', action='store_true',
                    default=False)

    from npf.version import __version__
    v.add_argument('--version', action='version',
                    version='%(prog)s {version}'.format(version=__version__))

    return v


def add_graph_options(parser: ArgumentParser):
    o = parser.add_argument_group('Output data')
    o.add_argument('--output',
                   help='Output data to CSV files, one per result type. By default it prints the variable value as first column and the second column is the mean of all runs. Check --output-columns to change this behavior.', dest='output', type=str, nargs='?', const='graph', default=None)
    o.add_argument('--output-columns', dest='output_columns', type=str, nargs='+', default=['x', 'mean'],
                    help='Columns to print in each --output CSV files. By default x mean. Valid values are mean/average, min, max, perc[0-9]+, med/median/perc50, std, nres/n, first, last, all. Check the documentation for details.')
    o.add_argument('--single-output', '--pandas', metavar='pandas_filename', type=str, default=None, dest='pandas_filename',
                    help='Output a dataframe to CSV with all result types as columns, and one line per variables and per runs. This is a pandas dataframe, and can be read with pandas easily again. Time series are each outputed in a single different CSV.')

    g = parser.add_argument_group('Graph options')
    g.add_argument('--graph-size', metavar='INCH', type=float, nargs=2, default=None,
                   help='Size of graph', dest="graph_size")
    g.add_argument('--graph-filename', metavar='graph_filename', type=str, default=None, dest='graph_filename',
                   help='path to the file to output the graph')

    g.add_argument('--show-serie', dest='show_serie', action='store_true', default=False, help='always add the serie name in the file path')
    g.add_argument('--graph-reject-outliers', dest='graph_reject_outliers', action='store_true', default=False)

    g.add_argument('--graph-no-series', dest='graph_no_series', action='store_true', default=False)

    g.add_argument('--graph-group-repo', dest='group_repo', action='store_true', default=False, help="Group series, using the repository name as a variable")

    g.add_argument('--graph-group-series', dest='group_series', action='store_true', default=False, help="Group series with the same name")
    g.add_argument('--no-transform', dest='do_transform', action='store_false', default=True, help="Forbid automatic transformation of data such as extracting a variable as a serie")

    g.add_argument('--graph-select-max', dest='graph_select_max', type=int, default=None)

    g.add_argument('--graph-dpi', dest='graph_dpi', type=int, default=300)

    g.add_argument('--no-graph-time', dest='do_time', action='store_false', default=True)

    g.add_argument('--no-graph', dest='no_graph', action='store_true', default=False)

    g.add_argument('--iterative', dest='iterative', action='store_true', default=False,
                   help='Graph after each results, allowing to get a faster glimpse at the results')
    g.add_argument('--onefirst', dest='onefirst', action='store_true', default=False,
                   help='Do a first pass with one run per variables, then do the last runs')


    s = parser.add_argument_group('Statistics options')
    s.add_argument('--statistics',
                   help='Give some statistics output', dest='statistics', action='store_true',
                   default=False)
    s.add_argument('--statistics-maxdepth',
                   help='Max depth of learning tree', dest='statistics_maxdepth', type=int, default=None)
    s.add_argument('--statistics-filename',
                   help='Output of learning tree', dest='statistics_filename', type=str, default=None)

    return g


def add_testing_options(parser: ArgumentParser, regression: bool = False):
    t = parser.add_argument_group('Testing options')
    tf = t.add_mutually_exclusive_group()
    tf.add_argument('--no-test',
                    help='Do not run any tests, use previous results', dest='do_test', action='store_false',
                    default=True)
    t.add_argument('--no-supplementary-test',
                    help='Do not run supplementary tests for regression, use previous results', dest='allow_supplementary', action='store_false',
                    default=True)
    tf.add_argument('--force-test',
                    help='Force re-doing all tests even if data for the given version and '
                         'variables is already known, but append the new data to exesting one', dest='force_test', action='store_true',
                    default=False)
    tf.add_argument('--force-retest',
                    help='Force re-doing all tests even if data for the given version and '
                         'variables is already known, and replace it', dest='force_retest', action='store_true',
                    default=False)
    t.add_argument('--no-init',
                   help='Do not run any init scripts', dest='do_init', action='store_false',
                   default=True)
    t.add_argument('--no-conntest',
                   help='Do not run connection tests', dest='do_conntest', action='store_false',
                   default=True)
    t.add_argument('--max-results',
                   help='Count the number of valid previous tests as the maxium number of points in all tests, instead of the minimum', dest='min_test', action='store_false',
                   default=True)
    t.add_argument('--preserve-temporaries',
                   help='Do not delete tesite folder with temporary files', dest='preserve_temp',
                   action='store_true',
                   default=False)
    t.add_argument('--use-last',
                   help='Use data from previous version instead of running test if possible', dest='use_last',
                   nargs='?',
                   default=0)
    t.add_argument('--result-path', '--result-folder', metavar='path', type=str, nargs=1, help='Path to NPF\'s own database of results. By default it is a "result" folder.', default=["results"])
    t.add_argument('--tags', metavar='tag', type=str, nargs='+', help='list of tags', default=[], action=ExtendAction)
    t.add_argument('--variables', metavar='variable=value', type=str, nargs='+', action=ExtendAction,
                   help='list of variables values to override', default=[])
    t.add_argument('--config', metavar='config=value', type=str, nargs='+', action=ExtendAction,
                   help='list of config values to override', default=[])

    t.add_argument('--test', '--test', '--npf', dest='test_files', metavar='path or test', type=str, nargs='?', default='tests',
                   help='script or script folder. Default is tests')


    t.add_argument('--build-folder', '--build-path', metavar='path', type=str, default=None, dest='build_folder', help='Set where dependencies would be built. Defaults to npf\'s folder itself, so dependencies are shared between test scripts.')

    t.add_argument('--experiment-folder', '--experiment-path', metavar='path', type=str, default="./", dest='experiment_folder', help='Where to create temporary files and execute tests from. Default to local directory. Tests will always be executed from a temporary-made folder inside that path. Beware if you do not have a similar NFS/SSHFS based directory identical on all nodes, the "path" argument of the cluster file must match this repository, same as the build path relative to that directory.')

    t.add_argument('--search-path', metavar='path', type=str, default=[], nargs='+', dest='search_path', help='Search for various files in this directories too (such as the parent of your own repo, cluster or modules folder)')
    t.add_argument('--no-mp', dest='allow_mp', action='store_false',
                   default=True, help='Run tests in the same thread. If there is multiple script, they will run '
                                      'one after the other, hence breaking most of the tests.')
    t.add_argument('--expand', type=str, default=None, dest="expand")
    t.add_argument('--rand-env', type=int, default=65536, dest="rand_env")
    t.add_argument('--experimental-design', type=str, default="matrix.csv", help="The path towards the experimental design point selection file")

    c = parser.add_argument_group('Cluster options')
    c.add_argument('--cluster', metavar='role=user@address:path [...]', type=str, nargs='*', default=[],
                   help='role to node mapping for remote execution of tests. The format is role=address, where address can be an address or a file in cluster/address.node describing supplementary parameters for the node.')
    c.add_argument('--cluster-autosave', default=False, action='store_true', dest='cluster_autosave',
                    help='Automatically save NICs found on the machine. If the file cluster/address.node does not exists, NPF will attempt to auto-discover NICs. If this option is set, it will auto-create the file.')


    return t



def add_building_options(parser):
    b = parser.add_argument_group('Building options')
    bf = b.add_mutually_exclusive_group()
    bf.add_argument('--use-local',
                    help='Use a local version of the program instead of the automatically builded one',
                    dest='use_local',
                    default=None)
    bf.add_argument('--no-build',
                    help='Do not build the last version, use the currently compiled one', dest='no_build', action='store_true', default=False)
    bf.add_argument('--force-build',
                    help='Force to rebuild even if the current version is matching the regression versions '
                         '(see --version or --history).', dest='force_build',
                    action='store_true', default=False)
    b.add_argument('--no-build-deps',
                    help='Do not build the last version of some dependencies, use the currently compiled one',
                   dest='no_build_deps',
                    action=ExtendAction,default=[],nargs='+')
    b.add_argument('--ignore-deps',
                    help='Do not use the specified dependencies, find binaries in the current path instead',
                   dest='ignore_deps',
                    action=ExtendAction,default=[],nargs='+')
    b.add_argument('--force-build-deps',
                    help='Force to rebuild some dependencies', dest='force_build_deps',
                   action=ExtendAction, default=[], nargs='+')
    return b

nodePattern = regex.compile(
    "(?P<role>[a-zA-Z0-9]+)=(:?(?P<user>[a-zA-Z0-9]+)@)?(?P<addr>[a-zA-Z0-9.-]+)(:?[:](?P<path>[a-zA-Z0-9_./~-]+))?")
roles = {}


def nodes_for_role(role, self_role=None, self_node=None, default_role_map={}):
    if role is None or role == '':
        role = 'default'
    if role == 'self':
        if self_role:
            role = self_role
            if self_node:
                return [self_node]
        else:
            raise Exception("Using self without a role context. Usually, this happens when self is used in a %file")
    if role not in roles:
        if role in default_role_map:
            role = default_role_map[role]
    return roles.get(role, roles['default'])


def executor(role, default_role_map):
    """
    Return the executor for a given role as associated by the cluster configuration
    :param role: A role name
    :return: The executor
    """
    return nodes_for_role(role, default_role_map)[0].executor


def set_args(args):
    sys.modules[__name__].options = args
    sys.modules[__name__].cwd = os.getcwd()

def parse_nodes(args):
    set_args(args)

    #other random stuffs to do
    if not options.build_folder is None:
        if not os.access(options.build_folder, os.W_OK):
            raise Exception("The provided build path is not writeable or does not exists : %s!" % options.build_folder)
        options._build_path = options.build_folder
    else:
        options._build_path = npf_writeable_root_path()+'/build/'

    if type(options.use_last) is not int:
        if options.use_last:
            options.use_last = 100

    if not os.path.exists(experiment_path()):
        raise Exception("The experiment root '%s' is not accessible ! Please explicitely define it with --experiment-path, and ensure that directory is writable !" % experiment_path())

    if not os.path.isabs(options.experiment_folder):
        options.experiment_folder = os.path.abspath(options.experiment_folder)

    # Create the test file
    os.close(os.open(experiment_path() + ".access_test" , os.O_CREAT))
    local = Node.makeLocal(options)
    #Delete the test file
    os.unlink(experiment_path() + ".access_test")

    roles['default'] = [local]

    options.search_path = set(options.search_path)
    for t in [options.test_files]:
        options.search_path.add(os.path.dirname(t))

    for val in options.cluster:

        # Create the test file
        os.close(os.open(experiment_path() + ".access_test" , os.O_CREAT))

        variables : list[str] = val.split(',')
        if len(variables) == 0:
            raise Exception("Bad definition of cluster parameter : %s" % variables)
        mapping: str =variables[0].strip()
        match = nodePattern.match(mapping)
        if not match:
            raise Exception("Bad definition of node : %s" % mapping)

        path = match.group('path')

        del variables[0]

        nfs = None
        assert isinstance(variables, list)
        for opts in variables:
            assert isinstance(opts, str)
            var,val = opts.split('=')
            if var == "nfs":
                nfs = int(val)
            elif var == "path":
                path = val
            else:
                continue
            variables.remove(opts)

        if match.group('addr') == 'localhost':
            node = local
        else:
            node = Node.makeSSH(user=match.group('user'), addr=match.group('addr'), path=path,
                            options=options, nfs=nfs)
        role = match.group('role')
        if role in roles:
            roles[role].append(node)
            print("Role %s has multiple nodes. The role will be executed by multiple machines. If this is not intended, fix your --cluster option." % role)
        else:
            roles[role] = [node]

        for opts in variables:
            var,val = opts.split('=')
            if var == 'nic':
                node.active_nics = [ int(v) for v in val.split('+') ]
            elif var == "multi":
                node.multi = int(val)
            elif var == "mode":
                node.mode = val
            else:
                raise Exception("Unknown cluster variable : %s" % var)

        #Delete the test file if it still exists (if the remote is the local machine, it won't)
        if os.path.exists(experiment_path() + ".access_test"):
            os.unlink(experiment_path() + ".access_test")

def parse_variables(args_variables, tags, sec) -> Dict:
    variables = {}
    for variable in args_variables:
        var, val, assign = sec.parse_variable(variable,tags)
        if var:
            val.assign = assign
            variables[var] = val
    return variables


def override(args, tests):
    for test in tests:
        overriden_variables = parse_variables(args.variables, test.tags, test.variables)
        overriden_config = parse_variables(args.config, test.tags, test.config)
        test.variables.override_all(overriden_variables)
        test.config.override_all(overriden_config)
    return tests


def npf_root_path():
    # Return the path to NPF root
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

def npf_writeable_root_path():
    path = npf_root_path()
    if not os.access(path, os.W_OK):
        return experiment_path()
    else:
        return path

def experiment_path():
    # Return the path to NPF experiment folder
    options = sys.modules[__name__].options
    return os.path.join(options.experiment_folder,'')

def cwd_path():
    # Return the path to where NPF was first executed
    return sys.modules[__name__].cwd

def get_build_path():
    assert(options._build_path)
    return options._build_path

def from_experiment_path(path):
    # Returns the path under NPF root if it is not absolute
    if (os.path.isabs(path)):
        return path
    else:
        return (experiment_path() if os.path.isabs(experiment_path()) else os.path.abspath(experiment_path())) + os.sep + path

def find_local(path, critical: bool = False, suppl: List = None):
    if os.path.exists(path):
        return path

    searched = [npf_root_path(), '.', experiment_path()] + list(sys.modules[__name__].options.search_path) + (suppl if suppl else [])
    for a in searched:
        p = a + os.sep + path
        if os.path.exists(p):
            return p
    if critical:
        raise FileNotFoundError("Could not find file %s, locations searched :\n%s" %
                (path,
                    "\n".join(searched)))
    return path

def splitpath(hint):
    if hint is None:
        hint = "results"
    dirname, c_filename = os.path.split(hint)
    if c_filename == '':
        basename = ''
        ext = ''
    else:
        basename, ext = os.path.splitext(c_filename)
        if not ext and basename.startswith('.'):
            ext = basename
            basename = ''
    return dirname, basename, ext

def build_filename(test, build, hint, variables, def_ext, type_str='', show_serie=False, suffix='', force_ext = False, data_folder = False, prefix=None):
    var_str = get_valid_filename('_'.join(
        ["%s=%s" % (k, (val[1] if type(val) is tuple else val)) for k, val in sorted(variables.items()) if val]))

    if hint is None:
        if data_folder:
            path = build.result_path(test.filename, def_ext, folder = var_str + (('-' if var_str else '') + type_str if type_str else ''), prefix=prefix, suffix = ('-' + suffix if suffix else '') + ('-' + get_valid_filename(build.pretty_name()) if show_serie else ''))
        else:
            path = build.result_path(test.filename, def_ext, suffix=('-' + suffix if suffix else '') + var_str + ('-' + type_str if type_str else '') + ('-' + get_valid_filename(build.pretty_name()) if show_serie else '') , prefix=prefix)
    else:
        dirname, basename, ext = splitpath(hint)

        if ext is None or ext == '' or force_ext:
            ext = '.' + def_ext

        if basename is None or basename == '':
            basename = var_str

        if not data_folder:
            if prefix:
                basename = prefix + basename

            if not dirname or show_serie:
                basename = (get_valid_filename(build.pretty_name()) if show_serie else '') + basename
            path = (dirname + '/' if dirname else '') + basename + (
        ('-' if basename else '') + type_str if type_str else '') + ('' if not suffix else ("-" + suffix)) + ext
        else:
            if not dirname or show_serie:
                dirname = (dirname + "/" if dirname else '') + basename
            path = (dirname + '/' if dirname else '') + (prefix if prefix else '') + (get_valid_filename(build.pretty_name()) if show_serie else '') + (type_str if type_str else '') + ('' if not suffix else ("-" + suffix)) + ext

    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    return path


def build_output_filename(options, repo_list):
    if options.graph_filename is None:
        filename = 'compare/' + os.path.splitext(os.path.basename(options.test_files))[0] + '_' + '_'.join(
            ["%s" % repo.reponame for repo in repo_list]) + '.pdf'
    else:
        filename = options.graph_filename
    return filename

def replace_path(path, build = None):
    if build:
        if build.version is not None:
            path = path.replace('$version', build.version)
        for var,val in build.repo.env.items():
            path = path.replace('$'+var,val)
    return path

def parseBool(s):
    if type(s) is str and s.lower() == "false":
       return False
    else:
       return bool(s)

def parseUnit(u):
    r = re.match('([-]?)([0-9.]+)[ ]*([GMK]?)',u)
    if r != None:
        n = float(r.group(2))
        unit = r.group(3)
        if r.group(1) == "-":
            n = -n

        if unit is None or unit == '':
            return n
        if unit == 'G':
            n = n * 1000000000
        elif unit == 'M':
            n = n * 1000000
        elif unit == 'K':
            n = n * 1000
        else:
            raise Exception('%s is not a valid unit !' % unit)
        return n
    else:
        raise Exception("%s is not a number !" % u)

def all_num(l):
    for x in l:
        if type(x) is not int and type(x) is not Decimal and not isinstance(x, (np.floating, float)):
            return False
    return True
