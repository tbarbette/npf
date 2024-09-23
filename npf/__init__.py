import os

from typing import Dict

import regex

from npf.cluster.node import Node
from npf.globals import experiment_path, npf_root_path, roles, set_args, get_options
from npf.osutils import get_valid_filename

nodePattern = regex.compile(
    "(?P<role>[a-zA-Z0-9]+)=(:?(?P<user>[a-zA-Z0-9]+)@)?(?P<addr>[a-zA-Z0-9.-]+)(:?[:](?P<path>[a-zA-Z0-9_./~-]+))?")

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

def initialize(args):
    set_args(args)

    #other random stuffs to do
    if not get_options().build_folder is None:
        if not os.access(get_options().build_folder, os.W_OK):
            raise Exception("The provided build path is not writeable or does not exists : %s!" % get_options().build_folder)
        get_options()._build_path = get_options().build_folder
    else:
        get_options()._build_path = npf_writeable_root_path()+'/build/'

    if type(get_options().use_last) is not int:
        if get_options().use_last:
            get_options().use_last = 100

    if not os.path.exists(experiment_path()):
        raise Exception("The experiment root '%s' is not accessible ! Please explicitely define it with --experiment-path, and ensure that directory is writable !" % experiment_path())

    if not os.path.isabs(get_options().experiment_folder):
        get_options().experiment_folder = os.path.abspath(get_options().experiment_folder)


    get_options().search_path = set(get_options().search_path)
    for t in [get_options().test_files]:
        get_options().search_path.add(os.path.dirname(t))

def create_local():
    # Create the test file
    os.close(os.open(experiment_path() + ".access_test" , os.O_CREAT))
    local = Node.makeLocal()
    #Delete the test file
    os.unlink(experiment_path() + ".access_test")
    roles['default'] = [local]
    return local

def parse_nodes(args):
    initialize(args)
    local = create_local()

    for val in get_options().cluster:

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
            node = Node.makeSSH(user=match.group('user'), addr=match.group('addr'), path=path, nfs=nfs)
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


def npf_writeable_root_path():
    path = npf_root_path()
    if not os.access(path, os.W_OK):
        return experiment_path()
    else:
        return path

def from_experiment_path(path):
    # Returns the path under NPF root if it is not absolute
    if (os.path.isabs(path)):
        return path
    else:
        return (experiment_path() if os.path.isabs(experiment_path()) else os.path.abspath(experiment_path())) + os.sep + path

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


def build_output_filename(repo_list):
    if get_options().graph_filename is None:
        filename = 'compare/' + os.path.splitext(os.path.basename(get_options().test_files))[0] + '_' + '_'.join(
            ["%s" % repo.reponame for repo in repo_list]) + '.pdf'
    else:
        filename = get_options().graph_filename
    return filename
