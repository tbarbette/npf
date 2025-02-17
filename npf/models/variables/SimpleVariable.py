from npf.models.units import get_numeric
from npf.models.variables.ListVariable import ListVariable
from npf.models.variables.variable import Variable
from npf.models.units import dtype


class SimpleVariable(Variable):
    """Variable with just a value
    """
    def __init__(self, name, value):
        super().__init__(name)
        self.value = get_numeric(value)

    def makeValues(self):
        return [self.value]

    def count(self):
        return 1

    def format(self):
        return self.name, dtype(self.value)

    def is_numeric(self):
        return self.format() != str

    def __add__(self, other):
        self.value += other.makeValues()[0]
        return self

    def pop(self, item):
        if self.value == item:
            return ListVariable(None, [])
        else:
            return self