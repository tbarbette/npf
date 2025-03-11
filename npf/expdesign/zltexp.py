from collections import OrderedDict
from math import ceil, log2
from typing import Dict

import numpy as np
from npf.expdesign.fullexp import FullVariableExpander
from npf.models.dataset import Run
from npf.models.variables.variable import Variable

class OptVariableExpander(FullVariableExpander):
    def __init__(self, vlist:Dict[str,Variable], results, overriden, input, margin, all=False):
        if input not in vlist:
            raise Exception(f"{input} is not in the variables, please define a variable in the %variable section.")

        self.results = results
        self.input = input
        self.input_values = vlist[input].makeValues()
        if len(self.input_values) <= 2:
            print(  f"WARNING: Doing zero-loss-throughput search on the variable {input} that has only {len(self.input_values)} values. This is useless."
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

    def strlen(self):
        approx = int(len(self.expanded) * ceil(log2(len(self.input_values)) if (self.n_it <= 1) else self.n_tot_done/(self.n_it - 1)))
        max = len(self.expanded) * len(self.input_values)
        return f"~{approx}(max {max})"

class ZLTVariableExpander(OptVariableExpander):
    """ZLT variable expander. This class is used to find the Zero Loss Throughput of a system.

    In a broader way, it will try to find the maximal value for a given parameter that passes some acceptance test. For ZLT, the acceptence is the number of packets being dropped nearing zero.

    Given a possible input speed of 1 to 16MPPS, it will try 16MPPS first. If the output observed rate was 8MPPS (with zlp instead of zlt, ie perc=True in this class, it will use a percentage instead), it will try 7MPPS, the rate below the obseration.
    If 7MPPS was not achievable, the first goal is to find a "minimal" acceptable rate with a binary search. Say 7MPPS of input gave 2MPPS of output, it will try 7-2=5MPPS. That is very unlikely though, much probably 7 was okay.
    When a minimal acceptable rate is found, it will try to find the maximal acceptable rate with a binary search. Say 7MPPS was acceptable, nothing says that 8 or 9 was not okay too as the response is not necessarily linear. So it will try the middle between 8 and 15. So 11. Then 9, then 8.

    Once the maximum acceptable rate is found, by default ZLT will try the value above to ensure that the rate is not diminishing and the response is indeed monotonic. If monotonic is true then this will not be done.

    The parameter all will force to run all acceptable rates. This is useful when you want to find all acceptable rates, not only the maximal one and want to observe what happens below the maximal rate. However in general you don't want *all* rates under the maximal one, but just what is necessary to observe how, say, the latency, increase with the rate. So all can be 2 to use an exponential backoff. If the acceptable rate is 8, it will only try 8-1=7, 8-2=6, 8-4=4, (not 8-8=0 unless that is a valid rate)

    Constraints are variables for which a higher value, all other parameters being equal, is better. For instance, the number of cores is a usual constraint in a system which is relatively horizontally scalable.
    Imagine you have 14MPPS with 4 cores and the system has not much inter-core contention. There's no need to try 15 and 16MPPS with 3 cores as 3 cores cannot do better than 4 cores.
    The same is true for frequency

    """
    def __init__(self, vlist:Dict[str,Variable], results, overriden,
                 input, output, margin, all=0, perc=False, monotonic=False,constraints=[]):
        self.output = output
        self.perc = perc
        self.monotonic = monotonic
        super().__init__(vlist, results, overriden, input, margin, all)
        if constraints:
            self.expanded = sorted(self.expanded, key=lambda result: tuple(result[c] for c in constraints if c in result),reverse=True)
            self.constraints = [tuple((c, vlist[c].makeValues())) for c in constraints]
        else:
            self.constraints = None

    def need_run_for(self, next_val):
        self.next_val = next_val
        copy = self.current.copy()
        copy.update({self.input : next_val})
        self.n_done += 1
        return copy

    def ensure_monotonic(self, max_r, vals_for_current):
        if not self.monotonic and \
            (max_r is not None and max_r < max(self.executable_values) or (max_r is None)):
            # If the function is not monotonic, we now have to try rates between the max acceptable and the first dropping rate
            if max_r is not None:
                after_max = next(iter(filter(lambda x : x > max_r, self.executable_values)))
            else:
                after_max = min(self.executable_values)

            if after_max not in vals_for_current:
                return self.need_run_for(after_max)

        #Else we're finished
        self.validate_run()
        return self.__next__()

    def validate_run(self):
        """ Mark this run as the best ZLT one
        """
        #self.results[self.current][IS_ZLT] = 1

        self.current = None

    def __next__(self):
        if self.current is None:
            self.current = self.it.__next__()
            if self.current is None:
                return None
            self.n_it += 1
            self.n_tot_done += self.n_done
            self.n_done = 0
            self.next_val = None
            self.executable_values = self.input_values.copy()
            print("Evaluating ", self.current)
            if self.constraints:
                wc = self.current.copy()

                for c, _ in self.constraints:
                    del wc[c]
                if True:
                    m = {}
                    #Keep only values that are strictly better
                    for r, vals in self.results.items():

                        if Run(wc).inside(r):  #Without the constraint and the rate, so the run is any rate but with C == 5
                            valid = True
                            #print("Run", r)
                            r_c_vals = [] #Values for each constraints
                            for c, c_vals in self.constraints:
                                c_equal = self.current[c]
                                c_plus = min(filter(lambda x: x > self.current[c], c_vals), default=None)
                                c_val = r.variables[c]
                                if c_val < c_equal or (c_plus and c_val > c_plus):
                                    valid = False
                                    break
                                r_c_vals.append(c_val)

                            if valid:
                                #print("Consider", r, r_c_vals)
                                r_out = np.mean(vals[self.output])
                                r_in = r.variables[self.input]
                                if self.perc:
                                    r_out = r_out/100 * r_in
                                if r_out >= r_in/self.margin:
                                    #Accepted run
                                    if not tuple(r_c_vals) in m or r_in > m[tuple(r_c_vals)]: #Find the rate at which drops start
                                        m[tuple(r_c_vals)] = r_in
                    if m:
                        m =  min(m.values())
                        self.executable_values = list(filter(lambda x : x <= m, self.executable_values))
                    else:
                        m = None
                    print("Max for run ",self.current," is ", m)


        elif not self.executable_values:
            #There's no more points to try, we could never find a ZLT
            self.current = None
            return self.__next__()


        # get all outputs for all inputs
        vals_for_current = {}
        acceptable_rates = []

        # max_r is the maximal rate (tried or not) that we tried but still dropped some packets
        max_r = max(self.executable_values)
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
                except KeyError as e:
                    #raise Exception(
                     print(   f"{self.output} is not in the results. Sample of last result : {vals}"
                    )
                    #from e

        #Step 1 : try the max input rate first
        next_val = None
        if not vals_for_current:
            next_val = max_r
        elif len(vals_for_current) == 1:
            #If we're lucky, the max rate is doable
            if len(acceptable_rates) == 1:
                if not self.all:
                    return self.ensure_monotonic(max(acceptable_rates), vals_for_current)
            else:
                #Step 2 : go for the rate below the output of the max input
                maybe_achievable_inputs = list(filter(lambda x : x <= max_r, self.executable_values))
                if len(maybe_achievable_inputs) == 0:
                    print(f"WARNING: No achievable for {self.input}! Tried {max_r} and it did not work.")
                    return self.ensure_monotonic(None, vals_for_current)
                else:
                    next_val = max(maybe_achievable_inputs)

        if next_val==None:
            #We have at least two values or one value but it's acceptable and all is set, so we need to analyse values below the max acceptable rate

            maybe_achievable_inputs = list(filter(lambda x : x <= max_r*self.margin, self.executable_values))
            left_to_try = set(maybe_achievable_inputs).difference(vals_for_current.keys())
            if len(left_to_try) == 0: #No more values left to try
                if len(acceptable_rates) > 0: #Nothing left to try but we have a ZLT, should try the next value in non-monotonic
                    return self.ensure_monotonic(max(acceptable_rates), vals_for_current)
                else:
                    #We could never find a zlt, and there's nothing left to try... no value can handle the input
                    self.validate_run()
                    return self.__next__()


            #Step 3...K : try to get an acceptable rate. This step might be skipped if we got an acceptable rate already
            if left_to_try and not acceptable_rates:
                #Try the rate below the min already tried rate - its drop count. For instance if we tried 70 last run but got 67 of throughput, try the rate below 64
                min_input = min(vals_for_current.keys())
                min_output = vals_for_current[min_input]
                target = min_output - (min_input - min_output)
                #We look for the rate below the target
                next_vals = list(filter(lambda x : x < target,left_to_try))
                #Maybe there's no rate as low as that so next_vals might be empty. In that case we take the minimal rate
                if len(next_vals) > 0:
                    next_val = max(next_vals)
                else:
                    next_val = min(left_to_try)
            else:
                #We now have an acceptable rate, but we don't know if it's the actual maximal one
                #Step K... n : we do a binary search between the maximum acceptable rate and the minimal rate observed

                #Max acceptable is the maximal known working rate
                max_acceptable = max(acceptable_rates)
                #Consider we tried 100->95 (max_r=95), 90->90 (acceptable) we have to try values between 90..95
                left_to_try_over_acceptable = list(filter(lambda x: x > max_acceptable, left_to_try))
                if not left_to_try_over_acceptable:
                    #Ok so we now have the real max acceptable rate. We now have to do more exploration if all is set
                    if self.all >= 1:
                        left_to_try_below_acceptable = list(filter(lambda x: x < max_acceptable, left_to_try))
                        if left_to_try_below_acceptable and self.all == 2:
                            to_try = set()
                            step = 1

                            midx = self.executable_values.index(max_acceptable)
                            pos = midx - 1
                            while pos >= 0:
                                val = self.executable_values[pos]
                                if val in left_to_try_below_acceptable:
                                    to_try.add(val)
                                step *= 2
                                pos = midx - step

                            left_to_try_below_acceptable = to_try
                        left_to_try_over_acceptable = left_to_try_below_acceptable
                    if not left_to_try_over_acceptable:
                        return self.ensure_monotonic(max(acceptable_rates), vals_for_current)
                #Binary search
                if self.all > 0:
                    next_val = max(left_to_try_over_acceptable)
                else:
                    next_val = left_to_try_over_acceptable[int(len(left_to_try_over_acceptable) / 2)]

        if next_val == self.next_val:

            print("ZLT Warning: Removing ",next_val)
            print(vals_for_current)
            self.executable_values.remove(next_val)
            #Loop : this value is not running for some reasons
            return self.__next__()

        return self.need_run_for(next_val)


class MinAcceptableVariableExpander(OptVariableExpander):
    """An exploration that tries to find the smallest value that is acceptable for a given factor.
    Typical usage is when you want to find the minimum amount of cores needed to achieve a certain throughput.
    """
    def __init__(self, vlist:Dict[str,Variable], results, overriden, input, output, margin):
        self.output = output
        super().__init__(vlist, results, overriden, input, margin, False)

    def need_run_for(self, next_val):
        self.next_val = next_val
        copy = self.current.copy()
        copy.update({self.input : next_val})
        self.n_done += 1
        return copy

    def ensure_monotonic(self, max_r, vals_for_current):
        self.validate_run()
        return self.__next__()

    def validate_run(self):
        """ Mark this run as the best ZLT one
        """
        #self.results[self.current][IS_ZLT] = 1
        # self.constraints Run(self.current)
        self.current = None

    def __next__(self):
        if self.current is None:
            self.current = self.it.__next__()
            if self.current is None:
                return None
            self.n_it += 1
            self.n_tot_done += self.n_done
            self.n_done = 0
            self.next_val = None
            self.executable_values = self.input_values.copy()
        elif not self.executable_values:
            #There's no more points to try, we could never find a ZLT
            self.current = None
            return self.__next__()


        # get all outputs for all inputs
        vals_for_current = {}
        acceptable_rates = []
        min_r = min(self.executable_values)
        for r, vals in self.results.items():
            if Run(self.current).inside(r):
                try:
                    if self.output:
                        r_out = np.mean(vals[self.output])
                        r_in = r.variables[self.input]
                        vals_for_current[r_in] = r_out
                        if r_out >= 100/self.margin:
                            acceptable_rates.append(r_in)
                except KeyError as e:
                    raise Exception(
                        f"{self.output} is not in the results. Sample of last result : {vals}"
                    ) from e

        #Step 1 : try the min value first
        if not vals_for_current:
            next_val = min_r
        elif len(vals_for_current) == 1:
            #If we're lucky, the min rate is doable

            if len(acceptable_rates) == 1:
                    return self.ensure_monotonic(min(acceptable_rates), vals_for_current)

            #Step 2 : go for the value abouve the undoable value
            maybe_achievable_inputs = list(filter(lambda x : x >= min_r, self.executable_values))
            next_val = max(maybe_achievable_inputs)
        else:

            max_r = max(self.executable_values)
            if vals_for_current[max_r] < 100/self.margin:
                #Undoable
                self.current = None
                return self.__next__()

            min_acceptable = min(acceptable_rates)
            maybe_achievable_inputs = list(filter(lambda x : x >= min_r/self.margin, self.executable_values))
            left_to_try = set(maybe_achievable_inputs).difference(vals_for_current.keys())

            left_to_try_below_acceptable = list(filter(lambda x: x < min_acceptable, left_to_try))
            if not left_to_try_below_acceptable:
                return self.ensure_monotonic(min_acceptable, vals_for_current)

            #Binary search
            next_val = left_to_try_below_acceptable[int(len(left_to_try_below_acceptable) / 2)]

        if next_val == self.next_val:
            self.executable_values.remove(next_val)
            #Loop : this value is not running for some reasons
            return self.__next__()

        return self.need_run_for(next_val)
