from npf.models.units import is_bool, is_integer, is_numeric
from npf.models.variables.variable import Variable
from npf.models.units import dtype


class ListVariable(Variable):
    """A variable with a list of elements
    """
    def __init__(self, name, l):
        super().__init__(name)
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

    def __add__(self,other):
        self.lvalues.extend(other.lvalues)
        return self

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
        t = dtype(self.lvalues[0])
        if t is int and is_bool(self.lvalues[0]):
            unique = list(set(self.lvalues))
            if len(unique) == 2 and all([int(u) in (0, 1) for u in unique]):
                return self.name, bool
            elif len(unique) == 1 and (unique[0] == 'true' or unique[0] == 'false'):
                return self.name, bool
        return self.name, t

    def is_numeric(self):
        return self.all_num

    def pop(self, item):
        if item in self.lvalues:
            self.lvalues.remove(item)
        return self