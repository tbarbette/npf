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

class VariableFactory:
    @staticmethod
    def build(name,valuedata):
        if is_numeric(valuedata):
            v = float(valuedata)
            if (v.is_integer()):
                v = int(v)
            return SimpleVariable(name,v)
        result = re.match("\[(-?[0-9]+)([+]|[*])(-?[0-9]+)\]", valuedata)
        if result:
            return RangeVariable(name,int(result.group(1)),int(result.group(3)),result.group(2) == "*")
        result = regex.match("\{([^,:]+:[^,:]+)(?:(?:,)([^,:]+:[^,:]+))*\}", valuedata)
        if result:
            return DictVariable(name,result.captures(1) + result.captures(2))

        result = regex.match("\{([^,]+)(?:(?:,)([^,])+)*}", valuedata)
        if result:
            return ListVariable(name,result.captures(1) + result.captures(2))
        return SimpleVariable(name,valuedata)

#        raise Exception("Unkown variable type : " + valuedata)


class SimpleVariable:
    def __init__(self,name,value):
        self.value = value

    def makeValues(self):
        return [self.value]

    def count(self):
        return 1

class ListVariable:
    def __init__(self,name,l):
        self.lvalues = l

    def makeValues(self):
        vs=[]
        for v in self.lvalues:
            if (v is None):
                continue
            vs.append(v)
        return vs

    def count(self):
        return len(self.lvalues)

class DictVariable:
    def __init__(self,name,data):
        self.vdict = {}
        for g in data:
            d = g.split(':')
            self.vdict[d[0]] = d[1]

    def makeValues(self):
        return [self.vdict]

    def count(self):
        return len(self.vdict)

class RangeVariable:
    def __init__(self,name,valuestart,valueend,log):
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
        vs=[]
        if self.log:
            i=self.a
            while i <= self.b:
                vs.append(i)
                if i==0:
                    i = 1
                else:
                    i*=2
        else:
            for i in range(self.a,self.b + 1):
                vs.append(i)
        return vs
