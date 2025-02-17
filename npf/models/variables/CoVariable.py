from npf.models.variables.variable import Variable


from collections import OrderedDict


class CoVariable(Variable):
    """A serie of variable that should advance together.

    A=[1-10]
    B=[1-10]

    Normally that creates 100 combinations.
    """
    def __init__(self, name = "covariable"):
        super().__init__(name)
        self.vlist = OrderedDict()

    def makeValues(self):
        vs = [OrderedDict() for i in range(self.count())]
        vals = []
        for i,(var,val) in enumerate(self.vlist.items()):
            vals.append(val.makeValues())
        for i in range(self.count()):
            for j,var in enumerate(self.vlist.keys()):
                vs[i][var] = vals[j][i]
        return vs

    def count(self):
        if len(self.vlist) == 0:
            return 1
        return min([v.count() for k,v in self.vlist.items()])

    def format(self):
        k = []
        v = []
        for var,val in self.vlist.items():
            K,V = val.format()
            k.append(K)
            v.append(V)
        return k,v

    def is_numeric(self):
        return False