import re
from collections import OrderedDict

import random
from asteval import Interpreter
import itertools
import numpy as np
import csv


import random

import npf.cluster.node
from npf.models.variables.variable import Variable
import npf.osutils
from npf.models.units import is_numeric
from npf.models.units import get_bool
from npf.models.units import get_numeric

def is_log(l):
    if len(l) < 3:
        return False

    for i in range(len(l)):
        if not is_numeric(l[i]):
            return False
        l[i] = get_numeric(l[i])

    i = 0
    if l[0] == 0:
        if l[1] != 1:
            return False
        else:
            i = 1
    n = l[i+1] / l[i]
    i = i+1 #1
    c = l[i]
    i = i + 1 #2

    for i in range(i,len(l)):
        c = c * n
        if l[i] != c:
            return False
    return n


def ae_product_range(a,b):
    return itertools.product(range(a),range(b))

def ae_rand(a,b):
    return random.randint(a,b)

aeval = Interpreter(usersyms ={'parseBool':get_bool,"randint":ae_rand,"productrange":ae_product_range,"chain":itertools.chain})


def replace_variables(v: dict, content: str, self_role=None, self_node=None, default_role_map={}, role_index = 0):
    """
    Replace all variable and nics references in content
    This is done in two step : variables first, then NICs reference so variable can be used in NIC references
    :param v: Dictionary of variables
    :param content: Text to change
    :param self_role: Role of the caller, that self reference in nic will map to
    :return: The text with reference to variables and nics replaced
    """

    def do_replace(match):
        varname = match.group('varname_sp') if match.group('varname_sp') is not None else match.group('varname_in')
        if varname in v:
            val = v[varname]
            return str(val[0] if type(val) is tuple else val)
        return match.group(0)

    content = re.sub(
        Variable.VARIABLE_REGEX,
        do_replace, content)

    def do_replace_nics(nic_match):
        varRole = nic_match.group('role')

        nodes = npf.cluster.factory.nodes_for_role(varRole, self_role, self_node, default_role_map)
        nodeidx = role_index % len(nodes)
        if nic_match.groupdict()['node']:
            t = str(nic_match.group('node'))
            if t == "node":
                return str(len(nodes))
            v = getattr(nodes[nodeidx], t)
            if v is None:
                if t == "multi":
                    return "1"
                else:
                    raise Exception("Unknown node variable %s" % t)
            else:
                return str(v)
        else:
            nic = nodes[nodeidx].get_nic(int(nic_match.group('nic_idx')))
            return str(nic[nic_match.group('type')])

    content = re.sub(
        Variable.VARIABLE_NICREF_REGEX,
        do_replace_nics, content)



    def do_replace_math(match):

        prefix = match.group('prefix')
        expr = match.group('expr').strip()
        expr = re.sub(
            Variable.VARIABLE_REGEX,
            do_replace, expr)
        if prefix:
            return "$((" + str(expr) + "))"
        else:
            return str(aeval(expr))

    content = re.sub(
        Variable.MATH_REGEX,
        do_replace_math, content)
    return content



# raise Exception("Unkown variable type : " + valuedata)

class FromFileVariable:
    """Deprecated. Use the experimental design system instead of drawing from a file.
    """
    matrix = None
    varmap = OrderedDict()

    @classmethod
    def getVals(cls, v:Variable):
        if cls.matrix is None:
            cls.load()
        if v.name not in cls.varmap:
            cls.varmap[v.name] = len(cls.varmap)
        return cls.matrix[cls.varmap[v.name]]

    @classmethod
    def load(cls):
        path = npf.osutils.find_local(npf.globals.options.spacefill)
        assert path is not None

        with open(path) as fd:
            csvreader = csv.reader(fd)
            data = [i for i in csvreader]
        
        FromFileVariable.matrix = np.array([[float(j) for j in i] for i in data])

        # TODO: assert that the number of rows of the matrix is sufficient for all the values of the experimental design variables

# For each value N of nums, generate a variable with the first N element of values
