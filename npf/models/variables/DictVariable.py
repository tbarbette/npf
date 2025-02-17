from npf.models.variables.variable import Variable
from npf.models.units import dtype


from collections import OrderedDict


class DictVariable(Variable):
    """A variable with a dictionnary of level:pretty name, where in the test "level" will be used but in display format "pretty name will be used"
    for instance `ZC={1:Zero-copy,0:Copy}`

    """
    def __init__(self, name, data):
        super().__init__(name)
        if type(data) is dict:
            self.vdict = data
        else:
            self.vdict = OrderedDict()
            for g in data:
                d = g.split(':')
                self.vdict[d[0]] = d[1]

    def makeValues(self):
        return [(k, v) for k, v in self.vdict.items()]

    def count(self):
        return len(self.vdict)

    def format(self):
        k, v = next(self.vdict.items().__iter__())
        return self.name, dtype(v)

    def is_numeric(self):
        k, v = next(self.vdict.items().__iter__())
        return dtype(v) != str

    def __add__(self, other):
        self.vdict.update(other.vdict)
        return self

    def pop(self, item):
        if item in self.vdict:
            del self.vdict[item]
        return self