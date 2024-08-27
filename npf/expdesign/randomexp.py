from random import shuffle

from npf.expdesign.fullexp import FullVariableExpander


class RandomVariableExpander(FullVariableExpander):
    """Same as BruteVariableExpander but shuffle the series to test"""

    def __init__(self, vlist, overriden):
        super().__init__(vlist, overriden)
        shuffle(self.expanded)
