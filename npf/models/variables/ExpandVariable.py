from npf.models.variables.variable import Variable


class ExpandVariable(Variable):
    """ Create a list which expands a string with all possible value for the variable
        it contains like it would be in a script or file section.

        This can be seen as a variable that will interpret all variables inside it. For instance
        A=7
        B=EXPAND(SYSTEM-$A)

        --> A=7, B=SYSTEM-7

        However if A has multiple values, it will also create multiple B.

        This should be avoided. The good practice is to use a jinja template in the test itself.

        A=7

        %script@dut jinja
        echo "SYSTEM-{{A}}"
        """
    def __init__(self, name, value, vsection):
        super().__init__(name)
        self.values = vsection.replace_all(value)

    def makeValues(self):
        return self.values

    def count(self):
        return len(self.values)

    def format(self):
        return self.name, str

    def is_numeric(self):
        return False

    def __add__(self, other):
        v = []
        for ov in other.makeValues():
            for mv in self.values:
                v.append(mv + ov)
        self.values = v
        return self