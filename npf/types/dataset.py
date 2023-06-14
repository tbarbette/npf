import numpy as np
from typing import Dict, List, Tuple
from collections import OrderedDict
import sys
if sys.version_info < (3, 7):
    from orderedset import OrderedSet
else:
    from ordered_set import OrderedSet
import natsort
import csv

from npf import npf
from npf.variable import is_numeric, get_numeric, numeric_dict

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
        if len(self.variables) != len(o.variables):
            return False
        for k, v in self.variables.items():
            if not k in o.variables:
                return False
            ov = o.variables[k]
            if v == ov:
                continue
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

    def __hash__(self):
        n = 0
        for k, v in self.variables.items():
            if type(v) is tuple:
                v = v[1]
            if is_numeric(v):
                n += get_numeric(v).__hash__()
            else:
                n += str(v).__hash__()
            n += k.__hash__()
        return n

    def __repr__(self):
        return "Run(" + self.format_variables() + ")"

    def __cmp__(self, o):
        for k, v in self.variables.items():
            if not k in o.variables: return 1
            ov = o.variables[k]
            if is_numeric(v) and is_numeric(ov):
                return get_numeric(v) - get_numeric(ov)

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

class ImmutableRun:
    def __init__(self, variables):
        self._run = Run(numeric_dict(variables))
        self._hash = self._run.__hash__()

    def __hash__(self):
        return self._hash

    def __eq__(self, o):
        if type(o) is Run:
            return self._run.__eq__(o)
        else:
            return self._run.__eq__(o._run)




Dataset = Dict[Run, Dict[str, List]]
ResultType = str

# A tuple of X,Y,E and B, each a list of :
#  * X variables, if you have one dynamic variable, X is that variable. If you have multiple series, and/or multiple variables X is the crossproduct
#  * the "average" of the values for the related run for X. y default the mean, but that can be changed with graph_y_group to be the median, the std, etc
#  * E is a tuple of the mean, the std, and the list of original values of Y for X (not grouped)
#  * and the build into the fourth, refered to as B
XYEB = Tuple

# A dictionnary of XYEB for all results
AllXYEB = Dict[ResultType, List[XYEB]]

def var_divider(test: 'Test', key: str, result_type = None):
    div = test.config.get_dict_value("var_divider", key, result_type=result_type, default=1)
    if is_numeric(div):
        return float(div)
    if div.lower() == 'g':
        return 1024 * 1024 * 1024
    elif div.lower() == 'm':
        return 1024 * 1024
    elif div.lower() == 'k':
        return 1024
    return 1

def group_val(result, t):
                           if t == 'mean':
                               return np.mean(result)
                           elif t == 'avg':
                               return np.average(result)
                           elif t == 'min':
                               return np.min(result)
                           elif t == 'max':
                               return np.max(result)
                           elif t[:4] == 'perc':
                               return np.percentile(result, int(t[4:]))
                           elif t == 'median' or t == 'med':
                               return np.median(result)
                           elif t == 'std':
                               return np.std(result)
                           elif t == 'nres' or t == 'n':
                               return len(result)
                           elif t == 'first':
                                return result[0]
                           elif t == 'last':
                                return result[-1]
                           elif t == 'all':
                               return result
                           else:
                               print("WARNING : Unknown format %s" % t)
                               return np.nan


