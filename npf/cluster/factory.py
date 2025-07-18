import os
import regex
from npf.cluster.node import Node
from npf.globals import experiment_path, roles


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


nodePattern = regex.compile(
    "(?P<role>[a-zA-Z0-9]+)=(:?(?P<user>[a-zA-Z0-9]+)@)?(?P<addr>[a-zA-Z0-9._-]+)(:?[:](?P<path>[a-zA-Z0-9_./~-]+))?")


def executor(role, default_role_map):
    """
    Return the executor for a given role as associated by the cluster configuration
    :param role: A role name
    :return: The executor
    """
    return nodes_for_role(role, default_role_map)[0].executor


def create_local():
    # Create the test file
    os.close(os.open(experiment_path() + ".access_test" , os.O_CREAT))
    local = Node.makeLocal()
    #Delete the test file
    os.unlink(experiment_path() + ".access_test")
    roles['default'] = [local]
    return local