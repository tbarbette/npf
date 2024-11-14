from typing import Dict
from npf import npf_writeable_root_path
from npf.cluster.factory import create_local, nodePattern
from npf.cluster.node import Node
from npf.globals import experiment_path, get_options, roles, set_args


import os


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