def write_output(datasets, statics, options, run_list, kind=None):
    if options.output is None:
        return

    all_result_types = OrderedSet()

    for test,build,all_results in datasets:
        for run, run_results in all_results.items():
            for result_type,results in run_results.items():
                all_result_types.add(result_type)
    for test, build, all_results in datasets:
        csvs = OrderedDict()
        for run in run_list:
            results_types = all_results.get(run, OrderedDict())
            for result_type in all_result_types:
                if result_type in csvs:
                    type_filename,csvfile,wr = csvs[result_type]
                else:
                    type_filename = npf.build_filename(test, build, options.output if options.output != 'graph' else options.graph_filename, statics, 'csv', type_str=result_type, show_serie=(len(datasets) > 1 or options.show_serie), force_ext=True, data_folder=True, prefix = kind + '-' if kind else None)
                    csvfile = open(type_filename, 'w')
                    wr = csv.writer(csvfile, delimiter=' ',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
                    csvs[result_type] = (type_filename,csvfile,wr)

                result = results_types.get(result_type,None)

                if result is not None:
                       row = []
                       for t in options.output_columns:
                           if t == 'x':
                               for var,val in run.variables.items():
                                   if var in statics:
                                       continue
                                   row.append(val)
                           elif t == 'all_x':
                               for var,val in run.variables.items():
                                   row.append(val)
                           elif t == 'raw':
                               row.extend(result)
                           else:
                               yval = group_val(result,t)
                               if yval is not None:
                                   try:
                                       it = iter(yval)
                                       row.extend(yval)
                                   except TypeError as te:
                                       row.append(yval)
                       if row:
                           wr.writerow(row)
        for result_type in csvs.keys():
            if options.output is not None:
                print("Output written to %s" % csvs[result_type][0])
                csvs[result_type][1].close()

# Converts a dataset (a most of series) to a more mathematical format, XYEB (see above)
def convert_to_xyeb(datasets: List[Tuple['Test', 'Build' , Dataset]], run_list, key, do_x_sort, statics, options, max_series = None, series_sort=None, y_group={}, color=[], kind = None) -> AllXYEB:
    write_output(datasets, statics, options, run_list, kind)
    data_types = OrderedDict()
    all_result_types = OrderedSet()

    for test,build,all_results in datasets:
        for run, run_results in all_results.items():
            for result_type,results in run_results.items():
                all_result_types.add(result_type)

    for test, build, all_results in datasets:
        x = OrderedDict()
        y = OrderedDict()
        e = OrderedDict()
        for run in run_list:
            if len(run) == 0:
                xval = build.pretty_name()
            else:
                xval = run.print_variable(key, build.pretty_name())

            results_types = all_results.get(run, OrderedDict())
            for result_type in all_result_types:

                #ydiv = var_divider(test, "result", result_type) results are now divided before
                xdiv = var_divider(test, key)
                result = results_types.get(result_type,None)

                if xdiv != 1 and is_numeric(xval):
                    x.setdefault(result_type, []).append(get_numeric(xval) / xdiv)
                else:
                    x.setdefault(result_type, []).append(xval)

                if result is not None:
                    yval = group_val(result, y_group[result_type] if result_type in y_group else ( y_group['result'] if 'result' in y_group else 'mean'))
                    y.setdefault(result_type, []).append(yval)

                    std = np.std(result)
                    mean = np.mean(result)
                    e.setdefault(result_type, []).append((mean, std, result))
                else:
                    y.setdefault(result_type, []).append(np.nan)
                    e.setdefault(result_type, []).append((np.nan, np.nan, [np.nan]))


        for result_type in x.keys():

          try:

            if not do_x_sort:
                ox = x[result_type]
                oy = y[result_type]
                oe = e[result_type]
            else:
                order = np.argsort(x[result_type])
                ox = np.array(x[result_type])[order]
                oy = np.array(y[result_type])[order]
                oe = [e[result_type][i] for i in order]


            data_types.setdefault(result_type, []).append((ox,oy,oe,build))
          except Exception as err:
              print("ERROR while transforming data")
              print(err)
              print("x",x[result_type])
              print("y",y[result_type])
              print("e",e[result_type])

    if series_sort is not None and series_sort != "":
        if type(series_sort) is str and series_sort.startswith('-'):
            inverted = True
            series_sort = series_sort[1:]
        else:
            inverted = False

        new_data_types = OrderedDict()
        for result_type, data in data_types.items():
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
            if type(series_sort) is list:
                ok = True
                for i,so in enumerate(series_sort):

                    if is_numeric(so):
                        o = so
                        if o >= len(data):
                            print("ERROR: sorting for %s is invalid, %d is out of range" % (result_type,o))
                            ok = False
                            break
                    elif so in [x for x,y,e,build in data]:
                        o = [x for x,y,e,build in data].index(so)
                    elif so in [build.pretty_name() for x,y,e,build in data]:
                        o = [build.pretty_name() for x,y,e,build in data].index(so)
                    else:
                            print("ERROR: sorting for %s is invalid, %s is not in list" % (result_type,so))
                            ok = False
                            break
                    series_sort[i] = o

                if ok:
                    order = series_sort
                else:
                    order = np.argsort(np.asarray(avg))
            elif series_sort == 'avg':
                order = np.argsort(np.asarray(avg))
            elif series_sort == 'max':
                order = np.argsort(- np.asarray(max))
            elif series_sort == 'min':
                order = np.argsort(np.asarray(min))
            elif series_sort == 'natsort':
                order = natsort.index_natsorted(data,key=lambda x: x[3].pretty_name())
            elif series_sort == 'color':
                order = np.argsort(color)
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


