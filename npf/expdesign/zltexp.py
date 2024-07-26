from collections import OrderedDict
from typing import Dict

import numpy as np
from npf.expdesign.fullexp import FullVariableExpander
from npf.types.dataset import Run
from npf.variable import Variable


class ZLTVariableExpander(FullVariableExpander):

    def __init__(self, vlist:Dict[str,Variable], results, overriden, input, output):
        
        
        if not input in vlist:
            raise Exception(f"{input} is not in the variables, please define a variable in the %variable section.")
        self.results = results
        self.input = input
        self.input_values = vlist[input].makeValues()
        del vlist[input]
        self.current = None
        self.output = output
        self.passed = 0
        super().__init__(vlist, overriden)
        
    def __iter__(self):
        self.it = self.expanded.__iter__()
        self.passed = 0
        return self
    
    def __len__(self):
        return len(self.expanded) * len(self.input_values) - self.passed

    def __next__(self):
        margin=1.01
        if self.current == None:
            self.current = self.it.__next__()
            
        # get all outputs for all inputs
        vals_for_current = {}
        acceptable_rates = []
        max_r = max(self.input_values)
        for r, vals in self.results.items():
            if Run(self.current).inside(r):
                try:
                    if self.output:
                        r_out = np.mean(vals[self.output])
                        r_in = r.variables[self.input]
                        vals_for_current[r_in] = r_out
                        if r_out >= r_in/margin:
                            acceptable_rates.append(r_in)
                        else:
                            max_r = min(max_r, r_out)
                except KeyError:
                    raise Exception(f"{self.output} is not in the results. Sample of last result : {vals}")
        
        #Step 1 : try the max output
        if len(vals_for_current) == 0:
            next_val = max_r
        elif len(vals_for_current) == 1:
            #If we're lucky, the max rate is doable
            
            if len(acceptable_rates) == 1:
                    self.current = None
                    self.passed += len(self.input_values) - 1
                    return self.__next__()
                
            #Step 2 : go for the rate below the max output
            maybe_achievable_inputs = list(filter(lambda x : x <= max_r, self.input_values))
            next_val = max(maybe_achievable_inputs)
        else:
            
            maybe_achievable_inputs = list(filter(lambda x : x <= max_r*margin, self.input_values))
            left_to_try = set(maybe_achievable_inputs).difference(vals_for_current.keys())
            
            #Step 3...K : try to get an acceptable rate. This step might be skiped if we got an acceptable rate already
            if len(acceptable_rates) == 0:
                #Try the rate below the min already tried rate - its drop count. For instance if we tried 70 last run but got 67 of throughput, try the rate below 64
                min_input = min(vals_for_current.keys())
                min_output = vals_for_current[min_input]
                target = min_output - (min_input - min_output)
                next_val = max(filter(lambda x : x < target,left_to_try))
            else:
                #Step K... n : we do a binary search between the maximum acceptable rate and the minimal rate observed
                max_acceptable = max(acceptable_rates)
                #Consider we tried 100->95 (max_r=95), 90->90 (acceptable) we have to try values between 90..95
                left_to_try_over_acceptable = list(filter(lambda x: x > max_acceptable, left_to_try))
                if len(left_to_try_over_acceptable) == 0:
                            #Found!
                            self.current = None
                            self.passed += len(self.input_values) - len(vals_for_current)
                            return self.__next__()
                #Binary search
                next_val = left_to_try_over_acceptable[int(len(left_to_try_over_acceptable) / 2)]

            
        copy = self.current.copy()
        copy.update({self.input : next_val})
        return copy
        
        