import io
import math
import re
import natsort
import copy
import traceback
import sys
if sys.version_info < (3, 7):
    from orderedset import OrderedSet
else:
    from ordered_set import OrderedSet

from packaging import version
from scipy import ndimage
from asteval import Interpreter
from collections import OrderedDict
from typing import List
import numpy as np
from pygtrie import Trie

from npf.types import dataset
from npf.types.dataset import Run, XYEB, AllXYEB, group_val
from npf.variable import is_log, is_numeric, get_numeric, numericable, get_bool, is_bool
from npf.section import SectionVariable
from npf.build import Build
from npf import npf, variable

import matplotlib
# There is a matplotlib bug which causes CI failures
# see https://github.com/rstudio/py-shiny/issues/611#issuecomment-1632866419
import warnings
if matplotlib.__version__ == "3.7.2":
        warnings.filterwarnings(
                        "ignore", category=UserWarning, message="The figure layout has changed to tight"
                            )
matplotlib.use('Agg')
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42
import matplotlib.pyplot as plt
from matplotlib.ticker import LinearLocator, ScalarFormatter, Formatter, MultipleLocator, NullLocator
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, FormatStrFormatter, EngFormatter
import matplotlib.transforms as mtransforms


import itertools
import math
import os
import webcolors

from scipy.ndimage import gaussian_filter1d

import pandas as pd

graphcolor = [(31, 119, 180), (174, 199, 232), (255, 127, 14), (255, 187, 120),
              (44, 160, 44), (152, 223, 138), (214, 39, 40), (255, 152, 150),
              (148, 103, 189), (197, 176, 213), (140, 86, 75), (196, 156, 148),
              (227, 119, 194), (247, 182, 210), (127, 127, 127), (199, 199, 199),
              (188, 189, 34), (219, 219, 141), (23, 190, 207), (158, 218, 229)]

for i in range(len(graphcolor)):
    r, g, b = graphcolor[i]
    graphcolor[i] = (r / 255., g / 255., b / 255.)

def hexToList(s):
    l = []
    for c in s.split(' '):
        l.append(tuple(a / 255. for a in webcolors.hex_to_rgb(c)))
    return l

def lighter(c, p, n):
    n = n / 255.
    return tuple(min(1,max(0,a * p + (1-p) * n)) for a in c)


def buildLight(c,m=4):
    l = []
    r=c
    for i in range(0,m):
        r = lighter(r,0.90,255)
        l.append(r)
    l.reverse()
    l.append(c)
    r=c
    for i in range(0,m):
        r = lighter(r,0.90,0)
        l.append(r)
    l.reverse()
    return l

graphcolorseries = [graphcolor]
#graphcolorseries.append(hexToList("#144c73 #185a88 #1b699e #1f77b4 #2385ca #2b93db #419ede"))
#graphcolorseries.append(hexToList("#1c641c #217821 #278c27 #2ca02c #32b432 #37c837 #4bce4b"))
#graphcolorseries.append(hexToList("#c15a00 #da6600 #f47200 #ff7f0e #ff8d28 #ff9a41 #ffa85b"))
#graphcolorseries.append(hexToList("#951b1c #ab1f20 #c02324 #d62728 #db3b3c #df5152 #e36667"))
#graphcolorseries.append(hexToList("#6e4196 #7b49a8 #8755b5 #9467bd #a179c5 #ad8bcc #ba9cd4"))
for i in range((int)(len(graphcolor) / 2)):
    graphcolorseries.append(buildLight([(graphcolor[i * 2][c] + graphcolor[i * 2 + 1][c]) / 2 for c in range(3)]))

gridcolors = [ (0.7,0.7,0.7) ]
legendcolors = [ None ]
for clist in graphcolorseries[1:]:
    gridcolors.append(lighter(clist[(int)(len(clist) / 2)], 0.25, 200))
    legendcolors.append(lighter(clist[(int)(len(clist) / 2)], 0.45, 25))

def find_base(ax):
    if ax[0] == 0 and len(ax) > 2:
        base = float(ax[2]) / float(ax[1])
    else:
        base = float(ax[1]) / float(ax[0])
    if base != 2:
        base = 10
    return base

def smooth(y, box_pts):
    if box_pts < 2:
        return y
    if box_pts % 2 == 0:
        print("Graph_smooth must be odd, it will be incremented")
        box_pts = box_pts + 1
    box = np.ones(box_pts)/box_pts
    h = int(math.floor(box_pts /2))
    y_smooth = np.convolve(np.concatenate((np.repeat(float(y[0]),h),  y, np.repeat(float(y[-1]),h)), axis=0), box, mode='valid')
    return y_smooth

def smooth_range(x, y, r, newx):
    new_y = tuple([] for _ in range(len(y)))
    for x_v in newx:
        mask = np.logical_and(x > (x_v - r), x <( x_v + r))
        for i in range(len(y)):
            l = np.mean(y[i][mask])
            new_y[i].append(l)
    return tuple([np.asarray(y) for y in new_y])

def roundf(x, prec):
    exp = pow(10, prec)
    x = round(float(x) * exp)
    x = x / exp
    return x

class Map(OrderedDict):
    def __init__(self, fname):
        super().__init__()
        if fname:
          for fn in fname.split('+'):
            f = open(fn, 'r')
            for line in f:
                line = line.strip()
                if not line or line.startswith('//') or line.startswith('#'):
                    continue
                k,v = [x.strip() for x in line.split(':',1)]
                self[re.compile(k)] = v

    def search(self, map_v):
        for k,v in self.items():
            if re.search(k,str(map_v)):
                return v
        return None


def guess_type(d):
    for k,v in d.items():
        if is_numeric(v):
            d[k]=get_numeric(v)
    return d


def broken_axes_ratio (values):
    if len(values) == 3:
        _, _, ratio = values
        if ratio is not None:
            return ratio
    elif len(values) == 2:
        vmin, vmax = values
        if vmin is not None and vmax is not None:
            return vmax-vmin
    return 1


class Graph:
    """
    This is a structure holder for data to build a graph
    """
    def __init__(self, grapher:'Grapher'):
        self.grapher = grapher
        self.subtitle = None
        self.data_types = None

    def statics(self):
        return dict([(var,list(values)[0]) for var,values in self.vars_values.items() if len(values) == 1])

    def dyns(self):
        return [var for var,values in self.vars_values.items() if len(values) > 1]

    #Convert the series into te XYEB format (see types.dataset)
    def dataset(self,kind=None):
        if not self.data_types:

            self.data_types = dataset.convert_to_xyeb(
                datasets = self.series,
                run_list = self.vars_all,
                key = self.key,
                max_series=self.grapher.config('graph_max_series'),
                do_x_sort=self.do_sort,
                series_sort=self.grapher.config('graph_series_sort'),
                options=self.grapher.options,
                statics=self.statics(),
                y_group=self.grapher.configdict('graph_y_group'),
                color=[get_numeric(v) for v in self.grapher.configlist('graph_color')],
                kind=kind
                )

        return self.data_types

    def split_for_series(self):
        '''Make a sub-graph per serie'''
        sg = []
        for script,build,all_results in self.series:
            subgraph = self.grapher.series_to_graph([(script,build,all_results)], self.dyns(), self.vars_values.copy(), self.vars_all.copy())
            subgraph.subtitle = ((self.title + " : ") if self.title else '') + build.pretty_name()
            subgraph.title = self.title
            sg.append(subgraph)
        return sg

    # Divide all series by the first one, making a percentage of difference
    @staticmethod
    def series_prop(series, prop, exclusions = []):
            if len(series) == 1:
                raise Exception("Cannot make proportional series with only one serie !")
            newseries = []
            if not is_numeric(prop):
                prop=1
            if len(series[0]) < 3:
                raise Exception("Malformed serie !")
            base_results=series[0][2]
            for i, (script, build, all_results) in enumerate(series[1:]):
                new_results={}
                for run,run_results in all_results.items():
                    if not run in base_results:
                        print(run,"FIXME is not in base")
                        continue

                    for result_type, results in run_results.items():
                        if not result_type in base_results[run]:
                            run_results[result_type] = None
                            print(result_type, "not in base for %s" % run)
                            continue
                        base = base_results[run][result_type]
                        if len(base) > len(results):
                            base = base[:len(results)]
                        elif len(results) > len(base):
                            results = results[:len(base)]
                        base = np.array(base)
                        results = np.array(results)
                        if result_type not in exclusions:
                            f = np.nonzero(base)
                            results = (results[f] / base[f] * float(abs(prop)) + (prop if prop < 0 else 0))
                        run_results[result_type] = results
                    new_results[run] = run_results
                build._pretty_name = build._pretty_name + " / " + series[0][1]._pretty_name
                newseries.append((script, build, new_results))
            return newseries


