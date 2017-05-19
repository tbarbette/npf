import numpy as np
from typing import Dict, List, Tuple

from npf.variable import is_numeric, get_numeric


class Run:
    def __init__(self, variables):
        self.variables = variables

    def format_variables(self, hide=None):
        if hide is None:
            hide = {}
        s = []
        for k, v in self.variables.items():
            if k in hide: continue
            if type(v) is tuple:
                s.append('%s = %s' % (k, v[1]))
            else:
                s.append('%s = %s' % (k, v))
        return ', '.join(s)

    def print_variable(self, k, default=None):
        v = self.variables.get(k,default)
        if type(v) is tuple:
            return v[1]
        else:
            return v

    def copy(self):
        newrun = Run(self.variables.copy())
        return newrun

    def inside(self, o):
        for k, v in self.variables.items():
            if not k in o.variables:
                return False
            ov = o.variables[k]
            if type(v) is tuple:
                v = v[1]
            if type(ov) is tuple:
                ov = ov[1]
            if is_numeric(v) and is_numeric(ov):
                if not get_numeric(v) == get_numeric(ov):
                    return False
            else:
                if not v == ov:
                    return False
        return True

    def intersect(self, common):
        difs = set.difference(set(self.variables.keys()), common)
        for dif in difs:
            del self.variables[dif]
        return self

    def __eq__(self, o):
        return self.inside(o) and o.inside(self)

    def __hash__(self):
        n = 0
        for k, v in self.variables.items():
            if type(v) is tuple:
                v = v[1]
            n += str(v).__hash__()
            n += k.__hash__()
        return n

    def __repr__(self):
        return "Run(" + self.format_variables() + ")"

    def __cmp__(self, o):
        for k, v in self.variables.items():
            if not k in o.variables: return 1
            ov = o.variables[k]
            if type(v) is str or type(ov) is str:
                if str(v) < str(ov):
                    return -1
                if str(v) > str(ov):
                    return 1
            else:
                if v < ov:
                    return -1
                if v > ov:
                    return 1
        return 0

    def __lt__(self, o):
        return self.__cmp__(o) < 0

    def __len__(self):
        return len(self.variables)


Dataset = Dict[Run, Dict[str, List]]
ResultType = str


def var_divider(testie: 'Testie', key: str, result_type):
    div = testie.config.get_dict_value("var_divider", "result", result_type=result_type, default=1)
    if is_numeric(div):
        return float(div)
    if div.lower() == 'g':
        return 1024 * 1024 * 1024
    elif div.lower() == 'm':
        return 1024 * 1024
    elif div.lower() == 'k':
        return 1024
    return 1


def convert_to_xye(datasets: List[Tuple[Dataset, 'Testie']], run_list, key) -> Dict[ResultType,List[Tuple]]:
    data_types = {}

    for all_results, testie in datasets:
        x = {}
        y = {}
        e = {}
        for run in run_list:
            results_types = all_results.get(run, {})
            for result_type, result in results_types.items():
                ydiv = var_divider(testie, "result", result_type)

                if len(run) == 0:
                    xval = key
                else:
                    xval = run.print_variable(key,key)

                x.setdefault(result_type, []).append(xval)
                if result is not None:
                    result = np.asarray(result) / ydiv
                    y.setdefault(result_type, []).append(np.mean(result))
                    e.setdefault(result_type, []).append(np.std(result))
                else:
                    y.setdefault(result_type, []).append(np.nan)
                    e.setdefault(result_type, []).append(np.nan)
        for result_type in x.keys():
            order = np.argsort(x[result_type])
            data_types.setdefault(result_type, []).append(
                (np.array(x[result_type])[order], np.array(y[result_type])[order], np.array(e[result_type])[order]))
    return data_types


