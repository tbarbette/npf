from npf.models.variables.variable import Variable


import random


class RandomVariable(Variable):
    """
    Generate a random number between 2 integers.

    This should generally be avoided.
    """
    def __init__(self, name, a, b):
        super().__init__(name)
        self.a = int(a.strip())
        self.b = int(b.strip())

    def makeValues(self):
        return [random.randint(self.a, self.b)]


    def count(self):
        return 1

    def format(self):
        return self.name, int

    def is_numeric(self):
        return True