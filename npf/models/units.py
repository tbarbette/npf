import numpy as np
import re

from decimal import Decimal



def all_num(l):
    for x in l:
        if type(x) is not int and type(x) is not Decimal and not isinstance(x, (np.floating, float)):
            return False
    return True

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


def parseBool(s):
    if type(s) is str and s.lower() == "false":
       return False
    else:
       return bool(s)


def is_numeric(s):
    try:
        val = float(s)
        return True
    except TypeError:
        return False
    except ValueError:
        return False


def is_integer(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


def get_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        if val == 0: return False
        if val == 1: return True
        raise ValueError("Number %d is not a bool" % val)

    if val == "0" or val.lower() == "f" or val.lower() == "false":
        return False
    if val == "1" or val.lower() == "t" or val.lower() == "true":
        return True
    raise ValueError("%s is not a bool" % val)


def is_bool(s):
    try:
        if type(s) is list:
            return False
        get_bool(s)
        return True
    except ValueError:
        return False


def get_numeric(data):
    if is_numeric(data):
        v = float(data)
        if v.is_integer():
            v = int(v)
        return v
    else:
        return data


def numericable(l):
    for x in l:
        if not is_numeric(x):
            return False
    return True


def numeric_dict(d):
        for k, v in d.items():
            if type(v) is tuple:
                if is_numeric(v[1]):
                    d[k] = tuple(v[0],get_numeric(v[1]))
            else:
                if is_numeric(v):
                    d[k] = get_numeric(v)
        return d


def dtype(v):
    if is_numeric(v):
        if is_integer(v):
            return int
        else:
            return float
    else:
        return str


