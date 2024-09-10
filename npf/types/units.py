import numpy as np


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