class Grapher:
    def __init__(self):
        self.scripts = set()
        self._config_cache = {}

    def config_bool(self, var, default=None):
        val = self.config(var, default)
        return get_bool(val)

    def config_bool_or_in(self, var, obj, default=None):
        val = self.config(var, default)

        #If not found, return the default
        if val is None:
            return default

        if type(val) == type(obj) and val == obj:
            return True

        if isinstance(val, list):
            return obj in val
        if is_bool(val):
            return get_bool(val)
        return default

    def config(self, var, default=None):
        for script in self.scripts:
            if var in script.config:
                return script.config[var]
        return default

    def configlist(self, var, default=None):
        for script in self.scripts:
            if var in script.config:
                return script.config.get_list(var)
        return default

    def configdict(self, var, default=None):
        for script in self.scripts:
            if var in script.config:
                return script.config.get_dict(var)
        return default

    def scriptconfig(self, var, key, default=None, result_type=None):
        if (var,key,result_type) in self._config_cache:
            return self._config_cache[(var,key,result_type)]
        else:
            v = self._scriptconfig(var, key, default, result_type)
            self._config_cache[(var,key,result_type)] = v
            return v

    def _scriptconfig(self, var, key, default, result_type):
        for script in self.scripts:
            if var in script.config:
                return script.config.get_dict_value(var,key,default=default,result_type=result_type)
        return default

    def result_in_list(self, var, result_type):
        l = self.configlist(var, [])
        return (result_type in l) or ("result-" + result_type in l) or ("result" in l)

    def var_name(self, key, result_type=None) -> str:
        return self.scriptconfig("var_names", key, key if not result_type else result_type, result_type)

    def us(self, x, pos):
        return self.formats(x, pos, 1)

    def formats(self,x,pos,mult):
        return "%d" % (x * mult)

    def get_var_lim(self, key, result_type):
        var_lim = self.scriptconfig("var_lim", key, result_type=result_type, default=None)
        axes = []
        if var_lim:
          for var_lim in var_lim.split('+'):
            ymin = None
            ymax = None
            ratio = None

            if var_lim.startswith('-'):
                n = var_lim[1:].split('-',2)
                n[0] = "-"+n[0]
            else:
                n = var_lim.split('-',2)
            try:
              # Try to read the ratio, if given
              if len(n) == 3 and n[1] != "" and  n[2] != "":
                ymin, ymax, ratio = (npf.parseUnit(x) for x in n)
              if len(n) >= 2 and n[1] != "":
                ymin, ymax = (npf.parseUnit(x) for x in n[:2])
              else:
                f=float(n[0])
                if f==0:
                    ymin=f
                else:
                    ylim=f
            except Exception as e:
                print(e)
                traceback.print_exc()
            if ratio:
                axes.append([ymin,ymax,ratio])
            else:
                axes.append([ymin,ymax])
        else:
            ymin = None
            ymax = None

            axes.append([ymin,ymax])
        return axes


    class ByteFormatter(Formatter):
        def __init__(self,unit,ps="",compact=False,k=1000,mult=1):
            self.unit = unit
            self.ps = ps
            if unit == "Bps":
                self.unit = "B"
                self.ps = "/s"

            self.compact = compact
            self.k = k
            self.mult = mult

        def __call__(self, x, pos=None):
            """
            Return the value of the user defined function.

            `x` and `pos` are passed through as-is.
            """
            return self.formatb(x * self.mult, pos,self.unit,self.ps,self.compact,self.k)

        def formatb(self, x, pos, unit, ps, compact, k):
            if compact:
                pres="%d"
            else:
                pres="%.2f"
            if x >= (k*k*k):
                v = x / (k*k*k)
                if v < 10 and compact:
                    pres = "%.1f"
                return (pres + "G%s"+ps) % (v, unit)
            elif x >= (k*k):
                return (pres + "M%s"+ps) % (x / (k*k), unit)
            elif x >= k:
                return (pres+ "K%s"+ps) % (x / k, unit)
            else:
                return (pres+ "%s"+ps) % (x, unit)

    def combine_variables(self, run_list, variables_to_merge):
        ss = []
        if len(variables_to_merge) == 1:
            for run in run_list:
                s = []
                for k, v in run.variables.items():
                    if k in variables_to_merge:
                        s.append("%s" % str(v[1] if type(v) is tuple else v))
                ss.append(','.join(s))
        else:
            use_short = False
            short_ss = []
            for run in run_list:
                s = []
                short_s = {}
                for k, v in run.variables.items():
                    if k in variables_to_merge:
                        v = str(v[1] if type(v) is tuple else v)
                        s.append("%s = %s" % (self.var_name(k), v))
                        short_s[k] = v
                vs = ','.join(s)
                ss.append(vs)
                if len(vs) > 30:
                    use_short = True
                l_short=[]
                t_short_s=Trie(short_s)
                for k,v in short_s.items():
                    p=1
                    while len(list(t_short_s.keys(k[:p]))) > 1:
                        p+=1
                    k = k[(p-1):]
                    l_short.append("%s = %s" % (k if len(k) < 6 else k[:3], v))
                short_ss.append(','.join(l_short))
            if use_short:
                ss = short_ss
        return ss

    def aggregate_variable(self, key, series, method):
        nseries = []
        for i,(test, build, all_results) in enumerate(series):
            aggregates = OrderedDict()
            for run, run_results in all_results.items():
                    #                    if (graph_variables and not run in graph_variables):
                    #                        continue
                newrun = run.copy()
                for k in key.split("+"):
                    if k in newrun.variables:
                        del newrun.variables[k]

                newrun.variables[key] = 'AGG'

                aggregates.setdefault(newrun,[]).append(run_results)

            new_all_results = OrderedDict()
            for run, multiple_run_results in aggregates.items():
                    new_run_results = OrderedDict()
                    agg = {}
                    all_result_types = set()
                    for run_results in multiple_run_results:
                        for result_type, results in run_results.items():
                            agg.setdefault(result_type,{})
                            all_result_types.add(result_type)
                            for i,result in enumerate(results):
                                agg[result_type].setdefault(i,[]).append(result)

                    for result_type in all_result_types:
                        if method == 'all':
                            new_run_results[result_type] = list(itertools.chain.from_iterable([ag for i,ag in agg[result_type].items()]))
                            #print (run, result_type, new_run_results[result_type])
                        else:
                            new_run_results[result_type] = [group_val(np.asarray(ag),method) for i,ag in agg[result_type].items()]
                    new_all_results[run] = new_run_results
            nseries.append((test,build,new_all_results))
        return nseries

    # Extract the variable key so it becomes a serie
    def extract_variable_to_series(self, key, vars_values, all_results, dyns, build, script) -> Graph:
        if not key in dyns:
            raise ValueError("Cannot extract %s because it is not a dynamic variable (%s are)" % (key, ', '.join(dyns)))
        dyns.remove(key)
        series = []
        versions = []
        values = list(vars_values[key])
        del vars_values[key]
        try:
            #values.sort()
            pass
        except TypeError:
            print("ERROR : Cannot sort the following values :", values)
            return
        new_varsall = OrderedSet()
        for i, value in enumerate(values):
            newserie = OrderedDict()
            for run, run_results in all_results.items():
                #                    if (graph_variables and not run in graph_variables):
                #                        continue
                if run.variables[key] == value:
                    newrun = run.copy()
                    del newrun.variables[key]
                    newserie[newrun] = run_results
                    new_varsall.add(newrun)

            if type(value) is tuple:
                value = value[1]
            versions.append(value)
            nb = build.copy()
            nb._pretty_name = str(value)
            if len(self.graphmarkers) > 0:
                nb._marker = self.graphmarkers[i % len(self.graphmarkers)]
            series.append((script, nb, newserie))
            self.glob_legend_title = self.var_name(key)
        vars_all = list(new_varsall)
        if len(dyns) == 1:
            key = dyns[0]
            do_sort = True
        elif len(dyns) == 0:
            do_sort = True
        else:
            key = "Variables"
            do_sort = False
        do_sort = self.config_bool_or_in('graph_x_sort', key, default=do_sort)
        if (do_sort):
            vars_all.sort()
        graph = Graph(self)
        graph.do_sort = do_sort
        graph.key = key
        graph.vars_all = vars_all
        graph.vars_values = vars_values
        graph.series = series
        return graph

    # Convert a list of series to a graph object
    #  if the list has a unique item and there are dynamic variables, one
    #  dynamic variable will be extracted to make a list of serie
    def series_to_graph(self, series, dyns, vars_values, vars_all):
        nseries = len(series)

        ndyn = len(dyns)
        if self.options.do_transform and (nseries == 1 and ndyn > 0 and not self.options.graph_no_series and not (
                            ndyn == 1 and npf.all_num(vars_values[dyns[0]]) and len(vars_values[dyns[0]]) > 2) and dyns[0] != "time"):
            """Only one serie: expand one dynamic variable as serie, but not if it was plotable as a line"""
            script, build, all_results = series[0]
            if self.config("var_serie") and self.config("var_serie") in dyns:
                key = self.config("var_serie")
            else:
                key = None
                # First pass : use the non-numerical variable with the most points, but limited to 10
                n_val = 0
                nonums = []
                for i in range(ndyn):
                    k = dyns[i]
                    if k == 'time':
                        continue
                    if not npf.all_num(vars_values[k]):
                        nonums.append(k)
                        if len(vars_values[k]) > n_val and len(vars_values[k]) < 10:
                            key = k
                            n_val = len(vars_values[k])
                if key is None:
                    # Second pass if that missed, use the numerical variable with the less point if dyn==2 (->lineplot) else the most points
                    n_val = 0 if ndyn > 2 else 999
                    for i in range(ndyn):
                        k = dyns[i]
                        if k == 'time':
                            continue
                        if (ndyn > 2 and len(vars_values[k]) > n_val) or (ndyn <= 2 and len(vars_values[k]) < n_val):
                            key = k
                            n_val = len(vars_values[k])

            # Key is found, no the extraction itself
            if not key:
                key = 'time'
            if key:
                graph = self.extract_variable_to_series(
                                key=key,
                                vars_values=vars_values,
                                all_results=all_results,
                                dyns=dyns,
                                build=build,
                                script=script)

        else:
            self.glob_legend_title = None
            if ndyn == 0:
                key = "version"
                do_sort = False
            elif ndyn == 1:
                key = dyns[0]
                do_sort = True
            else:
                key = "Variables"
                do_sort = False
            graph = Graph(self)
            graph.key = key
            graph.do_sort = do_sort
            graph.vars_all = vars_all
            graph.vars_values = vars_values
            graph.series = series
        return graph

    def map_variables(self, map_k, fmap, series, vars_values):
            transformed_series = []
            for i, (test, build, all_results) in enumerate(series):
                new_results={}
                for run, run_results in all_results.items():
                    if map_k and not map_k in run.variables:
                        new_results[run] = run_results
                        continue
                    map_v = run.variables[map_k]
                    new_v = fmap.search(map_v)
                    if new_v:
                        if map_v in vars_values[map_k]:
                            vars_values[map_k].remove(map_v)
                        if new_v and new_v != " ":
                            run.variables[map_k] = new_v
                            vars_values[map_k].add(new_v)
                            if run in new_results:
                              for result_type, results in new_results[run].items():
                                nr = run_results[result_type]
                                for i in range(min(len(results),len(nr))):
                                    results[i] += nr[i]
                            else:
                              new_results[run] = run_results
                    else:
                        new_results[run] = run_results
                transformed_series.append((test, build, new_results))
            return transformed_series

    def graph(self, filename, options, fileprefix=None, graph_variables: List[Run] = None, title=False, series=None):
        """series is a list of triplet (script,build,results) where
        result is the output of a script.execute_all()"""
        self.options = options
        if self.options.graph_size is None:
            self.options.graph_size = plt.rcParams["figure.figsize"]
        if series is None:
            series = []

        # If no graph variables, use the first serie
        if graph_variables is None:
            graph_variables = OrderedSet()
            for serie in series:
                for run, results in serie[2].items():
                    graph_variables.add(run)

        # Get all scripts, and execute pypost
        for i, (test, build, all_results) in enumerate(series):
            self.scripts.add(test)

            if hasattr(test, 'pypost'):
                def common_divide(a,b):
                    m = min(len(a),len(b))
                    return np.array(a)[:m] / np.array(b)[:m]
                def results_divide(res,a,b):
                    for RUN, RESULTS in all_results.items():
                        if a in RESULTS and b in RESULTS:
                            all_results[RUN][res] = common_divide(RESULTS[a], RESULTS[b])
                vs = {'ALL_RESULTS': all_results, 'common_divide': common_divide, 'results_divide': results_divide}
                try:
                    exec(test.pypost.content, vs)
                except Exception as e:
                    print("ERROR WHILE EXECUTING PYPOST SCRIPT:")
                    print(e)


        if not series:
            print("No data...")
            return

        # Add series to a pandas dataframe
        if options.pandas_filename is not None:
            all_results_df=pd.DataFrame() # Empty dataframe
            for test, build, all_results in series:
                for i, (x) in enumerate(all_results):
                    try:

                        labels = [k[1] if type(k) is tuple else k for k,v in x.variables.items()]
                        x_vars = [[v[1] if type(v) is tuple else v for k,v in x.variables.items()]]
                        #x_vars = x.variables
                        print(x_vars)
                        x_vars=pd.DataFrame(x_vars,index=[0],columns=labels)
                        x_vars=pd.concat([pd.DataFrame({'build' :build.pretty_name()},index=[0]), pd.DataFrame({'test_index' :i},index=[0]), x_vars],axis=1)
                        x_data=pd.DataFrame.from_dict(all_results[x],orient='index').transpose() #Use orient='index' to handle lists with different lengths
                        if len(x_data) == 0:
                            continue
                        x_data['run_index']=x_data.index
                        x_vars = pd.concat([x_vars]*len(x_data), ignore_index=True)
                        x_df = pd.concat([x_vars, x_data],axis=1)
                        all_results_df = pd.concat([all_results_df,x_df],ignore_index = True, axis=0)
                    except Exception as e:
                        print("ERROR: When trying to export serie %s:" % build.pretty_name())
                        raise(e)

            # Save the pandas dataframe into a csv
            pandas_df_name=os.path.splitext(options.pandas_filename)[0] + ("-"+fileprefix if fileprefix else "") + ".csv"
            # Create the destination folder if it doesn't exist
            df_path = os.path.dirname(pandas_df_name)
            if df_path and not os.path.exists(df_path):
                os.makedirs(df_path)

            all_results_df.to_csv(pandas_df_name, index=True, index_label="index", sep=",", header=True)
            print("Pandas dataframe written to %s" % pandas_df_name)

        #Overwrite markers and lines from user
        self.graphmarkers = self.configlist("graph_markers")
        self.graphlines = self.configlist("graph_lines")

        # Combine variables as per the graph_combine_variables config parameter
        for tocombine in self.configlist('graph_combine_variables', []):
            if type(tocombine) is tuple:
                toname = tocombine[1]
                tocombine = tocombine[0]
            else:
                toname = tocombine
            tomerge = tocombine.split('+')
            newgraph_variables = []
            run_map = OrderedDict()
            newnames = set()
            for run in graph_variables:
                newrun = run.copy()
                vals = []
                for var, val in run.variables.items():
                    if var in tomerge:
                        del newrun.variables[var]
                        vals.append(str(val[1] if type(val) is tuple else val).strip())
                combname = ', '.join(OrderedSet(vals))
                newrun.variables[toname] = combname
                newnames.add(combname)
                newgraph_variables.append(newrun)
                run_map[run] = newrun

            if numericable(newnames):
                for run in newgraph_variables:
                    run.variables[toname] = get_numeric(run.variables[toname])
            del newnames

            graph_variables = newgraph_variables

            newseries = []
            for i, (test, build, all_results) in enumerate(series):
                new_all_results = {}
                for run, run_results in all_results.items():
                    newrun = run_map.get(run, None)
                    if newrun is not None:
                        new_all_results[newrun] = run_results
                newseries.append((test, build, new_all_results))
            series = newseries

        # Data transformation : reject outliers, transform list to arrays, filter according to graph_variables
        #   and divide results as per the var_divider
        filtered_series = []
        vars_values = OrderedDict()
        for i, (test, build, all_results) in enumerate(series):
            new_results = OrderedDict()
            for run, run_results in all_results.items():
                if run in graph_variables:
                    for result_type, results in run_results.items():
                        if self.options.graph_reject_outliers:
                            results = self.reject_outliers(np.asarray(results), test)
                        else:
                            results = np.asarray(results)
                        if self.options.graph_select_max:
                            results = np.sort(results)[-self.options.graph_select_max:]

                        ydiv = dataset.var_divider(test, "result", result_type)
                        if not results.any():
                            results=np.asarray([0])
                        new_results.setdefault(run.copy(), OrderedDict())[result_type] = results / ydiv

                    for k, v in run.variables.items():
                        vars_values.setdefault(k, OrderedSet()).add(v)

            if new_results:
                if len(self.graphmarkers) > 0:
                    build._marker = self.graphmarkers[i % len(self.graphmarkers)]
                filtered_series.append((test, build, new_results))
            else:
                print("No valid data for %s" % build)
        series = filtered_series
        if len(series) == 0:
            return

        #If graph_series_as_variables, take the series and make them as variables
        if self.config_bool('graph_series_as_variables',False):
            new_results = {}
            vars_values['serie'] = set()
            for i, (test, build, all_results) in enumerate(series):
                for run, run_results in all_results.items():
                    run.variables['serie'] = build.pretty_name()
                    vars_values['serie'].add(build.pretty_name())
                    new_results[run] = run_results
            series = [(test, build, new_results)]

        # Transform results to variables as the graph_result_as_variable config
        #  option. It is a dict in the format
        #  a+b+c:var_name[-result_name]
        #  i.e. the first is a + separated list of result and the second member
        #  a new name for the combined variable
        # or
        # a-(.*):var_name[-result_name]
        # Both will create a variable with a/b/c as values or all regex mateched values
        # Example:
        # Values for one run:
        # RESULT-CPU-0 53
        # RESULT-CPU-1 72
        # With CPU-(.*):LOAD it will create two runs
        # CPU=0 -> LOAD = 53
        # CPU=1 -> LOAD = 72
        for result_types, var_name in self.configdict('graph_result_as_variable', {}).items():
            if len(var_name.split('-')) > 1:
                result_name=var_name.split('-')[1]
                var_name=var_name.split('-')[0]
            else:
                result_name="result-" + var_name
            result_to_variable_map = []

            for result_type in result_types.split('+'):
                result_to_variable_map.append(result_type)

            exploded_vars_values = vars_values.copy()
            vvalues = OrderedSet()

            untouched_series = []
            exploded_series = []
            for i, (test, build, all_results) in enumerate(series):
                exploded_results = OrderedDict()
                untouched_results = OrderedDict()

                for run, run_results in all_results.items():
                    new_run_results_exp = OrderedDict() #Results that matched, key is the matched value
                    untouched_run_results = OrderedDict()

                    for result_type, results in run_results.items():
                        match = False
                        for stripout in result_to_variable_map:
                            m = re.match(stripout, result_type)
                            if m:
                                match = m.group(1) if len(m.groups()) > 0 else result_type
                                break
                        if match:
                            new_run_results_exp[match] = results
                        else:
                            untouched_run_results[result_type] = results

                    if len(new_run_results_exp) > 0:
                        if numericable(new_run_results_exp.keys()):
                            nn = {}
                            for k, v in  new_run_results_exp.items():
                                nn[get_numeric(k)] = v
                            new_run_results_exp = OrderedDict(sorted(nn.items()))

                        u = self.scriptconfig("var_unit", var_name, default="")
                        mult = u == 'percent' or u == '%'
                        if mult:
                            tot = 0
                            for result_type, results in new_run_results_exp.items():
                                tot += np.mean(results)
                        if True:
                            for extracted_val, results in new_run_results_exp.items(): #result-type
                                variables = run.variables.copy()
                                variables[var_name] = extracted_val
                                vvalues.add(extracted_val)
                                #nr = new_run_results.copy()
                                nr = {}
                                #If unit is percent, we multiply the value per the result
                                if mult:
                                    m = np.mean(results)
                                    tot += m
                                    for result_type in nr:
                                        nr[result_type] = nr[result_type].copy() * m / 100
                                nr.update({result_name: results})
                                exploded_results[Run(variables)] = nr


                    untouched_results[run] = untouched_run_results

                if exploded_results:
                    exploded_series.append((test, build, exploded_results))

                if untouched_results:
                    untouched_series.append((test, build, untouched_results))

            exploded_vars_values[var_name] = vvalues

            self.graph_group(series=exploded_series, vars_values=exploded_vars_values, filename=filename, fileprefix = fileprefix, title=title)
            series=untouched_series

        self.graph_group(series, vars_values, filename=filename, fileprefix = fileprefix, title=title)

    def graph_group(self, series, vars_values, filename, fileprefix, title):
        if len(series) == 0:
            print("No valid series...")
            return

        # List of static variables to use in filename
        statics = {}

        # Set lines types
        for i, (script, build, all_results) in enumerate(series):
            build._line = self.graphlines[i % len(self.graphlines)]
            build.statics = {}

        # graph_variables_as_series will force a variable to be considered as
        # a serie. This is different from var_serie which will define
        # what variable to use as a serie when there is only one serie
        for to_get_out in self.configlist('graph_variables_as_series', []):
            try:
                values = natsort.natsorted(vars_values[to_get_out], lambda x: x[1] if type(x) is tuple else x)
            except KeyError as e:
                print("WARNING : Unknown variable %s to export as serie" % to_get_out)
                print("Known variables : ",", ".join(vars_values.keys()))
                continue
            if len(values) == 1:
                statics[to_get_out] = list(values)[0]
            del vars_values[to_get_out]

            transformed_series = []
            for sindex, (test, build, all_results) in enumerate(series):
                new_series = OrderedDict()
                for value in values:
                    new_series[value] = OrderedDict()

                for run, run_results in all_results.items():
                    variables = run.variables.copy()
                    new_run_results = {}
                    value = variables[to_get_out]
                    del variables[to_get_out]
                    new_series[value][Run(variables)] = run_results

                for i, (value, data) in enumerate(new_series.items()):
                    nbuild = build.copy()
                    nbuild.statics = build.statics.copy()
                    nbuild._pretty_name = ' - '.join(([nbuild.pretty_name()] if len(series) > 1 or self.options.show_serie else []) + [ (str(value[1]) if not self.config_bool("graph_variables_explicit") else ("%s = %s" % (self.var_name(to_get_out), str(value[1]))) ) if type(value) is tuple else ("%s = %s" % (self.var_name(to_get_out), str(value)))  ])
                    if len(self.graphmarkers) > 0:
                        nbuild._marker = self.graphmarkers[i % len(self.graphmarkers)]
                    if len(series) == 1: #If there is one serie, expand the line types
                        nbuild._line = self.graphlines[sindex % len(self.graphlines)]

                    nbuild._color_index = sindex + 1
                    nbuild.statics[to_get_out] = value
                    transformed_series.append((test, nbuild, data))

            series = transformed_series

        #Map and combine variables values
        for map_k, fmap in self.configdict('graph_map',{}).items():
            fmap = Map(fmap)
            series = self.map_variables(fmap=fmap, map_k=map_k, series=series, vars_values=vars_values)

        m = self.configdict('graph_map_inline',{})
        if m:
            fmap = Map(None)
            fmap.update(m)
            for k in vars_values.keys():
                series = self.map_variables(fmap=fmap, map_k=str(k), series=series, vars_values=vars_values)

        #round values of a variable to a given precision, if it creates a merge, the list is appended
        for var, prec in self.configdict("var_round",{}).items():
            transformed_series = []
            prec = float(prec)
            for i, (test, build, all_results) in enumerate(series):
                new_all_results = OrderedDict()
                for run, run_results in all_results.items():
                    if var in run.variables:
                        v = roundf(run.variables[var], prec)
                        run.variables[var] = v
                        if run in new_all_results:
                            np.append(new_all_results[run], run_results)
                        else:
                            new_all_results[run] = run_results
                transformed_series.append((test, build, new_all_results))
            series = transformed_series


        # Apply a mathematical formula to results
        for result_type, fil in self.configdict("graph_filter",{}).items():
            transformed_series = []
            aeval = Interpreter()
            for i, (test, build, all_results) in enumerate(series):
                new_all_results = OrderedDict()
                def lam(x):
                    aeval.symtable['x'] = x
                    return aeval(fil)
                for run, run_results in all_results.items():
                    if result_type in run_results:
                        run_results[result_type] = list(filter(lam, run_results[result_type]))
                    new_all_results[run] = run_results
                transformed_series.append((test, build, new_all_results))
            series = transformed_series


        for key,method in self.configdict('var_aggregate').items():
            series = self.aggregate_variable(key=key,series=series,method=method)
            for k in key.split('+'):
                vars_values[k] = ['AGG']


        versions = []
        vars_all = OrderedSet()
        for i, (test, build, all_results) in enumerate(series):
            versions.append(build.pretty_name())
            for run, run_results in all_results.items():
                vars_all.add(run)
        vars_all = list(vars_all)
        vars_all.sort()

        dyns = []
        for k, v in vars_values.items():
            if len(v) > 1:
                dyns.append(k)
            else:
                if len(v) > 0:
                    statics[k] = list(v)[0]
                else:
                    print("ERROR: Variable %s has no values" % k)

        #Divide a serie by another
        prop = self.config('graph_series_prop')
        if prop:
            if len(series) > 1:
                series = Graph.series_prop(series, prop, self.configdict('graph_cross_reference').values())
                prop = False

        #Eventually overwrite label of series
        graph_series_label = self.config("graph_series_label")
        sv = self.config('graph_subplot_variable', None)
        graphs = []

        #Interpret title
        if title:
            v = {}
            v.update(statics)
            title=SectionVariable.replace_variables(v, title)

        if sv: #Only one supported for now
            graphs = [ None for v in vars_values[sv] ]
            for j,(script, build, all_results) in enumerate(series):
                graph = self.extract_variable_to_series(sv, vars_values.copy(), all_results, dyns.copy(), build, script)

                self.glob_legend_title = title #This variable has been extracted, the legend should not be the variable name in this case

                if graph_series_label:
                    for i, (test, build, all_results) in enumerate(series):
                        v = {}
                        v.update(statics)
                        v.update(build.statics)
                        build._pretty_name=SectionVariable.replace_variables(v, graph_series_label)

