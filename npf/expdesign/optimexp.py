from npf.tests.variable import OrderedDict


from collections import OrderedDict

from skopt import Optimizer
from skopt.space import Real
from joblib import Parallel, delayed
# example objective taken from skopt
from skopt.benchmarks import branin

class OptimizeVariableExpander:
    """Use scipy optimize function"""

    def __init__(self, vlist, overriden):
        dimensions = []
        for k, v in vlist.items():
            if k in overriden:
                continue

            l = v.makeValues()
            dimensions.append(l)
            
        self.optimizer = Optimizer(
            dimensions=dimensions,
            random_state=1,
            base_estimator='gp'
        ) 


    def __iter__(self):
        x = self.optimizer.ask(n_points=1)  # x is a list of n_points points
        return x

    def tell(x, y):
        self.optimizer.tell(x, y)
        
    def __next__(self):
        return self.it.__next__()