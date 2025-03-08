from collections import OrderedDict
import random
from npf.expdesign.fullexp import FullVariableExpander
from skopt.sampler import Lhs
from skopt.space import Space

class LHSVariableExpander(FullVariableExpander):
    """Same as BruteVariableExpander but uses LHS to explore only some point"""

    def __init__(self, vlist, overriden, seed, n_iter):
        self.n_iter = n_iter
        v_space = []
        r_space = []
        self.expanded = []
        ks = []
        uniques = OrderedDict()
        self.orig_n = 1 #Original dimension size
        for k, v in vlist.items():
            if k in overriden:
                continue

            l = v.makeValues()
            if len(l) == 1:
                uniques[k] = l[0]
                continue

            self.orig_n *=len(l)
            r_space.append(l)

            v_space.append( (0,len(l)-1) )
            ks.append(k)

        space = Space(v_space)

        lhs = Lhs(criterion="maximin", iterations=10000)
        x = lhs.generate(space.dimensions, n_samples=n_iter, random_state=seed)
        for line in x:
            d = OrderedDict()
            for i,v in enumerate(line):
                d[ks[i]] =  r_space[i][v]
            d.update(uniques)
            self.expanded.append(d)
        self.it = self.expanded.__iter__()

    def strlen(self):
        return f"{self.n_iter} (LHS on {self.orig_n})"