#                graph.title = title if title else self.var_name(sv)
#                if len(series) > 1:
#                    graph.title = build._pretty_name + " - " + graph.title
                s = graph.series.copy()
                for i,stuple in enumerate(s):
                    if graphs[i] is None:
                        graphs[i] = copy.copy(graph)
                        graphs[i].title = self.var_name(sv) + " = " + stuple[1]._pretty_name
                        graphs[i].series = list()

                    graphs[i].series.append(stuple)
                    graphs[i].series[j][1]._pretty_name = build._pretty_name
                assert(not sv in graph.vars_values)


            del dyns
            del vars_values
        else:
            graph = self.series_to_graph(series, dyns, vars_values, vars_all)
            graph.title = title
            graphs.append(graph)

        if prop:
            for graph in graphs:
                graph.series_prop(prop, self.configdict('graph_cross_reference').values())

        if len(graphs) > 0:
            self.plot_graphs(graphs, filename, fileprefix)


    def plot_graphs(self, graphs, filename, fileprefix):
        """
        This function will sort out the layout of the grid, according to the number of sublot, dual axis, etc...
        It will then properly call generate_plot_for_graph() for each of those subplots, and finaly save_fix.
        @graphs is a list of graph objects
        """
        assert(len(graphs) > 0)
        matched_set = set()

        text = self.config("graph_text")

        i_subplot = 0

        ret = {}

        #List of positions of plots on the sheet (also handle dual-axis plots)
        plots = OrderedDict()

        # For all graphs, find the various sub-plots
        graph = graphs[0]
        if len(graph.series) == 0:
            return
        data_types : AllXYEB = graph.dataset(kind=fileprefix)
        one_test,one_build,whatever = graph.series[0]

        if self.options.no_graph:
            return

        # Combine some results as subplots of a single plot. Expect a dictionary like THROUGHPUT+LATENCY:2 where the first list is the results to combine, and the second the number of columns to use for subplots, ignored for dual axis
        for i,(result_type_list, n_cols) in enumerate(self.configdict('graph_subplot_results', {}).items()):
            for result_type in re.split('[,]|[+]', result_type_list):
                matched = False
                for k in data_types.keys():
                    if re.match(result_type, k):
                        if variable.is_numeric(n_cols):
                            n_cols = get_numeric(n_cols)
                            subplot_legend_titles = [self.var_name("result",result_type=result_type)]
                        else:
                            subplot_legend_titles = re.split("[+]", n_cols)
                            n_cols = 1

                        plots.setdefault(i,([],n_cols,[]))
                        plots[i][0].append((k))
                        plots[i][2].extend(subplot_legend_titles)
                        matched_set.add(k)
                        matched = True
                if not matched:
                    print("WARNING: Unknown data type to include as subplot : %s" % result_type)

        # Unmatched plots are added as single subplots
        for result_type, data in sorted(data_types.items()):
            if result_type not in matched_set:
                plots[result_type] = ([result_type],1,[])

        max_cols = self.config("graph_max_cols", 2)
        graph_only = self.config("graph_only", [])
        for result_type, (figure,n_s_cols,subplot_legend_titles) in plots.items():
            if len(figure) == 1 and graph_only and not result_type in graph_only:
                print("Not graphing %s" % result_type)
                continue
            v_cols = len(graphs)
            v_lines = 1
            while v_cols > max_cols and v_cols > v_lines:
                v_cols = math.ceil(v_cols / 2)
                v_lines *= 2
            n_cols = v_cols * n_s_cols

            if len(self.configlist("graph_display_statics")) > 0:
                for stat in self.configlist("graph_display_statics"):
                    if text == '' or text[-1] != "\n":
                        text += "\n"
                    text += str(self.var_name(stat)) + " : " + ', '.join([str(val) for val in graph.vars_values[stat]])
            n_s_lines = math.ceil((len(figure) + (1 if text else 0)) / float(n_cols))
            n_lines = v_lines * n_s_lines
            fig_name = "subplot" + str(result_type)

            i_subplot = 0
            lgd = None
            extra_artists = []
            for graph in graphs:
                data_types = graph.dataset(kind=fileprefix)

                result = self.generate_plot_for_graph(
                    result_type, i_subplot, figure, n_cols, n_lines, graph.vars_values,
                    data_types, graph.dyns(), graph.vars_all, graph.key,
                    graph.subtitle if graph.subtitle else graph.title,
                    ret, subplot_legend_titles)

                if result is None:
                    continue
                result_type, lgd, a = result
                if lgd is not None:
                    extra_artists += [lgd]
                extra_artists += a

                i_subplot += len(figure)

            if text:
                plt.subplot(n_lines, n_cols, len(figure) + 1)
                plt.axis('off')
                plt.figtext(.05, (0.5 / (len(figure) + 1)), text.replace("\\n", "\n"), verticalalignment='center',
                            horizontalalignment='left')

            if len(figure) > 1:
                if i_subplot < len(figure) - 1:
                    return
                else:
                    result_type = fig_name
            if not filename:
                buf = io.BytesIO()
                plt.savefig(buf, format='png', bbox_extra_artists=(extra_artists,) if len(extra_artists) > 0 else [], bbox_inches='tight')
                buf.seek(0)
                ret[result_type] = buf.read()
            else:
                type_filename = npf.build_filename(one_test, one_build, filename if not filename is True else None, graph.statics(), 'pdf', type_str=(fileprefix +'-' if fileprefix else "") +result_type, show_serie=False)
                try:
                    plt.savefig(type_filename, bbox_extra_artists=extra_artists if len(extra_artists) > 0 else [],
                            bbox_inches='tight',
                            dpi=self.options.graph_dpi, transparent=True)
                    print("Graph of test written to %s" % type_filename)
                except Exception as e:
                    print("ERROR : Could not draw the graph!")
                    print(e)
                    traceback.print_exc()
                ret[result_type] = None
            plt.clf()
        return ret




    #Generate the plot of data_types at the given i/i_subplot position over n_cols/n_lines
    def generate_plot_for_graph(self, i, i_subplot, figure, n_cols, n_lines, vars_values, data_types, dyns, vars_all, key, title, ret, subplot_legend_titles):
            ndyn=len(dyns)
            subplot_type=self.config("graph_subplot_type")
            subplot_handles=[]
            axiseis = []
            savekey=key
            extra_artists = []

            #Get global plotting variables
            cross_reference =  self.configdict('graph_cross_reference')
            tick_params = self.configdict("graph_tick_params",default={})

            gcolor = self.configlist('graph_color')

            #A figure may be composed of multiple subplots if user asked for subplots OR shared axis
            # but each subplot may use broken axis that are in fact fake subplot
            for i_s_subplot, result_type in enumerate(figure):
                #Variable that depends on the figure
                key=savekey
                if not result_type in data_types:
                    continue
                data = data_types[result_type]

                #Number of broken axis
                brokenaxesY = self.get_var_lim(key="result", result_type=result_type)
                brokenaxesX = self.get_var_lim(key=key, result_type=None)

                # Add a dummy ratio if not given
                brokenaxesY = [ b if len(b) == 3 else b + [None] for b in brokenaxesY ]
                brokenaxesX = [ b if len(b) == 3 else b + [None] for b in brokenaxesX ]

                isubplot = int(i_subplot * len(figure) + i_s_subplot)

                if result_type in cross_reference:
                    cross_key = cross_reference[result_type]
                    xdata = data_types[cross_key]
                else:
                    cross_key=key
                    xdata = None

                subplot_type=self.config("graph_subplot_type")
                if len(figure) > 1 and subplot_type != "subplot":
                  for i, (x, y, e, build) in enumerate(data):
                    if self.config_bool("graph_subplot_unique_legend", False):
                        build._line=self.graphlines[i_subplot% len(self.graphlines)]
                    else:
                        build._line=self.graphlines[i_s_subplot% len(self.graphlines)]

                r = True

                nbrokenY = len(brokenaxesY)

                nbrokenX = len(brokenaxesX)

                if nbrokenY * nbrokenX > 1:
                    fig = plt.figure(constrained_layout=False)

                    heights = [ broken_axes_ratio(values) for values in brokenaxesY]
                    widths = [ broken_axes_ratio(values) for values in brokenaxesX]
                    spec = fig.add_gridspec(ncols=nbrokenX, nrows = nbrokenY, height_ratios = heights, width_ratios = widths)
                    spec.update(left=0.15, bottom=0.2)

                xname=self.var_name(cross_key)

                #For every broken axis
                for ibrokenY,(ymin,ymax, yratio) in enumerate(reversed(brokenaxesY)):
                  for ibrokenX,(xmin, xmax, xratio) in enumerate(brokenaxesX):
                    if nbrokenY > 1 or nbrokenX > 1:
                        if len(figure) > 1:
                            print("Broken axis with subplots is not supported!")
                            raise Exception("Not yet supported.")
                        axis = fig.add_subplot(spec[ibrokenY, ibrokenX])
                        shift = 0
                        ihandle = 0
                    else:
                        # Finding subplot indexes
                        if subplot_type=="subplot":
                            #if i_s_subplot > 0:
                            #    plt.setp(axiseis[0].get_xticklabels(), visible=False)
                            #axiseis[0].set_xlabel("")
                            axis = plt.subplot(n_lines * nbrokenY, n_cols * nbrokenX,
                                    isubplot + 1 + ibrokenY,
                                    sharex = axiseis[0] if ibrokenY > 0 and nbrokenY > 1 else None,
                                    sharey = axiseis[0] if ibrokenX > 0 and nbrokenX > 1 else None)
                            ihandle = 0
                            shift = 0
                        else: #subplot_type=="axis" for dual axis
                            if isubplot == 0:
                                fix,axis=plt.subplots(nbrokenY * nbrokenX)
                                ihandle = 0
                            elif isubplot == len(figure) - 1:
                                axis=axis.twinx()
                                ihandle = 1
                            else:
                                axis=axiseis[0]
                                ihandle = 0
                            if len(figure) > 1:
                                shift = isubplot + 1
                            else:
                                shift = 0

                    if ibrokenX==0 and ibrokenY==0:
                        axiseis.append(axis)
                        subplot_handles.append((axis,result_type,[]))
                    subplot_handles[ihandle][2].append(result_type)

                    #Handling colors
                    gi = {} #Index per-color
                    for i, (x, y, e, build) in enumerate(data):
                        if not gcolor and shift == 0 and not hasattr(build,"_color_set"):
                            build._color=graphcolorseries[0][i % len(graphcolorseries[0])]
                        else:
                            if hasattr(build,"_color_index"):
                                s = build._color_index
                                tot = [build._color_index for x,y,e,build in data].count(s)
                            elif gcolor:
                                s=gcolor[(i + isubplot*len(data)) % len(gcolor)]
                                tot = gcolor.count(s)
                            else:
                                s=shift
                                tot = len(data)

                            gi.setdefault(s,0)
                            if not is_numeric(s):
                                build._color=s
                            else:
                                slen = len(graphcolorseries[s % len(graphcolorseries)])
                                n = slen / tot
                                if n < 0:
                                    n = 1
                                #For the default colors we take them in order

                                if s == 0:
                                    f = gi[s]
                                else:
                                    f = round((gi[s] + (0.33 if gi[s] < tot / 2 else 0.66)) * n)

                                cserie = graphcolorseries[s % len(graphcolorseries)]

                                build._color=cserie[f % len(cserie)]
                            gi[s]+=1


                    axis.tick_params(**tick_params)


                    #This is the heart of the logic to find which kind of graph to use for the data

                    graph_type = False
                    default_doleg = True
                    if ndyn == 0:
                        default_doleg = False
                        if len(vars_all) == 1:
                            graph_type = "boxplot"
                        else:
                            graph_type = "simple_bar"
                    elif ndyn == 1 and len(vars_all) > 2 and npf.all_num(vars_values[key]):
                        graph_type = "line"
                    graph_types = self.config("graph_type",[])


                    if len(graph_types) > 0 and (type(graph_types[0]) is tuple or type(graph_types) is tuple):
                        if type(graph_types) is tuple:
                            graph_types = dict([graph_types])
                        else:
                            graph_types = dict(graph_types)
                        if result_type in graph_types:
                            graph_type = graph_types[result_type]
                        elif "default" in graph_types:
                            graph_type = graph_types["default"]
                        elif "result" in graph_types:
                            graph_type = graph_types["result"]
                        else:
                            graph_type = "line"

                    else:
                        if type(graph_types) is str:
                            graph_types = [graph_types]
                        graph_types.extend([graph_type, "line"])
                        graph_type = graph_types[isubplot if isubplot < len(graph_types) else len(graph_types) - 1]
                    if ndyn == 0 and graph_type == "line":
                        print("WARNING: Cannot graph %s as a line without dynamic variables" % graph_type)
                        graph_type = "simple_bar"
                    barplot = False
                    horizontal = False

                    try:
                        if graph_type == "simple_bar":
                            """No dynamic variables : do a barplot X=version"""
                            r, ndata = self.do_simple_barplot(axis, result_type, data, shift, isubplot)
                            barplot = True
                        elif graph_type == "line" or graph_type == "lines":
                            """One dynamic variable used as X, series are version line plots"""
                            r, ndata = self.do_line_plot(axis, key, result_type, data, data_types, shift, isubplot, xmin, xmax, xdata)
                        elif graph_type == "boxplot":
                            """A box plot, with multiple X values and series in color"""
                            r, ndata = self.do_box_plot(axis, key, result_type, data, xdata, shift, isubplot)
                            barplot = True #It's like a barplot, no formatting
                        elif graph_type == "cdf":
                            """CDF"""
                            r, ndata = self.do_cdf(axis, key, result_type, data, xdata, shift, isubplot)
                            default_doleg = True
                            ymin = 0
                            ymax = 100
                            xname=self.var_name(result_type)
                        elif graph_type == "heatmap":
                            """Heatmap"""
                            r, ndata = self.do_heatmap(axis, key, result_type, data, xdata, vars_values, shift, isubplot, sparse = False)
                            default_doleg = False
                            barplot = True
                        elif graph_type == "sparse_heatmap":
                            """sparse Heatmap"""
                            r, ndata = self.do_heatmap(axis, key, result_type, data, xdata, vars_values, shift, isubplot, sparse = True)
                            default_doleg = False
                            barplot = True

                        elif graph_type == "barh" or graph_type=="horizontal_bar":
                            r, ndata= self.do_barplot(axis,vars_all, dyns, result_type, data, shift, ibrokenY==0, horizontal=True)
                            barplot = True
                            horizontal = True
                        else:
                            """Barplot. X is all seen variables combination, series are version"""
                            r, ndata= self.do_barplot(axis,vars_all, dyns, result_type, data, shift, ibrokenY==0)
                            barplot = True
                    except Exception as e:
                        print("ERROR : could not graph %s" % result_type)
                        print(e)
                        print(traceback.format_exc())
                        continue
                    if not r:
                        continue

                    if self.config('graph_force_diagonal_labels'):
                        direction='diagonal'
                    else:
                        direction = self.scriptconfig('graph_label_dir', 'result', result_type=result_type, default=None)

                    if direction == 'diagonal' or direction == 'oblique':
                        plt.xticks(rotation = 45, ha='right')

                    else:
                        plt.xticks(rotation = 'vertical' if (ndata > 8 or direction =='vertical') else 'horizontal')


                    plt.ylim(ymin=ymin, ymax=ymax)
                    plt.xlim(xmin=xmin, xmax=xmax)

                    axis.tick_params(
                                       axis='both',          # changes apply to the x-axis
                                       which='both',      # both major and minor ticks are affected
                                       bottom = ibrokenY == nbrokenY-1,
                                       top = ibrokenY == 0,
                                       left = ibrokenX == 0,
                                       right = ibrokenX == nbrokenX-1,
                                       labelbottom = ibrokenY == nbrokenY-1,
                                       labelleft = ibrokenX == 0,
                                       direction = "in"
                                       )

                    axis.spines['bottom'].set_visible(ibrokenY == nbrokenY-1)
                    axis.spines['top'].set_visible(ibrokenY == 0)
                    axis.spines['right'].set_visible(ibrokenX == nbrokenX-1)
                    axis.spines['left'].set_visible(ibrokenX == 0)

                    type_config = "" if not result_type else "-" + result_type

                    lgd = None
                    if len(figure) == 1 or subplot_type=="subplot":
                        sl = 0
                    elif gcolor:
                        sl = gcolor[(isubplot * len(data)) % len(gcolor)] % len(legendcolors)
                    else:
                        sl = shift % len(legendcolors)

                    if legendcolors[sl]:
                        axis.yaxis.label.set_color(legendcolors[sl])
                        axis.tick_params(axis='y',colors=legendcolors[sl])

                    if ibrokenX == 0:
                        xunit = self.scriptconfig("var_unit", key, default="n,")
                        xformat = self.scriptconfig("var_format", key, default="")
                        isLog = self.config_bool_or_in('var_log', key, default=False)
                        base=2
                        baseLog = self.scriptconfig('var_log_base', key, default=None)
                        if baseLog:
                            isLog = True
                        if not isLog:
                            ax = data[0][0]
                            if npf.all_num(ax) and is_log(ax) is not False:
                                isLog = True
                                baseLog = is_log(ax)
                        thresh=1
                        if isLog and not barplot:
                            ax = data[0][0]
                            if ax is not None and len(ax) > 1:
                                if baseLog:
                                    if type(baseLog) is str:
                                        baseLog = baseLog.split("-")
                                        base = float(baseLog[0])
                                        if len(baseLog) > 1:
                                            thresh=float(baseLog[1])
                                    else:
                                        base=baseLog
                                        if min(ax) > 1:
                                            thresh=0
                                else:
                                    base = find_base(ax)
                                if thresh > 0:
                                    plt.xscale('symlog',base=base,linthresh=thresh )
                                else:
                                    if version.parse(matplotlib.__version__) >= version.parse("3.3.0"):
                                        plt.xscale('log',base=base)
                                    else:
                                        plt.xscale('log',basex=base)

                                xticks = data[0][0]
                                if not is_log(xticks) and xmin:
                                    i = xmin
                                    if xmax:
                                        top = xmax
                                    else:
                                        top = max(xticks)
                                    xticks = []
                                    while i <= top:
                                        xticks.append(i)
                                        if i <= 0:
                                            i = 1
                                        else:
                                            i = i * base
                                if len(xticks) > (float(self.options.graph_size[0]) * 1.5):
                                    n =int(math.ceil(len(xticks) / 8))
                                    index = np.array(range(len(xticks)))[1::n]
                                    if index[-1] != len(xticks) -1:
                                        index = np.append(index,[len(xticks)-1])
                                    xticks = np.delete(xticks,np.delete(np.array(range(len(xticks))),index))
