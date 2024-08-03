from collections import OrderedDict
from math import ceil, log2
from typing import Dict

import numpy as np
from npf.expdesign.fullexp import FullVariableExpander
from npf.types.dataset import Run
from npf.variable import Variable

class OptVariableExpander(FullVariableExpander):
    def __init__(self, vlist:Dict[str,Variable], results, overriden, input, margin, all=False):
        if not input in vlist:
            raise Exception(f"{input} is not in the variables, please define a variable in the %variable section.")

        self.results = results
        self.input = input
        self.input_values = vlist[input].makeValues()
        if len(self.input_values) <= 2:
            print(f"WARNING: Doing zero-loss-throughput search on the variable {input} that has only {len(self.input_values)} values. This is useless."
                 f"You must define a range to search with a variable like {input}=[0-100#5].")
        del vlist[input]
        self.current = None
        self.n_done = 0
        self.n_it = 0
        self.n_tot_done = 0
        self.margin = margin
        self.all = all
        super().__init__(vlist, overriden)

    def __iter__(self):
        self.it = self.expanded.__iter__()
        self.current = None
        self.n_it = 0
        self.n_tot_done = 0
        return self
    
    def __len__(self):
        return int(len(self.expanded) * ceil(log2(len(self.input_values)) if (self.n_it <= 1) else self.n_tot_done/(self.n_it - 1)))

class ZLTVariableExpander(OptVariableExpander):

    def __init__(self, vlist:Dict[str,Variable], results, overriden, input, output, margin, all=False, perc=False):

        self.output = output
        self.perc = perc
        super().__init__(vlist, results, overriden, input, margin, all)


    def __next__(self):

        if self.current == None:
            self.current = self.it.__next__()
            self.n_it += 1
            self.n_tot_done += self.n_done
            self.n_done = 0


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
                        if self.perc:
                            r_out = r_out/100 * r_in
                        vals_for_current[r_in] = r_out
                        if r_out >= r_in/self.margin:
                            acceptable_rates.append(r_in)
                        else:
                            max_r = min(max_r, r_out)
                except KeyError:
                    raise Exception(f"{self.output} is not in the results. Sample of last result : {vals}")
        
        #Step 1 : try the max input rate first
        if len(vals_for_current) == 0:
            next_val = max_r
        elif len(vals_for_current) == 1:
            #If we're lucky, the max rate is doable
            
            if len(acceptable_rates) == 1 and not self.all:
                    self.current = None
                    return self.__next__()
                
            #Step 2 : go for the rate below the output of the max input
            maybe_achievable_inputs = list(filter(lambda x : x <= max_r, self.input_values))
            next_val = max(maybe_achievable_inputs)
        else:
            
            maybe_achievable_inputs = list(filter(lambda x : x <= max_r*self.margin, self.input_values))
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
                max_acceptable = -1 if self.all else max(acceptable_rates)
                #Consider we tried 100->95 (max_r=95), 90->90 (acceptable) we have to try values between 90..95
                left_to_try_over_acceptable = list(filter(lambda x: x > max_acceptable, left_to_try))
                if len(left_to_try_over_acceptable) == 0:
                            #Found!
                            self.current = None
                            return self.__next__()
                #Binary search
                if self.all:
                    next_val=max(left_to_try_over_acceptable)
                else:
                    next_val = left_to_try_over_acceptable[int(len(left_to_try_over_acceptable) / 2)]

            
        copy = self.current.copy()
        copy.update({self.input : next_val})
        self.n_done += 1
        return copy
        
        