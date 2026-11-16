from npf.cluster.nic import NIC


class Variable:
    def __init__(self, name):
        self.assign = '='
        self.is_default = False
        self.name = name

    NAME_REGEX = r'[a-zA-Z0-9._-]+'
    TAGS_REGEX = r'[a-zA-Z0-9._,|!-]+'
    VALUE_REGEX = r'[a-zA-Z0-9._/,{}^$-:]+'
    VARIABLE_REGEX = r'(?<!\\)[$](' \
                     r'[{](?P<varname_in>' + NAME_REGEX + ')[}]|' \
                     r'(?P<varname_sp>' + NAME_REGEX + ')(?=}|[^a-zA-Z0-9_]|$))'
    MATH_REGEX = r'(?P<prefix>\\)?[$][(][(](?P<expr>.*?)[)][)]'
    # The keys of a .node file (cluster/NAME.node), documented in cluster.rst of npf-docs, besides env=KEY=VALUE and
    # the NICs (N:TYPE=VALUE, see NIC.TYPES). Scripts read them with ${ROLE:KEY}.
    #   path          Folder of NPF's experiment on the node
    #   user, addr, port, identityfile   How to connect to the node with SSH
    #   nfs           0 when the experiment folder is not shared with the node: NPF then sends the files it needs
    #   tags, arch    Accepted, but not used
    ALLOWED_NODE_VARS = 'path|user|addr|tags|nfs|arch|port|identityfile'
    NICREF_REGEX = r'(?P<role>[a-z0-9]+)[:](:?(?P<nic_idx>[0-9]+)[:](?P<type>' + NIC.TYPES + '+)|(?P<node>'+ALLOWED_NODE_VARS+'|ip|ip6|multi|mode|node))'
    VARIABLE_NICREF_REGEX = r'(?<!\\)[$][{]' + NICREF_REGEX + '[}]'