from collections import OrderedDict

from npf.expdesign.fullexp import FullVariableExpander
from itertools import chain


class ChildIterator():
    def __init__(self, children_it):
        self.children_it = children_it
        self.current = next(children_it)
        self.current_idx = 0
        self.current_it = iter(self.current)

    def __next__(self):
        try:
            return next(self.current_it)
        except StopIteration:
            self.current = next(self.children_it)
            self.current_idx += 1
            self.current_it = iter(self.current)
            return self.__next__()
        

class MultiVariableExpander(FullVariableExpander):
    """Only explore max and min value of each dimension"""

    def __init__(self, children):      
        self.children = children

    def __iter__(self):
        self.it = ChildIterator(self.children.__iter__())
        return self.it

    def __next__(self):
        return self.it.__next__()
    
    def __len__(self):
        return sum([len(c) for c in self.children])

    def strlen(self):
        return self.it.current.strlen() + f" of exploration {self.it.current_idx + 1}/{len(self.children)}"