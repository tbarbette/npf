from npf.models.units import is_numeric
from npf.models.variables.variable import Variable


class HeadVariable(Variable):
    """DEPRECATED, use jinja instead.
    """
    def __init__(self, name, nums, values, join = None):
        super().__init__(name)
        self.values = values
        if not is_numeric(nums):
            raise Exception("%s is not a number!" % nums)
        self.nums = nums
        self.join = join if join else "\n"


    def makeValues(self):
        if self.nums == 0:
            return ['']
        vs = []
        i = int(self.nums)
        if type(i) is str:
            i = int(i.strip())
        vs.append((self.join.join(self.values[:i]), i))
        return vs

    def count(self):
        return sum(self.nums) if len(self.nums) > 0 else 1

    def format(self):
        return self.name, str

    def is_numeric(self):
        return False