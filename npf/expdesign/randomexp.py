import random
from npf.expdesign.fullexp import FullVariableExpander


class RandomVariableExpander(FullVariableExpander):
    """Same as BruteVariableExpander but shuffle the series to test"""

    def __init__(self, vlist, overriden, seed, n_iter):
        super().__init__(vlist, overriden)

        random.seed(seed)
        random.shuffle(self.expanded)
        if n_iter > 0:
            self.expanded = self.expanded[:n_iter]
