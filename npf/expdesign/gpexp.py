from collections import OrderedDict
import random

from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C
from sklearn.preprocessing import MinMaxScaler

from npf.expdesign.fullexp import FullVariableExpander

import pandas as pd 
import numpy as np

class GPVariableExpander(FullVariableExpander):
    """Uses a GP variable expander"""

    def __init__(self, vlist, overriden, results, seed=42, ci=0.95, outputs = None):      
        #List of all variables
        self.results = results
        self.ci = 1-ci
        self.seed = seed
        self.outputs = outputs
        super().__init__(vlist, overriden)

    def __iter__(self):
        self.it_left = self.expanded.copy()
        return self
    
    def __next__(self): 
        if len(self.it_left) == 0:
            raise StopIteration
        kernel = C(1.0) * RBF(length_scale=1.0)
        self.gp = GaussianProcessRegressor(kernel=kernel, alpha=1e-6, n_restarts_optimizer=10, random_state=self.seed)
        random.seed(self.seed)
        
        #for r, vals in self.results.items():
        X = pd.DataFrame([r.variables for r,_ in self.results.items()])
        y = pd.DataFrame([{k:np.mean(v) for k,v in vals.items()} for _,vals in self.results.items()])
        
        if self.outputs:
            y = y[self.outputs]
        #print(X)
        #print(y)
        
        min_max_scaler = MinMaxScaler()
        y_scaled = min_max_scaler.fit_transform(y)

        self.gp.fit(X, y_scaled)

        # Define candidate points for the next experiment
        X_next = pd.DataFrame([r for r in self.it_left])
        #print(X_next)

        # Predict mean and uncertainty (standard deviation)
        y_mean, y_std = self.gp.predict(X_next, return_std=True)

        #print(y_mean,y_std)
        ci = np.max(y_std)
        print("GP CI:", ci)
        if ci < self.ci:
            raise StopIteration
        
        
        # Select the point with the highest uncertainty (largest std deviation)
        max_val = np.max(y_std)
        max_indices = np.argwhere(y_std == max_val)
        #print(max_indices,len(max_indices))
        # print("max indices", max_indices)
        #idx = max_indices[len(max_indices) // 2]

        #print("Next run: ", idx)
        next_run = self.it_left[random.randint(0,max_indices.shape[0])]
        #print(next_run)
        self.it_left.remove(next_run)
        
        return next_run
        
    def strlen(self):
        return f"{len(self.expanded)}"
