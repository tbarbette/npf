from argparse import ArgumentParser
import argparse



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

    v.add_argument('--no-colors', help='Do not use terminal colors', dest='color', action='store_false', default=True)
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
    o.add_argument('--web',
                   help='Generate interactive graphs in a *.html file format')
    o.add_argument('--notebook', '--nb', dest='notebook_path',
                   help='Generate a Jupyter Notebook that plots the data (*.ipynb file format).')
    o.add_argument('--template-nb', dest='template_nb_path',
                   help='Use a custom Jupyter Notebook as template.',
                   default="npf/output/notebook/template.ipynb")
    o.add_argument('--nb-kernel', dest='nb_kernel',
                   help='Specify which kernel to use for executing the Jupyter Notebook.',
                   default="python3")
    o.add_argument('--update-nb',
                   help='If the notebook already exists, try to update the experiment data (cell containing "data = ").', action='store_true',
                   default=False)
    o.add_argument('--force-nb',
                   help='If the notebook already exists, overwrite it (the previous data and code will be lost).', action='store_true',
                   default=False)
    o.add_argument('--disable-nb-exec', dest='execute_nb',
                   help='By default the output notebook is executed, this option disables that feature.', action='store_false',
                   default=True)
    o.add_argument('--output',
                   help='Output data to CSV files, one per result type. By default it prints the variable value as first column and the second column is the mean of all runs. Check --output-columns to change this behavior.', dest='output', type=str, nargs='?', const='graph', default=None)
    o.add_argument('--output-columns', dest='output_columns', type=str, nargs='+', default=['x', 'mean'],
                    help='Columns to print in each --output CSV files. By default x mean. Valid values are mean/average, min, max, perc[0-9]+, med/median/perc50, std, nres/n, first, last, all. Check the documentation for details.')
    o.add_argument('--single-output', '--pandas', '--csv', metavar='pandas_filename', type=str, default=None, dest='pandas_filename',
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

    g.add_argument('--keep-parameters', dest='remove_parameters', action='store_false', default=True, help="Do not remove parameters from the dataset. By default, variables which have the same values for the entire dataset are removed before the dataset is passed to output modules (CSV, graphs, web, ...). This option keeps them.")

    g.add_argument('--no-transform', dest='do_transform', action='store_false', default=True, help="Forbid automatic transformation of data such as extracting a variable as a serie")

    g.add_argument('--graph-select-max', dest='graph_select_max', type=int, default=None, help="Only keep the first X results for each run.")

    g.add_argument('--graph-dpi', dest='graph_dpi', type=int, default=300)

    g.add_argument('--no-graph-time', dest='do_time', action='store_false', default=True, help="Do not plot time series graphs")

    g.add_argument('--no-graph', dest='no_graph', action='store_true', default=False, help="Do not plot graphs")

    g.add_argument('--iterative', dest='iterative', action='store_true', default=False,
                   help='Graph after each results, allowing to get a faster glimpse at the results')

    g.add_argument('--onefirst', dest='onefirst', action='store_true', default=False,
                   help='Do a first pass with one run per variables, then do the last runs')


    s = parser.add_argument_group('Statistics options')
    s.add_argument('--statistics',
                   help='Give some statistics output. Accepts a list of outputs names to give statistics about, or will try to find the best outputs if no value is provided.',
                   dest='statistics', default=False,
                   action=ArgListOrTrueAction)
    s.add_argument('--statistics-maxdepth',
                   help='Max depth of learning tree', dest='statistics_maxdepth', type=int, default=None)
    s.add_argument('--statistics-maxmetrics',
                   help='Maximum number of metrics to give, ignored if statistics has some arguments.', dest='statistics_maxmetrics', type=int, default=3)
    s.add_argument('--statistics-filename',
                   help='Output of learning tree', dest='statistics_filename', type=str, default=None)

    return g


class ExtendAction(argparse.Action):
    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        super(ExtendAction, self).__init__(option_strings, dest, nargs, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, getattr(namespace, self.dest) + values)


class ArgListOrTrueAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        if "nargs" in kwargs:
            raise ValueError("nargs cannot be set for ArgListOrTrueAction, it is always *")
        super().__init__(option_strings, dest, nargs='*', **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if values is None:
            setattr(namespace, self.dest, True)
        else:
            current_values = getattr(namespace, self.dest, [])
            if type(current_values) is bool:
                current_values = []
            setattr(namespace, self.dest, current_values + values)


def add_testing_options(parser: ArgumentParser, regression: bool = False):
    t = parser.add_argument_group('Testing options')
    tf = t.add_mutually_exclusive_group()
    t.add_argument('--no-test',
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
                    action="store_true",
                    default=True,
                    help='DEPRECATED. Now the default is to ignore the cache. Use --cache instead.')
    tf.add_argument('--cache',
                    help='Use data from the previous experiments. If the same combination of variables was already tried, do not re-run the experiment but keep results. This allows fast exploration of the parameter space.',
                    dest='force_retest', action='store_false',
                    default=True)
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
                   help='Do not delete test folder with temporary files. If a value is provided, each test result will be moved to that folder. The folder path may contain variable values to do the replacement.',
                   dest='preserve_temp',
                   nargs='?',
                   const=True,
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

    t.add_argument('--env', metavar='list of variables', dest='keep_env', type=str, nargs='+', help='list of environment variables to pass in scripts', default=[], action=ExtendAction)

    t.add_argument('--test', '--test', '--npf', dest='test_files', metavar='path or test', type=str, nargs='?', default='tests',
                   help='script or script folder. Default is tests')


    t.add_argument('--build-folder', '--build-path', metavar='path', type=str, default=None, dest='build_folder', help='Set where dependencies would be built. Defaults to npf\'s folder itself, so dependencies are shared between test scripts.')

    t.add_argument('--experiment-folder', '--experiment-path', metavar='path', type=str, default="./", dest='experiment_folder', help='Where to create temporary files and execute tests from. Default to local directory. Tests will always be executed from a temporary-made folder inside that path. Beware if you do not have a similar NFS/SSHFS based directory identical on all nodes, the "path" argument of the cluster file must match this repository, same as the build path relative to that directory.')

    t.add_argument('--search-path', metavar='path', type=str, default=[], nargs='+', dest='search_path', help='Search for various files in this directories too (such as the parent of your own repo, cluster or modules folder)')
    t.add_argument('--no-mp', dest='allow_mp', action='store_false',
                   default=True, help='Run tests in the same thread. If there is multiple script, they will run '
                                      'one after the other, hence breaking most of the tests.')
    t.add_argument('--exp-design', type=str, default="full", dest="design", help="Experimental design method")
    t.add_argument('--spacefill', type=str, default="matrix.csv", dest="spacefill", help="The path towards the space filling values matrix")
    t.add_argument('--rand-env', type=int, default=65536, dest="rand_env", help="Add an environmental variable of a random size to prevent bias")

    c = parser.add_argument_group('Cluster options')
    c.add_argument('--cluster', metavar='role=user@address:path [...]', type=str, nargs='*', default=[],
                   help='role to node mapping for remote execution of tests. The format is role=address[,option=value,...] . Address can be an address or a file in cluster/address.node describing supplementary parameters for the node.')
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
