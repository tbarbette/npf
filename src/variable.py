import re
import regex


def is_numeric(s):
    try:
        val = float(s)
    except TypeError:
        return False
    except ValueError:
        return False
    return True


def is_integer(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

def is_bool(s):
    try:
        bool(s)
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

def dtype(v):
    if is_numeric(v):
        if is_integer(v):
            return int
        else:
            return float
    else:
        return str

class VariableFactory:
    @staticmethod
    def build(name, valuedata, vsection = None):
        result = re.match("\[(-?[0-9]+)([+-]|[*])(-?[0-9]+)\]", valuedata)
        if result:
            return RangeVariable(name, int(result.group(1)), int(result.group(3)), result.group(2) == "*")
        result = regex.match("\{([^,:]+:[^,:]+)(?:(?:,)([^,:]+:[^,:]+))*\}", valuedata)
        if result:
            return DictVariable(name, result.captures(1) + result.captures(2))

        result = regex.match("\{([^,]+)(?:(?:,)([^,]+))*}", valuedata)
        if result:
            return ListVariable(name, result.captures(1) + result.captures(2))

        result = regex.match("EXPAND\((.*)\)", valuedata)
        if result:
            return ExpandVariable(name, result.group(1), vsection)

        result = regex.match("PRODUCT[ ]*\([ ]*\$([^,]+)[ ]*,[ ]*\$([^,]+)[ ]*\)", valuedata)
        if result and vsection:
            return ProductVariable(name, vsection.vlist[result.group(1)].makeValues(),
                                   vsection.vlist[result.group(2)].makeValues())

        return SimpleVariable(name, valuedata)


# raise Exception("Unkown variable type : " + valuedata)

class Variable:
    pass

class ProductVariable(Variable):
    def __init__(self, name, nums, values):
        self.values = values
        self.nums = nums
        self.join = "\n"

    def makeValues(self):
        vs = []
        for i in self.nums:
            vs.append((self.join.join(self.values[:i]), i))
        return vs

    def count(self):
        return sum(self.nums)

    def format(self):
        return str

    def is_numeric(self):
        return False


class ExpandVariable(Variable):
    def __init__(self, name, value, vsection):
        self.values = vsection.replace_all(value)

    def makeValues(self):
        return self.values

    def count(self):
        return len(self.values)

    def format(self):
        return str

    def is_numeric(self):
        return False


class SimpleVariable(Variable):
    def __init__(self, name, value):
        self.value = get_numeric(value)

    def makeValues(self):
        return [self.value]

    def count(self):
        return 1

    def format(self):
        return dtype(self.value)

    def is_numeric(self):
        return self.format() != str


class ListVariable(Variable):
    def __init__(self, name, l):
        all_num = True
        for x in l:
            if not is_numeric(x):
                all_num = False
                break
        if all_num:
            self.lvalues = [int(x) if is_integer(x) else float(x) if is_numeric(x) else x for x in l]
        else:
            self.lvalues = [str(x) for x in l]
        self.all_num = all_num

    def makeValues(self):
        vs = []
        for v in self.lvalues:
            if (v is None):
                continue
            vs.append(v)
        return vs

    def count(self):
        return len(self.lvalues)

    def format(self):
        t =  dtype(self.lvalues[0])
        if t is int and is_bool(self.lvalues[0]):
            unique = list(set(self.lvalues))
            if len(unique) == 2 and all([int(u) in (0,1) for u in unique]):
                return bool
            elif len(unique) == 1 and (unique[0] == 'true' or unique[0]=='false'):
                return bool
        return t

    def is_numeric(self):
        return self.all_num


class DictVariable(Variable):
    def __init__(self, name, data):
        self.vdict = {}
        for g in data:
            d = g.split(':')
            self.vdict[d[0]] = d[1]

    def makeValues(self):
        return [self.vdict]

    def count(self):
        return len(self.vdict)

    def format(self):
        k,v = next(self.vdict.items())
        return dtype(v)

    def is_numeric(self):
        return dtype(v) != str


class RangeVariable(Variable):
    def __init__(self, name, valuestart, valueend, log):
        if (valuestart > valueend):
            self.a = valueend
            self.b = valuestart
        else:
            self.a = valuestart
            self.b = valueend
        self.log = log

    def count(self):
        """todo: think"""
        return len(self.makeValues())

    def makeValues(self):
        vs = []
        if self.log:
            i = self.a
            while i <= self.b:
                vs.append(i)
                if i == 0:
                    i = 1
                else:
                    i *= 2
        else:
            for i in range(self.a, self.b + 1):
                vs.append(i)
        return vs

    def format(self):
        return int

    def is_numeric(self):
        return True