#Weird code.
#                        if not xlims and min(data[0][0]) >= 1:
#                            xlims = [1]
#                            axis.set_xlim(xlims[0])
                                plt.xticks(xticks)
                            else:
                                plt.xscale('symlog')
                            plt.gca().xaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter('%d'))

                    if not barplot:
                        formatterSet, unithandled = self.set_axis_formatter(plt.gca().xaxis, xformat, xunit.strip(), isLog, True)

                    xticks = self.scriptconfig("var_ticks", key, default=None)
                    if xticks:
                        if isLog:
                            plt.gca().xaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
                        plt.xticks([get_numeric(x) for x in xticks.split('+')])

                    #background
                    bg = self.config("graph_background")
                    idx=None
                    if is_numeric(bg):
                        idx=get_numeric(bg)
                    elif is_bool(bg):
                        idx=15
                    else:
                        graph_bg = self.configdict("graph_background",{})
                        if result_type in graph_bg:
                            idx = int(graph_bg[result_type])

                    if idx is not None:
                        bgcolor = lighter(graphcolor[idx*2],0.12,255)
                        bgcolor2 = lighter(graphcolor[idx*2],0.03,255)
                        yl = axis.get_ylim()
                        xt = axis.get_xticks()
                        if len(xt) > 1:
                            w = xt[1] - xt[0]
                        else:
                            w = 1
                        b = axis.bar(xt, height=yl[1] * 2, width=w, color=[bgcolor,bgcolor2], zorder=-99999)
                        axis.set_ylim(yl[0],yl[1])

                    if nbrokenY * nbrokenX > 1:
                        if nbrokenY > 1:
                            d = .5  # proportion of vertical to horizontal extent of the slanted line
                            kwargs = dict(marker=[(-1, -d), (1, d)], markersize=12,
                                                  linestyle="none", color='k', mec='k', mew=1, clip_on=False)
                            if ibrokenX == 0:
                                if ibrokenY < nbrokenY - 1:
                                    axis.plot([0], [0], transform=axis.transAxes, **kwargs)
                                if ibrokenY > 0:
                                    axis.plot([0], [1], transform=axis.transAxes, **kwargs)
                            if ibrokenX == nbrokenX - 1:
                                if ibrokenY < nbrokenY -1:
                                    axis.plot([1], [0], transform=axis.transAxes, **kwargs)
                                if ibrokenY > 0:
                                    axis.plot([1], [1], transform=axis.transAxes, **kwargs)
                        if nbrokenX > 1:
                            d = .5  # proportion of vertical to horizontal extent of the slanted line
                            kwargs = dict(marker=[(-d, -1), (d, 1)], markersize=12,
                                                  linestyle="none", color='k', mec='k', mew=1, clip_on=False)
                            if ibrokenY == 0:
                                if ibrokenX < nbrokenX - 1:
                                    axis.plot([1], [1], transform=axis.transAxes, **kwargs)
                                if ibrokenX > 0:
                                    axis.plot([0], [1], transform=axis.transAxes, **kwargs)
                            if ibrokenY == nbrokenY - 1:
                                if ibrokenX < nbrokenX -1:
                                    axis.plot([1], [0], transform=axis.transAxes, **kwargs)
                                if ibrokenX > 0:
                                    axis.plot([0], [0], transform=axis.transAxes, **kwargs)

                    print_xlabel = self.config_bool_or_in('graph_show_xlabel', result_type)

                    print_ylabel = self.config_bool_or_in('graph_show_ylabel', result_type)
                    if nbrokenY * nbrokenX > 1:
                        if ibrokenX == 0 and ibrokenY==0:
                            # Just one time, set the axis labels

                            # FIXME: are these ratios ok for different font sizes and DPI?
                            # Likely they need to be scalated
                            if print_xlabel:
                                extra_artists.append(fig.text(0.5,0.03, xname,  transform=fig.transFigure))
                            if print_ylabel:
                                if horizontal:
                                    axis.set_xlabel(axis.yname)
                                else:
                                    axis.set_ylabel(axis.yname)
                            # We have 10% white bottom now
                            axis.yaxis.label.set_position((0,0.5 + 0.1))
                            axis.yaxis.label.set_transform(mtransforms.blended_transform_factory(mtransforms.IdentityTransform(), fig.transFigure))
                    else:
                        if print_xlabel:

                            if horizontal:
                                axis.set_ylabel(xname)
                            else:
                                axis.set_xlabel(xname)

                        if print_ylabel:
                            if horizontal:
                                axis.set_xlabel(axis.yname)
                            else:
                                axis.set_ylabel(axis.yname)

                if self.options.graph_size:
                    fig = plt.gcf()
                    fig.set_size_inches(self.options.graph_size[0], self.options.graph_size[1])

                if title and i_s_subplot == 0:
                    plt.title(title)

                try:

                    if nbrokenY * nbrokenX > 1:
                        plt.subplots_adjust(hspace=0.05 if nbrokenY > 1 else 0,wspace=0.05 if nbrokenX > 1 else 0)  # adjust space between axes
                    else:
                        plt.tight_layout()

                except Exception as e:
                    print("Could not make the graph fit. It may be because you have too many points or variables to graph")
                    print("Try reducing the number of dynamic variables : ")
                    for dyn in dyns:
                        print(dyn)
                    print(e)
                    return None

            legend_params = guess_type(self.configdict("graph_legend_params",default={}))
            lgd = None
            for ilegend,(axis, result_type, plots) in enumerate(subplot_handles):
                handles, labels = axis.get_legend_handles_labels()
                for i,label in enumerate(labels):
                    labels[i] = label.replace('_', ' ')
                labelsov = self.configlist("graph_labels", None)
                if labelsov:
                    labels = labelsov
                ncol = self.config("legend_ncol")
                if type(ncol) == list:
                    ncol = ncol[ilegend % len(ncol)]
                doleg = self.config_bool_or_in('graph_legend', result_type)
                if doleg is None:
                    if len(labels) == 1 and labels[0] in ('local','version'):
                        doleg = False
                        print("Legend not shown as there is only one serie with a default name. Set --config graph_legend=1 to force printing a legend.")
                    else:
                        doleg = True
                if default_doleg or doleg:
                    loc = self.config("legend_loc")
                    if type(loc) is dict or type(loc) is list:
                        loc = self.scriptconfig("legend_loc",key="result",result_type=result_type)
                    if subplot_type=="axis" and len(figure) > 1:
                      if self.config_bool("graph_subplot_unique_legend"):
                        if ilegend != len(subplot_handles) - 1 : continue
                        nhandles=[]
                        for handle in handles:
                            handle = copy.copy(handle)
                            handle.set_color('black')
                            if isinstance(handle, matplotlib.lines.Line2D):
                                handle.set_linestyle('')
                            nhandles.append(handle)
                        handles = nhandles
                        legend_title = self.glob_legend_title
                      else:
                        if not loc.startswith("outer"):
                            if self.configlist("subplot_legend_loc"):
                                loc=self.configlist("subplot_legend_loc")[ilegend]
                            else:
                                if ilegend == 0:
                                    loc = 'upper left'
                                else:
                                    loc = 'lower right'

                        else:
                            if ilegend > 0:
                                continue
                        legend_title = subplot_legend_titles[ilegend % len(subplot_legend_titles)]
                        if len(labels) == 1:
                            legend_title = None

                        if legend_title:
                            t = self.var_name(legend_title)
                            if print_ylabel:
                                axis.set_ylabel(t)

                        if len(plots) == len(labels):
                            labels = []
                            for p in plots:
                                labels.append(self.var_name("result",result_type=p))
                        elif len(plots) > 1:
                            nlabels = []
                            nlabel = len(labels) / len(plots)
                            for p in plots:
                                for i in range(int(nlabel)):
                                    nlabels.append(labels[i] + " - " + self.var_name("result",result_type=p))
                            labels = nlabels
                    else:
                        legend_title = self.glob_legend_title
                    if loc == "none":
                        continue
                    if legend_title == ' ' or legend_title == '_':
                        legend_title=None
                    if loc and loc.startswith("outer"):
                        loc = loc[5:].strip()
                        legend_bbox=self.configlist("legend_bbox")
                        lgd = axis.legend(handles=handles, labels=labels, loc=loc,bbox_to_anchor=(legend_bbox if legend_bbox and len(legend_bbox) > 1 else None), mode=self.config("legend_mode"), borderaxespad=0.,ncol=ncol, title=legend_title,bbox_transform=plt.gcf().transFigure,frameon=self.config_bool("legend_frameon"), **legend_params)
                    else:
                        lgd = axis.legend(handles=handles, labels=labels, loc=loc,ncol=ncol, title=legend_title, frameon=self.config_bool("legend_frameon"), **legend_params )
            return result_type, lgd, extra_artists


    def reject_outliers(self, result, test):
        return test.reject_outliers(result)

    def write_labels(self, rects, plt, color, idx = 0, each=False):
        if self.config('graph_show_values',False):
            prec =  self.config('graph_show_values',False)
            if is_numeric(prec):
                prec = get_numeric(prec)
            elif type(prec) is list and is_numeric(prec[idx]):
                prec = get_numeric(prec[idx])
            else:
                prec = 2
            def autolabel(rects, ax):
                for rect in rects:
                    if hasattr(rect, 'get_ydata'):
                        heights = rect.get_ydata()
                        xs = rect.get_xdata()
                        m=1.1
                    else:
                        heights = rect.get_height()
                        xs = rect.get_x() + rect.get_width()/2.
                        m=1.05

                    if not each:
                        xs = [np.mean(xs)]
                        heights = [np.mean(heights)]
                    for x,height in zip(xs,heights):
                        try:

                            if np.isnan(height):
                                continue
                        except Exception as e:
                            print("exception", e)
                            continue
                        ax.text(x, m*height,
                            ('%0.'+str(prec - 1)+'f') % height, color=color, fontweight='bold',
                             ha='center', va='bottom')
            autolabel(rects, plt)

    def do_simple_barplot(self,axis, result_type, data,shift=0,isubplot=0):
        i = 0
        interbar = 0.1

        x = np.asarray([s[0][0] for s in data])
        y = np.asarray([s[1][0] for s in data])
        mean = np.asarray([s[2][0][0] for s in data])
        std = np.asarray([s[2][0][1] for s in data])

        ndata = len(x)

        mask = np.isfinite(y)

        if len(x[mask]) == 0:
            return False, 0

        nseries = 1
        width = (1 - (2 * interbar)) / nseries

        ticks = np.arange(ndata) + 0.5

        self.format_figure(axis,result_type,shift)

        gcolor = self.configlist('graph_color')
        if not gcolor:
            gcolor = range(len(graphcolorseries))
        c = graphcolorseries[gcolor[isubplot % len(gcolor)]][0]
        rects = plt.bar(ticks, y, label=x, color=c, width=width, yerr=( y - mean + std, mean - y +  std))

        self.write_labels(rects, plt,c)

        plt.xticks(ticks, x)
        plt.gca().set_xlim(0, len(x))
        return True, ndata

    def do_box_plot(self, axis, key, result_type, data : XYEB, xdata : XYEB,shift=0,idx=0):

        self.format_figure(axis, result_type, shift, key=key)
        nseries = max([len(y) for y in [y for x,y,e,build in data]])

        labels=[]
        alllabels=[]
        allticks=[]
        allcolors=[]
        if len(data) > 30:
            print("WARNING : Not drawing more than 30 boxplots")
            return False, 0
        ipos=1
        for i, (x, ys, e, build) in enumerate(data):
            if nseries == 1 and np.isnan(ys).all():
                    continue
            if xdata:
                x = []
                for yi in range(len(xdata[i][2])):
                    x.append(np.mean(xdata[i][2][yi][2]))

            label = str(build.pretty_name())
            boxdata=[]
            pos = []
            for yi in range(nseries):
                y=e[yi][2]
                if nseries > 1:
                    pos.append(yi*len(data) + i + 1)
                else:
                    pos.append(ipos)
                ipos+=1
                y = np.asarray(y)
                boxdata.append(y[~np.isnan(y)])

                if i == 0:
                    if is_numeric(x[yi]):
                        v = get_numeric(x[yi])
                        if not np.isnan(v):
                            labels.append("%d" % v)
                        else:
                            labels.append(v)
                    else:
                        labels.append(x[yi])
            allticks.extend(pos)

            if not all(map(lambda x: np.isnan(x).all(), boxdata)):
                axis.plot([], c= build._color , label=label)
                alllabels.append(label)
                allcolors.append(build._color)


