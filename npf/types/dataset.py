import numpy as np
from typing import Dict, List, Tuple
from collections import OrderedDict
from npf.variable import is_numeric, get_numeric
import natsort

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

XYEB = Tuple
AllXYEB = Dict[ResultType, List[XYEB]]

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


def convert_to_xyeb(datasets: List[Tuple['Testie', 'Build' , Dataset]], run_list, key, do_x_sort, max_series = None, series_sort=None) -> AllXYEB:
    data_types = OrderedDict()
    all_result_types = set()

    for testie,build,all_results in datasets:
        for run, run_results in all_results.items():
            for result_type,results in run_results.items():
                all_result_types.add(result_type)

    for testie, build, all_results in datasets:
        x = OrderedDict()
        y = OrderedDict()
        e = OrderedDict()
        for run in run_list:
            if len(run) == 0:
                xval = build.pretty_name()
            else:
                xval = run.print_variable(key,build.pretty_name())
            results_types = all_results.get(run, {})
            for result_type in all_result_types:
                ydiv = var_divider(testie, "result", result_type)
                result = results_types.get(result_type,None)

                x.setdefault(result_type, []).append(xval)
                if result is not None:
                    result = np.asarray(result) / ydiv
                    y.setdefault(result_type, []).append(np.mean(result))
                    e.setdefault(result_type, []).append(np.std(result))
                else:
                    y.setdefault(result_type, []).append(np.nan)
                    e.setdefault(result_type, []).append(np.nan)
        for result_type in x.keys():
            if not do_x_sort:
                ox = x[result_type]
                oy = y[result_type]
                oe = e[result_type]
            else:
                order = np.argsort(x[result_type])
                ox = np.array(x[result_type])[order]
                oy = np.array(y[result_type])[order]
                oe = np.array(e[result_type])[order]


            data_types.setdefault(result_type, []).append((ox,oy,oe,build))
    if series_sort is not None:
        new_data_types = OrderedDict()
        for result_type,data in data_types.items():
            avg = []
            max = []
            min = []
            for x,y,e,build in data:
                if not np.isnan(np.sum(y)):
                    avg.append(np.sum(y))
                else:
                    avg.append(0)
                max.append(np.max(y))
                min.append(np.min(y))
            if series_sort.startswith('-'):
                inverted = True
                series_sort = series_sort[1:]
            else:
                inverted = False

            if series_sort == 'avg':
                order = np.argsort(np.asarray(avg))
            elif series_sort == 'max':
                order = np.argsort(- np.asarray(max))
            elif series_sort == 'min':
                order = np.argsort(np.asarray(min))
            elif series_sort == 'natsort':
                order = natsort.index_natsorted(data,key=lambda x: x[3].pretty_name())
            else:
                raise Exception("Unknown sorting : %s" % series_sort)

            if inverted:
                order = np.flip(order,0)

            data = [data[i] for i in order]
            new_data_types[result_type] = data
        data_types = new_data_types

    if max_series:
        new_data_types = OrderedDict()
        for i,(result_type,data) in enumerate(data_types.items()):
            new_data_types[result_type] = data[:max_series]
        data_types = new_data_types

    return data_types


