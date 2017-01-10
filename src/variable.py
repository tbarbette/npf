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
        return int if is_integer(v) else float
    else:
        return str

class VariableFactory:
    @staticmethod
    def build(name, valuedata, vsection):
        if is_numeric(valuedata):
            v = float(valuedata)
            if (v.is_integer()):
                v = int(v)
            return SimpleVariable(name, v)
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
        if result:
            return ProductVariable(name, vsection.vlist[result.group(1)].makeValues(),
                                   vsection.vlist[result.group(2)].makeValues())

        return SimpleVariable(name, valuedata)


# raise Exception("Unkown variable type : " + valuedata)

class ProductVariable:
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


class ExpandVariable:
    def __init__(self, name, value, vsection):
        self.values = vsection.replace_all(value)

    def makeValues(self):
        return self.values

    def count(self):
        return len(self.values)

    def format(self):
        return str


class SimpleVariable:
    def __init__(self, name, value):
        self.value = value

    def makeValues(self):
        return [self.value]

    def count(self):
        return 1

    def format(self):
        return dtype(self.value)



class ListVariable:
    def __init__(self, name, l):
        self.lvalues = [int(x) if is_integer(x) else float(x) if is_numeric(x) else x for x in l]

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
        return dtype(self.lvalues[0])


class DictVariable:
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


class RangeVariable:
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