#                labels.append(build.pretty_name() + " "+ str(x[i]))
#            mean = np.array([e[i][0] for i in order])
#            std = np.array([e[i][1] for i in order])
#            ymin = np.array([np.min(e[i][2]) for i in order])
#            ymax = np.array([np.max(e[i][2]) for i in order])
            if len(boxdata) > 1000:
                print("WARNING: Not drawing more than 1000 points...")
                continue
            rects = axis.boxplot(boxdata, showfliers=self.config_bool_or_in("graph_show_fliers",result_type), positions = pos, widths=0.6 )
            plt.setp(rects['boxes'], color = build._color)
            plt.setp(rects['whiskers'], color = build._color)
            plt.setp(rects['caps'], color = build._color)
            plt.setp(rects['fliers'], color = build._color)
            plt.setp(rects['medians'], color = lighter(build._color,0.50,0))

            self.write_labels(rects['boxes'], plt, build._color)

        if nseries > 1:
            m = len(data)*nseries + 1
        else:
            m = ipos
        axis.set_xlim(0,m)

        if  nseries > 1:
            xticks = (np.asarray(range(nseries)) * len(data) ) + (len(data) / 2) + 0.5
            axis.set_xticks(xticks)
            axis.set_xticklabels(labels)
        else:
            axis.set_xticks(allticks)
            axis.set_xticklabels(alllabels)
            for i,(ticklabel, (x,y,e,build)) in enumerate(zip(axis.get_xticklabels(), data)):
                ticklabel.set_color(allcolors[i])

        return True, nseries

    def do_cdf(self, axis, key, result_type, data : XYEB, xdata : XYEB,shift=0,idx=0):

        self.format_figure(axis, result_type, shift, key=key, default_format="%d")
        nseries = max([len(y) for y in [y for x,y,e,build in data]])

        for i, (x, ys, e, build) in enumerate(data):
            for yi in range(nseries):
                y = e[yi][2]
                x2 = np.sort(y)
                N=len(y)
                y2 = np.arange(N) / float(N)

                axis.plot(x2, y2 * 100,  color = build._color, label = x[yi])
        axis.yname = "Cumulative distribution of "+axis.yname+" (%)"


        if nseries*len(data) > 4:
            print("Remember: CDF show the CDF of results for each point. Maybe you want to use var_aggregate={VAR1+VAR2+...+VARN:all}?")
        return True, nseries

    def do_heatmap(self, axis, key, result_type, data : XYEB, xdata : XYEB, vars_values: dict, shift=0, idx=0, sparse=False):
        self.format_figure(axis, result_type, shift, key=key)
        nseries = 0
        yvals = []
        for x,y,e,build in data:
            nseries = max(len(y),nseries)
            y = get_numeric(build._pretty_name)
            yvals.append(y)
        if not key in vars_values:
            print("WARNING: Heatmap with an axis of size 1")
            xvals = [1]
        else:
            xvals = list(vars_values[key])
        if sparse:
            xmin=min(xvals)
            xmax=max(xvals)
            ymin=min(yvals)
            ymax=max(yvals)
        else:
            xmin=0
            xmax=len(xvals) - 1
            ymin=0
            ymax=len(yvals) - 1


        matrix = np.empty(tuple((ymax-ymin + 1,xmax-xmin + 1)))
        matrix[:] = np.NaN

        if len(data) <= 1 or nseries <= 1:
            print("WARNING: Heatmap needs two dynamic variables. The map will have a weird ratio")
        for i, (x, ys, e, build) in enumerate(data):
            assert(isinstance(build,Build))
            for yi in range(nseries):
                if sparse:
                    matrix[ymax - yvals[i],xvals[yi] - xmin] = ys[yi]
                else:
                    matrix[ymax - i,yi] = ys[yi]

        axis.yname = self.glob_legend_title

        pos = axis.imshow(matrix)
        axis.figure.colorbar(pos, ax=axis)

        if sparse:
            prop = xmax-xmin / ymax-ymin
            if prop < 0:
                ny = min(len(yvals),9)
                nx = max(2,int(ny*prop))
            else:
                nx = min(len(xvals),9)
                ny = max(2,int(nx/prop))

            axis.set_yticks(np.linspace(0,ymax-ymin,num=ny))
            axis.set_yticklabels(["%d" % f for f in reversed(np.linspace(ymin,ymax,num=ny))])
            axis.set_xticks(np.linspace(0,xmax-xmin,num=nx))
            axis.set_xticklabels(["%d" % f for f in np.linspace(xmin,xmax,num=nx)])
        else:
            axis.set_xticks(range(xmax+1))
            axis.set_xticklabels(xvals)
            axis.set_yticks(range(ymax+1))
            axis.set_yticklabels(reversed(yvals))

        return True, nseries

    def do_line_plot(self, axis, key, result_type, data : XYEB, data_types, shift,idx,xmin,xmax,xdata = None):
        allmin = float('inf')
        allmax = 0
        drawstyle = self.scriptconfig('var_drawstyle',result_type,default='default')

        line_params = guess_type(self.configdict("graph_line_params",default={}))
        minX = None

        #Filters allow to use a different linestyle for points where a value of another variable is higher than zero. Only works for lines (no scatter)
        filters = self.configdict("graph_filter_by", default={})

        #Sync a variable, make all start at 0
        if self.config_bool_or_in("var_sync", key):
            for i, (x, y, e, build) in enumerate(data):
                if minX is None:
                    minX = min(x)
                else:
                    minX = min(minX,min(x))

        #For each series...
        for i, (x, y, e, build) in enumerate(data):
            self.format_figure(axis, result_type, shift, key=key)
            c = build._color

            if xdata:
                x = []
                for yi in range(len(xdata[i][2])):
                    x.append(np.mean(xdata[i][2][yi][2]))
            if not npf.all_num(x):
                if variable.numericable(x):
                    ax = [variable.get_numeric(v) for i, v in enumerate(x)]
                else:
                    ax = np.arange(len(x)) + 0.5 + i
            else:
                ax = x
            idx = np.arange(len(ax))[np.isfinite(y)]
