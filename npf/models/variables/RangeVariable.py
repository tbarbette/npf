from npf.models.units import is_integer
from npf.models.variables.variable import Variable
from npf.tests.variable import FromFileVariable


class RangeVariable(Variable):
    def __init__(self, name, valuestart, valueend, log = False, step = None, force_int = False):
        super().__init__(name)

        if is_integer(valuestart) and is_integer(valueend):
            valuestart=int(valuestart)
            valueend=int(valueend)
        else:
            valuestart=float(valuestart)
            valueend=float(valueend)
        if valuestart > valueend:
            self.a = valueend
            self.b = valuestart
        else:
            self.a = valuestart
            self.b = valueend
        self.log = log
        if step is None:
            if log:
                self.step = 2
            else:
                self.step = 1
        else:
            self.step = step
        self.force_int = force_int

    def count(self):
        """todo: think"""
        if self.step == "":
            return len(FromFileVariable.getVals(self))
        else:
            if self.log:
                return len(self.makeValues())
            else:
                return int(((self.b-self.a) / self.step) + 1)


    def makeValues(self):
            #Experimental design
            if self.step == "":
                vs =  self.a + (self.b-self.a) * FromFileVariable.getVals(self)
            else:
                vs = []
                i = self.a
                while i <= self.b:
                    vs.append(i)
                    if i == self.b:
                        break
                    if i == 0 and self.log:
                        if self.b > 0:
                            i = 1
                        else:
                            i = -1
                    else:
                        if self.log:
                            i *= self.step
                        else:
                            i += self.step
                if i > self.b:
                    vs.append(self.b)
            return [int(v) for v in vs] if self.force_int else vs

    def format(self):
        return self.name, int

    def is_numeric(self):
        return True