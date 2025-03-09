from npf.models.units import get_numeric
from npf.models.variables.ListVariable import ListVariable
from npf.models.variables.variable import Variable
from npf.models.units import dtype


class ParentVariable(Variable):
    """Variable with just a value
    """
    def __init__(self, name, children):
        super().__init__(name)
        self.children = children


    def makeValues(self):
        l = []
        for c in self.children:
            l.extend(c.makeValues())
        return l

    def count(self):
        return sum([c.count() for c in self.children])

    def format(self):
        return self.name, [c.format() for c in self.children]

    def is_numeric(self):
        return all([c.is_numeric() for c in self.children])