#            ax = np.asarray([float(x) for x in ax])
#            idx = idx[ax[idx] < 100]
            order = idx[np.argsort(np.asarray(ax)[idx])]
            if len(order) == 0:
                continue
            shift = float(self.scriptconfig("var_shift", key=key, result_type=result_type, default=0))
            if minX is not None:
                ax = np.asarray([float(float(ax[i]) - shift - float(minX)) for i in order])
            else:
                ax = np.asarray([float(ax[i]) - shift for i in order])
            y = np.array([y[i] for i in order])

            if 'step' in drawstyle:
                s = y[np.isfinite(y)]
                if len(s) > 0 and len(y) > 0:
                    y[-1] = s[-1]

            ymin = np.array([np.min(e[i][2]) for i in order])
            ymax = np.array([np.max(e[i][2]) for i in order])
            mean = np.array([e[i][0] for i in order])
            std = np.array([e[i][1] for i in order])
#            y = gaussian_filter1d(y, sigma=5)
            smcon = self.config("graph_smooth")
            if smcon > 1:
                smax = np.max(ax) if xmax is None else max(np.max(ax), xmax)
                smin = np.min(ax) if xmin is None else min(np.min(ax), xmin)
                diff = smax - smin
                nx = np.arange(smin,smax + 1,step=diff/100)
                y,ymin,ymax,mean,std = smooth_range(ax,(y,ymin,ymax,mean,std),smcon*diff/100,nx)
                ax = nx

            lab = build.pretty_name()
            while lab.startswith('_'):
                lab = lab[1:]

            marker=build._marker

            fillstyle = self.config("graph_fillstyle")
            sm = self.scriptconfig("var_markers", key=key, result_type=result_type, default=None)
            if sm is not None:
                m = sm.split(';')
                marker = m[i % len(m)]

            if self.config_bool_or_in("graph_scatter", result_type):
                rects = axis.scatter(ax, y, label=lab, color=c,  marker=marker, facecolors=fillstyle)
            else:
                if result_type in filters:
                    #The result type to filter on
                    fl = filters[result_type]
                    if not fl in data_types:
                        print("ERROR: graph_filter_by's %s not found" % fl)
                        return
                    fl_data = data_types[fl]
                    fl_y = None
                    for fl_xyeb in fl_data:
                        if fl_xyeb[3] ==  build:
                            fl_y = np.array(fl_xyeb[1])
                            break
                    mask = fl_y > 1

                    if len(mask) != len(ax) or len(mask) != len(y):
                        print("ERROR: graph_filter_by cannot be applied, because length of X is %d, length of Y is %d but length of mask is %d" % (len(ax), len(y), len(mask)))
                        continue

                    rects = axis.plot(ax[~mask], y[~mask], label=lab, color=c, linestyle=build._line, marker=marker,markevery=(1 if len(ax) < 20 else math.ceil(len(ax) / 20)),drawstyle=drawstyle, fillstyle=fillstyle, **line_params)
                    mask = ndimage.binary_dilation(mask)
                    filter_linestyle = self.config('graph_filter_linestyle', default='--')
                    axis.plot(ax[mask], y[mask], label=None, color=lighter(c,0.9,255), linestyle=filter_linestyle, marker=marker,markevery=(1 if len(ax) < 20 else math.ceil(len(ax) / 20)),drawstyle=drawstyle, fillstyle=fillstyle, **line_params)
                else:
                    rects = axis.plot(ax, y, label=lab, color=c, linestyle=build._line, marker=marker,markevery=(1 if len(ax) < 20 else math.ceil(len(ax) / 20)),drawstyle=drawstyle, fillstyle=fillstyle,  **line_params)
            error_type = self.scriptconfig('graph_error', 'result', result_type=result_type, default = "bar").lower()
            if error_type != 'none':
                if error_type == 'bar' or (error_type == None and not self.config('graph_error_fill')):
                    if error_type == 'barminmax':
                        axis.errorbar(ax, ymin, yerr=(ymin,ymax), marker=' ', label=None, linestyle=' ', color=c, capsize=3)
                    else: #std dev
                        axis.errorbar(ax, mean, yerr=std, marker=' ', label=None, linestyle=' ', color=c, capsize=3)
                else: #error type is fill or fillminmax
                    if not np.logical_or(np.zeros(len(y)) == mean, np.isnan(y)).all():
                        if error_type=="fillminmax":
                            axis.fill_between(ax, ymin, ymax, color=c, alpha=.4, linewidth=0)
                        elif error_type=="fill50":
                            perc25 = smooth(np.array([np.percentile(e[i][2],25) for i in order]),sm)
                            perc75 = smooth(np.array([np.percentile(e[i][2],75) for i in order]),sm)
                            axis.fill_between(ax, perc25, perc75, color=c, alpha=.4, linewidth=0)
                        else:
                            axis.fill_between(ax, mean - std, mean + std, color=c, alpha=.4, linewidth=0)

            allmin = min(allmin, np.min(ax))
            allmax = max(allmax, np.max(ax))

            self.write_labels(rects, plt, build._color, idx, True)

        if xmin == float('inf'):
            return False, len(data)

        return True, len(data)


    def set_axis_formatter(self, axis, format, unit, isLog, compact=False):
        mult=1
        if (unit and unit[0] == 'k'):
            unit=unit[1:]
            mult = 1024 if unit[0] == "B" else 1000
        axis.set_minor_locator(NullLocator())
        if format:
            # Engineering format as eng+digits+unit
            if (format.lower().startswith("eng")):
                digits=None
                unit = unit
                f_split= format.split('-')
                if len(f_split) > 1:
                    digits=int(f_split[1])
                    if len(f_split) > 2:
                        unit = f_split[2]
                formatter = EngFormatter(places=digits, unit=unit, sep="\N{THIN SPACE}")
                axis.set_major_formatter(formatter)
                return True, True
            else:
                formatter = FormatStrFormatter(format)
                axis.set_major_formatter(formatter)
                return True, False
        elif unit.lower() == "byte":
            axis.set_major_formatter(Grapher.ByteFormatter(unit="B",compact=compact,k=1024,mult=mult))
            return True, True
        elif (unit.lower() == "bps" or unit.lower() == "byteps"):
            if compact:
                u = unit
            else:
                u = "Bits" if unit.lower() == "bps" else "Bytes"
            k = 1000 if unit.lower() == "bps" or "bit" in unit.lower() else 1024
            axis.set_major_formatter(Grapher.ByteFormatter(u,"" if u.lower().endswith("ps") else "/s", compact=compact, k=k, mult=mult))
            return True, True
        elif (unit.lower() == "us" or unit.lower() == "µs"):
            formatter = FuncFormatter(self.us)
            axis.set_major_formatter(formatter)
            return True, True
        elif (unit.lower() == "%" or unit.lower().startswith("percent")):
            def to_percent(y, position):
                s = str(100 * y)
                if matplotlib.rcParams['text.usetex'] is True:
                    return s + r'$\%$'
                else:
                    return s + '%'
            axis.set_major_formatter(FuncFormatter(to_percent))
            return True,False
        else:
            if not isLog:
                try:
                    axis.get_major_formatter().set_useOffset(False)
                except:
                    pass
                return True,False
        return False, False

    def format_figure(self, axis, result_type, shift, key = None, default_format = None):
        yunit = self.scriptconfig("var_unit", "result", default="", result_type=result_type)
        yformat = self.scriptconfig("var_format", "result", default=default_format, result_type=result_type)
        yticks = self.scriptconfig("var_ticks", "result", default=None, result_type=result_type)
        shift = int(shift)
        tick_params = self.configdict("graph_tick_params",default={})
        if self.config_bool_or_in('var_grid',result_type) or self.config_bool_or_in('var_grid',"result"):
            axis.grid(True,color=gridcolors[shift], axis="y" if not self.config_bool_or_in('var_grid',key) else "both", **({"linestyle":self.config("graph_grid_linestyle")} if "grid_linestyle" not in tick_params else {}) )
            #linestyle=self.graphlines[( shift - 1 if shift > 0 else 0) % len(self.graphlines)]
            axis.set_axisbelow(True)
        isLog = False
        baseLog = self.scriptconfig('var_log_base', "result",result_type=result_type, default=None)
        if baseLog:
            baseLog = baseLog.split('-')
            if len(baseLog) == 2:
                thresh = float(baseLog[1])
            else:
                thresh=1
            baseLog = float(baseLog[0])
            plt.yscale('symlog', base=baseLog, linthresh=thresh)
            isLog = True
        elif self.result_in_list('var_log', result_type):
            plt.yscale('symlog' if yformat else 'log')
            isLog = True
        whatever, handled = self.set_axis_formatter(axis.yaxis,yformat,yunit,isLog,True)
        yname = self.var_name("result", result_type=result_type)
        if yname != "result":
            if not handled and not '(' in yname and yunit and yunit.strip():
                yname = yname + ' (' + yunit + ')'
        axis.yname = yname

        if yticks:
            ticks = [variable.get_numeric(npf.parseUnit(y)) for y in yticks.split('+')]
            plt.yticks(ticks)

    def do_barplot(self, axis,vars_all, dyns, result_type, data, shift, show_vals, horizontal=False):
        nseries = len(data)

        self.format_figure(axis,result_type,shift)

        # If more than 20 bars, do not print bar edges
        maxlen = max([len(serie_data[0]) for serie_data in data])

        if nseries * maxlen > 20:
            edgecolor = "none"
            interbar = 0.05
        else:
            edgecolor = None
            interbar = 0.1

        interbar = self.config('graph_bar_inter', default=interbar)
        stack = self.config_bool('graph_bar_stack')
        do_hatch = self.config_bool('graph_bar_hatch', default=False)
        n_series = len(vars_all)
        bars_per_serie = 1 if stack else len(data)
        ind = np.arange(n_series)
        patterns = ('-', '+', 'x', '\\', '*', 'o', 'O', '.')
        width = (1 - (2 * interbar)) / bars_per_serie
        if horizontal:
            func=axis.barh
            ticks = plt.yticks
        else:
            func=axis.bar
            ticks = plt.xticks

        if stack:
            last = 0
            for i, (x, y, e, build) in enumerate(data):
                y = np.asarray([0.0 if np.isnan(x) else x for x in y])
                last = last + y

            for i, (x, y, e, build) in enumerate(data):
                y = np.asarray([0.0 if np.isnan(x) else x for x in y])
                std = np.asarray([std for mean,std,raw in e])
                rects = func(ind, last, width,
                    label=str(build.pretty_name()), color=build._color,
                    yerr=std if not horizontal else None, xerr=std if horizontal else None,
                    edgecolor=edgecolor)
                last = last - y
        else:
            for i, (x, y, e, build) in enumerate(data):
                std = np.asarray([std for mean,std,raw in e])
                fx = interbar + ind + (i * width)
                rects = func(fx, y, width,
                    label=str(build.pretty_name()), color=lighter(build._color, 0.6, 255) if do_hatch else build._color,
                    yerr=std if not horizontal else None, xerr=std if horizontal else None,
                    edgecolor=lighter(build._color, 0.6, 0) if do_hatch else edgecolor, hatch=patterns[i] if do_hatch else None)
                if show_vals:
                    self.write_labels(rects, plt, build._color)

        ss = self.combine_variables(vars_all, dyns)

        if not bool(self.config_bool('graph_x_label', True)):
            ss = ["" for i in range(n_series)]

        ticks(ind if stack else interbar + ind + (width * (len(data) - 1) / 2.0), ss,
                   rotation='vertical' if (sum([len(s) for s in ss]) > 80) and not horizontal  else 'horizontal')
        return True, len(data)
