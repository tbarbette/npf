import re

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
            return SimpleVariable(name,valuedata)
        result = re.match("\[(-?[0-9]+)([+]|[*])(-?[0-9]+)\]", valuedata)
        if result:
            return RangeVariable(name,int(result.group(1)),int(result.group(3)),result.group(2) == "*")
        raise Exception("Unkown variable type : " + valuedata)


class SimpleVariable:
    def __init__(self,name,value):
        self.name = name
        self.value = value

    def makeValues(self):
        return [{self.name : self.value}]

class RangeVariable:
    def __init__(self,name,valuestart,valueend,log):
        if (valuestart > valueend):
            self.a = valueend
            self.b = valuestart
        else:
            self.a = valuestart
            self.b = valueend
        self.name = name
        self.log = log

    def makeValues(self):
        vs=[]
        if self.log:
            i=self.a
            while i <= self.b:
                vs.append({self.name : i})
                if i==0:
                    i = 1
                else:
                    i*=2
        else:
            for i in range(self.a,self.b + 1):
                vs.append({self.name : i})
        return vs



