from npf.models.variables.variable import Variable
from npf.tests.variable import aeval


class IfVariable(Variable):
    """Condition variable.

    This is deprecated, prefer to use conditions in the test itself using a jinja template.
    """
    def __init__(self, name, cond, a, b):
        super().__init__(name)
        self.cond = cond
        self.a = a
        self.b = b

    def makeValues(self):
        vs = []
        if aeval(self.cond):
            return [self.a]
        else:
            return [self.b]

    def count(self):
        return 1

    def format(self):
        return str

    def is_numeric(self):
        return False