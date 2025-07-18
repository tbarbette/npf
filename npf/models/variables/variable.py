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
    ALLOWED_NODE_VARS = 'path|user|addr|tags|nfs|arch|port|identityfile'
    NICREF_REGEX = r'(?P<role>[a-z0-9]+)[:](:?(?P<nic_idx>[0-9]+)[:](?P<type>' + NIC.TYPES + '+)|(?P<node>'+ALLOWED_NODE_VARS+'|ip|ip6|multi|mode|node))'
    VARIABLE_NICREF_REGEX = r'(?<!\\)[$][{]' + NICREF_REGEX + '[}]'