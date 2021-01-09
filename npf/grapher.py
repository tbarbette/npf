import io
import math
import re
import natsort
from orderedset._orderedset import OrderedSet
import copy
import traceback

from collections import OrderedDict
from typing import List
import numpy as np
from pygtrie import Trie

from npf.types import dataset
from npf.types.dataset import Run, XYEB, group_val
from npf.variable import is_log, is_numeric, get_numeric, numericable, get_bool, is_bool
from npf.section import SectionVariable
from npf import npf, variable

import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42
import matplotlib.pyplot as plt
from matplotlib.ticker import LinearLocator, ScalarFormatter, Formatter, MultipleLocator, NullLocator
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, FormatStrFormatter
import matplotlib.transforms as mtransforms

import itertools
import math
import os
import webcolors

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


class Graph:
    def __init__(self, grapher:'Grapher'):
        self.grapher = grapher
        self.subtitle = None
        self.data_types = None

    def statics(self):
        return dict([(var,list(values)[0]) for var,values in self.vars_values.items() if len(values) == 1])

    def dyns(self):
        return [var for var,values in self.vars_values.items() if len(values) > 1]

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
    def series_prop(self, prop, exclusions = []):
            series = self.series
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
                        if result_type not in exclusions:
                            results = results / base * abs(prop) + prop if prop < 0 else 0

                        run_results[result_type] = results
                    new_results[run] = run_results
                newseries.append((script, build, new_results))
            self.series = newseries


class Grapher:
    def __init__(self):
        self.scripts = set()
        self._config_cache = {}

    def config_bool(self, var, default=None):
        val = self.config(var, default)
        return get_bool(val)

    def config_bool_or_in(self, var, obj, default=None):
        val = self.config(var, default)

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

            if var_lim.startswith('-'):
                n = var_lim[1:].split('-',1)
                n[0] = "-"+n[0]
            else:
                n = var_lim.split('-',1)
            try:
              if len(n) == 2 and n[1] != "":
                ymin, ymax = (npf.parseUnit(x) for x in n)
              else:
                f=float(n[0])
                if f==0:
                    ymin=f
                else:
                    ylim=f
            except Exception as e:
                print(e)
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
                return (pres + "G%s"+ps) % (x / (k*k*k), unit)
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
        for i,(testie, build, all_results) in enumerate(series):
            aggregates = OrderedDict()
            for run, run_results in all_results.items():
                    #                    if (graph_variables and not run in graph_variables):
                    #                        continue
                newrun = run.copy()
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
                            print (run, result_type, new_run_results[result_type])
                        else:
                            new_run_results[result_type] = [group_val(np.asarray(ag),method) for i,ag in agg[result_type].items()]
                    new_all_results[run] = new_run_results
            nseries.append((testie,build,new_all_results))
        return nseries

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
                # First pass : use the non-numerical variable with the most points
                n_val = 0
                nonums = []
                for i in range(ndyn):
                    k = dyns[i]
                    if k == 'time':
                        continue
                    if not npf.all_num(vars_values[k]):
                        nonums.append(k)
                        if len(vars_values[k]) > n_val:
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
            for i, (testie, build, all_results) in enumerate(series):
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
                transformed_series.append((testie, build, new_results))
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

        # Get all scripts
        for i, (testie, build, all_results) in enumerate(series):
            self.scripts.add(testie)

        # Add series to a pandas dataframe
        if options.pandas_filename is not None:
            all_results_df=pd.DataFrame() # Empty dataframe
            for testie, build, all_results in series:
                for i, (x) in enumerate(all_results):
                    x_vars=pd.DataFrame(x.variables,index=[0])
                    x_vars=pd.concat([pd.DataFrame({'build' :build.pretty_name()},index=[0]), pd.DataFrame({'test_index' :i},index=[0]), x_vars],axis=1)
                    x_data=pd.DataFrame.from_dict(all_results[x],orient='index').transpose() #Use orient='index' to handle lists with different lengths
                    x_data['run_index']=x_data.index
                    x_vars = pd.concat([x_vars]*len(x_data), ignore_index=True)
                    x_df = pd.concat([x_vars, x_data],axis=1)
                    all_results_df= all_results_df.append(x_df,ignore_index = True)

            # Save the pandas dataframe into a csv
            pandas_df_name=options.pandas_filename.split(".")[0] +"-pandas" + ".csv"
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
            for i, (testie, build, all_results) in enumerate(series):
                new_all_results = {}
                for run, run_results in all_results.items():
                    newrun = run_map.get(run, None)
                    if newrun is not None:
                        new_all_results[newrun] = run_results
                newseries.append((testie, build, new_all_results))
            series = newseries

        # Data transformation : reject outliers, transform list to arrays, filter according to graph_variables
        #   and divide results as per the var_divider
        filtered_series = []
        vars_values = OrderedDict()
        for i, (testie, build, all_results) in enumerate(series):
            new_results = OrderedDict()
            for run, run_results in all_results.items():
                if run in graph_variables:
                    for result_type, results in run_results.items():
                        if self.options.graph_reject_outliers:
                            results = self.reject_outliers(np.asarray(results), testie)
                        else:
                            results = np.asarray(results)
                        if self.options.graph_select_max:
                            results = np.sort(results)[-self.options.graph_select_max:]

                        ydiv = dataset.var_divider(testie, "result", result_type)
                        if not results.any():
                            results=np.asarray([0])
                        new_results.setdefault(run.copy(), OrderedDict())[result_type] = results / ydiv

                    for k, v in run.variables.items():
                        vars_values.setdefault(k, OrderedSet()).add(v)

            if new_results:
                if len(self.graphmarkers) > 0:
                    build._marker = self.graphmarkers[i % len(self.graphmarkers)]
                filtered_series.append((testie, build, new_results))
            else:
                print("No valid data for %s" % build)
        series = filtered_series
        if len(series) == 0:
            return

        #If graph_series_as_variables, take the series and make them as variables
        if self.config_bool('graph_series_as_variables',False):
            new_results = {}
            vars_values['serie'] = set()
            for i, (testie, build, all_results) in enumerate(series):
                for run, run_results in all_results.items():
                    run.variables['serie'] = build.pretty_name()
                    vars_values['serie'].add(build.pretty_name())
                    new_results[run] = run_results
            series = [(testie, build, new_results)]

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
            for i, (testie, build, all_results) in enumerate(series):
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
#                            if tot <= 99:
#                                new_run_results_exp['Other'] = [100-tot]

#                        if var_name in run.variables:
#                            results = new_run_results_exp[run.variables[var_name]]
#                            nr = new_run_results.copy()
                            #If unit is percent, we multiply the value per the result
#                            if mult:
#                                m = np.mean(results)
#                                tot += m
#                                for result_type in nr:
#                                    nr[result_type] = nr[result_type].copy() * m / 100
 #                           nr.update({result_name: results})
#
#                            new_results[run] = nr
#                        else:
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
                    exploded_series.append((testie, build, exploded_results))

                if untouched_results:
                    untouched_series.append((testie, build, untouched_results))
#                if vvalues:
                    #if not npf.all_num(vvalues):
                    #    raise Exception("Cannot transform series %s as the following are not all numerical : %s " % (result_types, vvalues))

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
                values = natsort.natsorted(vars_values[to_get_out])
            except KeyError as e:
                print("ERROR : Unknown variable %s to export as serie" % to_get_out)
                print("Known variables : ",vars_values.keys())
                continue
            if len(values) == 1:
                statics[to_get_out] = list(values)[0]
            del vars_values[to_get_out]

            transformed_series = []
            for sindex, (testie, build, all_results) in enumerate(series):
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
                    nbuild._pretty_name = ' - '.join(([nbuild.pretty_name()] if len(series) > 1 or self.options.show_serie else []) + ["%s = %s" % (self.var_name(to_get_out), str(value))])
                    if len(self.graphmarkers) > 0:
                        nbuild._marker = self.graphmarkers[i % len(self.graphmarkers)]
                    if len(series) == 1: #If there is one serie, expand the line types
                        nbuild._line = self.graphlines[sindex % len(self.graphlines)]

                    nbuild._color_index = sindex + 1
                    nbuild.statics[to_get_out] = value
                    transformed_series.append((testie, nbuild, data))

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
            prec = int(prec)
            for i, (testie, build, all_results) in enumerate(series):
                new_all_results = OrderedDict()
                for run, run_results in all_results.items():
                    if var in run.variables:
                        run.variables[var] = round(run.variables[var], prec)
                        if run in new_all_results:
                            np.append(new_all_results[run][result_type], run_results[result_type])
                        else:
                            new_all_results[run] = run_results
                transformed_series.append((testie, build, new_all_results))
            series = transformed_series

        for key,method in self.configdict('var_aggregate').items():
            series = self.aggregate_variable(key=key,series=series,method=method)
            vars_values[key] = ['AGG']

        versions = []
        vars_all = OrderedSet()
        for i, (testie, build, all_results) in enumerate(series):
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

        graph_series_label = self.config("graph_series_label")
        sv = self.config('graph_subplot_variable', None)
        graphs = []

        if sv:
            for script, build, all_results  in series:

                graph = self.extract_variable_to_series(sv, vars_values.copy(), all_results, dyns.copy(), build, script)
                if prop:
                    graph.series_prop(prop,  self.configdict('graph_cross_reference').values())
                if graph_series_label:
                    for i, (testie, build, all_results) in enumerate(series):
                        v = {}
                        v.update(statics)
                        v.update(build.statics)
                        build._pretty_name=SectionVariable.replace_variables(v, graph_series_label)

                graph.title = title if title else self.var_name(sv)
                if len(series) > 0:
                    graph.title = build._pretty_name + " - " + graph.title
                assert(not sv in graph.vars_values)
                graphs += graph.split_for_series()
            del dyns
            del vars_values
        else:
            graph = self.series_to_graph(series, dyns, vars_values, vars_all)
            if prop:
                graph.series_prop(prop, self.configdict('graph_cross_reference').values())
            graph.title = title
            graphs.append(graph)

        if len(graphs) > 0:
            self.plot_graphs(graphs, filename, fileprefix)


    def plot_graphs(self, graphs, filename, fileprefix):
        """
        Each graph is a dataset that contains multiple result types, there may be multiple graphs if there are multiple series.
        There may be multiple graphs in the case of regression tests for instance
        """
        assert(len(graphs) > 0)
        matched_set = set()

        text = self.config("graph_text")

        i_subplot = 0

        ret = {}

        plots = OrderedDict()

        # For all graphs, find the various sub-plots
        graph = graphs[0]
        if len(graph.series) == 0:
            return
        data_types = graph.dataset(kind=fileprefix)
        one_testie,one_build,whatever = graph.series[0]

        if self.options.no_graph:
            return
        # Combine some results as subplots of a single plot
        for i,(result_type_list, n_cols) in enumerate(self.configdict('graph_subplot_results', {}).items()):
            for result_type in re.split('[,]|[+]', result_type_list):
                matched = False
                for k in data_types.keys():
                    if re.match(result_type, k):
                        if variable.is_numeric(n_cols):
                            n_cols = variable.get_numeric(n_cols)
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
            for graph in graphs:
                data_types = graph.dataset(kind=fileprefix)

                result = self.generate_plot_for_graph(result_type, i_subplot, figure, n_cols, n_lines, graph.vars_values, data_types, graph.dyns(), graph.vars_all, graph.key, graph.subtitle if graph.subtitle else graph.title, ret, subplot_legend_titles)
                if result is None:
                    continue
                result_type, lgd = result

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
                plt.savefig(buf, format='png', bbox_extra_artists=(lgd,) if lgd else [], bbox_inches='tight')
                buf.seek(0)
                ret[result_type] = buf.read()
            else:
                type_filename = npf.build_filename(one_testie, one_build, filename if not filename is True else None, graph.statics(), 'pdf', type_str=(fileprefix +'-' if fileprefix else "") +result_type, show_serie=False)
                try:
                    plt.savefig(type_filename, bbox_extra_artists=(lgd,) if lgd else [], bbox_inches='tight', dpi=self.options.graph_dpi, transparent=True)
                    print("Graph of test written to %s" % type_filename)
                except Exception as e:
                    print("ERROR : Could not draw the graph!")
                    print(e)
                ret[result_type] = None
            plt.clf()
        return ret

    def generate_plot_for_graph(self, i, i_subplot, figure, n_cols, n_lines, vars_values, data_types, dyns, vars_all, key, title, ret, subplot_legend_titles):
            ndyn=len(dyns)
            subplot_type=self.config("graph_subplot_type")
            subplot_handles=[]
            axiseis = []
            savekey=key

            #Get global plotting variables
            cross_reference =  self.configdict('graph_cross_reference')
            tick_params = self.configdict("graph_tick_params",default={})
            gcolor = self.configlist('graph_color')

            #A figure may be composed of multiple subplots if user asked for subplots OR shared axis
            # but each subplot may use broken axis that are in fact fake subplot
            for i_s_subplot, result_type in enumerate(figure):
                #Variable that depends on the figure
                key=savekey
                data = data_types[result_type]

                #Number of broken axis
                brokenaxesY = self.get_var_lim(key="result", result_type=result_type)
                brokenaxesX = self.get_var_lim(key=key, result_type=None)

                isubplot = int(i_subplot * len(figure) + i_s_subplot)

                if result_type in cross_reference:
                    cross_key = cross_reference[result_type]
                    xdata = data_types[cross_key]
                else:
                    cross_key=key
                    xdata = None

                if len(figure) > 1:
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
                    spec = fig.add_gridspec(ncols=nbrokenX, nrows = nbrokenY, height_ratios=[ymax-ymin if( ymax is not None and ymin is not None) else 1 for ymin,ymax in reversed(brokenaxesY)],width_ratios=[xmax-xmin if (xmax is not None and xmin is not None) else 1 for xmin,xmax in reversed(brokenaxesX)])

                xname=self.var_name(cross_key)
                #For every broken axis
                for ibrokenY,(ymin,ymax) in enumerate(reversed(brokenaxesY)):
                  for ibrokenX,(xmin, xmax) in enumerate(brokenaxesX):
                    if nbrokenY > 1:
                        if len(figure) > 1:
                            print("Broken axis with subplots is not supported!")
                        axis = fig.add_subplot(spec[ibrokenY, ibrokenX])
                        shift = 0
                        ihandle = 0
                    else:
                        # Finding subplot indexes
                        if subplot_type=="subplot":
                            if i_s_subplot > 0:
                                plt.setp(axiseis[0].get_xticklabels(), visible=False)
                                #axiseis[0].set_xlabel("")
                            axis = plt.subplot(n_lines * nbrokenY, n_cols * nbrokenX, isubplot + 1 + ibrokenY, sharex=axiseis[0] if ibrokenY > 0 and nbrokenY > 1 else None, sharey = axiseis[0] if ibrokenX > 0 and nbrokenX > 1 else None)
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

                    if not axis in axiseis:
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
                            slen = len(graphcolorseries[s % len(graphcolorseries)])
                            n = slen / tot
                            if n < 0:
                                n = 1
                            #For the default colors we take them in order
                            if s == 0:
                                f = gi[s]
                            else:
                                f = round((gi[s] + (0.33 if gi[s] < tot / 2 else 0.66)) * n)
                            gi[s]+=1
                            cserie = graphcolorseries[s % len(graphcolorseries)]
                            build._color=cserie[f % len(cserie)]



                    axis.tick_params(**tick_params)

                    graph_type = False
                    if ndyn == 0:
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


                    try:
                        if graph_type == "simple_bar":
                            """No dynamic variables : do a barplot X=version"""
                            r = self.do_simple_barplot(axis,result_type, data, shift, isubplot)
                            barplot = True
                        elif graph_type == "line":
                            """One dynamic variable used as X, series are version line plots"""
                            r = self.do_line_plot(axis, key, result_type, data,shift, isubplot, xdata)
                        elif graph_type == "boxplot":
                            """One dynamic variable used as X, series are version line plots"""
                            r = self.do_box_plot(axis, key, result_type, data, xdata, shift, isubplot)
                        else:
                            """Barplot. X is all seen variables combination, series are version"""
                            self.do_barplot(axis,vars_all, dyns, result_type, data, shift)
                            barplot = True
                    except Exception as e:
                        print("ERROR : could not graph %s" % result_type)
                        print(e)
                        print(traceback.format_exc())
                        continue
                    if not r:
                        continue

                    plt.ylim(ymin=ymin, ymax=ymax)
                    plt.xlim(xmin=xmin, xmax=xmax)

                    if nbrokenY > 1:
                        if ibrokenY == 0:
                            # hide the spines between ax and ax2
                            axis.spines['bottom'].set_visible(False)
                            axis.xaxis.tick_top()
                            axis.tick_params(labeltop=False)  # don't put tick labels at the top
                            if ibrokenX == 0:
                               axis.yaxis.label.set_transform(mtransforms.blended_transform_factory(
                                       mtransforms.IdentityTransform(), fig.transFigure # specify x, y transform
                                              )) # changed from default blend (IdentityTransform(), a[0].transAxes)
                               axis.yaxis.label.set_position((0, 0.5))
                               axis.set_ylabel(axis.yname)
                        else:
                            axis.spines['top'].set_visible(False)
                            axis.xaxis.tick_bottom()
#                            fig.text(0.05, 0.5, axis.yname, va='center', rotation='vertical')

                    else:
                        plt.ylabel(axis.yname)


                    print_xlabel = self.config_bool_or_in('graph_show_xlabel', result_type)

                    if nbrokenX > 1:
                        if ibrokenX == 0:
                            # hide the spines between ax and ax2
                            axis.spines['right'].set_visible(False)
                            axis.yaxis.tick_left()
                            axis.tick_params(labelleft=False)  # don't put tick labels at the top
#                            axis.xaxis.label.set_transform(mtransforms.blended_transform_factory(
#                                       mtransforms.IdentityTransform(), fig.transFigure # specify x, y transform
#                                              )) # changed from default blend (IdentityTransform(), a[0].transAxes)
#                            axis.xaxis.label.set_position((0, 0.5))
                            if ibrokenY == nbrokenY - 1:
                                axis.set_xlabel(xname)
                        else:
                            axis.spines['left'].set_visible(False)
                            axis.yaxis.tick_right()
#                            fig.text(0.05, 0.5, axis.yname, va='center', rotation='vertical')

                    else:
                        if print_xlabel:
                            plt.xlabel(xname)

                    type_config = "" if not result_type else "-" + result_type

                    lgd = None
                    if len(figure) == 1:
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
                        isLog = key in self.config('var_log', {})
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
                                else:
                                    base = find_base(ax)
                                if thresh > 0:
                                    plt.xscale('symlog',basex=base,linthreshx=thresh )
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
                        plt.xticks([variable.get_numeric(x) for x in xticks.split('+')])


                    #background
                    graph_bg = self.configdict("graph_background",{})
                    if result_type in graph_bg:
                        idx = int(graph_bg[result_type])
                        bgcolor = lighter(graphcolor[idx],0.12,255)
                        bgcolor2 = lighter(graphcolor[idx],0.03,255)
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
                            if ibrokenX == 1:
                                if ibrokenY < nbrokenY -1:
                                    axis.plot([1], [0], transform=axis.transAxes, **kwargs)
                                if ibrokenY > 0:
                                    axis.plot([1], [1], transform=axis.transAxes, **kwargs)



                if self.options.graph_size:
                    fig = plt.gcf()
                    fig.set_size_inches(self.options.graph_size[0], self.options.graph_size[1])

                if title and i_s_subplot == 0:
                    plt.title(title)

                try:

                    if nbrokenY * nbrokenX > 1:

                        plt.subplots_adjust(hspace=0.1 if nbrokenY > 1 else 0,wspace=0.1 if nbrokenX > 1 else 0)  # adjust space between axes
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
            if ibrokenY == 0 and ibrokenX == 0:
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
                if graph_type != "simple_bar" and doleg:
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
            return result_type, lgd


    def reject_outliers(self, result, testie):
        return testie.reject_outliers(result)

    def write_labels(self, rects, plt, color, idx = 0):
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
                        height = rect.get_ydata()
                        x = rect.get_xdata()
                        m=1.1
                    else:
                        height = rect.get_height()
                        x = rect.get_x() + rect.get_width()/2.
                        m=1.05
                    try:
                        if np.isnan(height):
                            continue
                    except:
                        continue
                    ax.text(x, m*height,
                        ('%0.'+str(prec)+'f') % height, color=color, fontweight='bold',
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
            return False

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
        plt.xticks(ticks, x, rotation='vertical' if (ndata > 8) else 'horizontal')
        plt.gca().set_xlim(0, len(x))
        return True

    def do_box_plot(self, axis, key, result_type, data : XYEB, xdata : XYEB,shift=0,idx=0):

        self.format_figure(axis, result_type, shift, key=key)
        nseries = max([len(y) for y in [y for x,y,e,build in data]])

        labels=[]

        if len(data) > 30:
            print("WARNING : Not drawing more than 30 boxplots")
            return
        for i, (x, ys, e, build) in enumerate(data):
            if xdata:
                x = []
                for yi in range(len(xdata[i][2])):
                    x.append(np.mean(xdata[i][2][yi][2]))

            label = str(build.pretty_name())
            boxdata=[]
            pos = []
            for yi in range(nseries):
                y=e[yi][2]
                pos.append(yi*len(data) + i + 1)
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
            axis.plot([], c= build._color , label=label)


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

        m = len(data)*nseries + 1
        axis.set_xlim(0,m)
        axis.set_xticklabels(labels)
        xticks = (np.asarray(range(nseries)) * len(data) ) + (len(data) / 2) + 0.5





        axis.set_xticks(xticks)
        return True

    def do_line_plot(self, axis, key, result_type, data : XYEB,shift=0,idx=0,xdata = None):
        xmin, xmax = (float('inf'), 0)
        drawstyle = self.scriptconfig('var_drawstyle',result_type,default='default')

        minX = None

        #Sync a variable, make all start at 0
        if self.config_bool_or_in("var_sync", key):
            for i, (x, y, e, build) in enumerate(data):
                if minX is None:
                    minX = min(x)
                else:
                    minX = min(minX,min(x))

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

            order = np.argsort(ax)

            shift = float(self.scriptconfig("var_shift", key=key, result_type=result_type, default=0))
            if minX is not None:
                ax = np.asarray([float(float(ax[i]) - shift - float(minX)) for i in order])
            else:
                ax = np.asarray([float(ax[i]) - shift for i in order])
            y = np.array([y[i] for i in order])
            mean = np.array([e[i][0] for i in order])
            std = np.array([e[i][1] for i in order])
            ymin = np.array([np.min(e[i][2]) for i in order])
            ymax = np.array([np.max(e[i][2]) for i in order])


            if 'step' in drawstyle:
                s = y[np.isfinite(y)]
                if len(s) > 0 and len(y) > 0:
                    y[-1] = s[-1]

            mask = np.isfinite(y)

            if len(ax[mask]) == 0:
                continue

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
                rects = axis.scatter(ax[mask], y[mask], label=lab, color=c,  marker=marker, fillstyle=fillstyle)
            else:
                rects = axis.plot(ax[mask], y[mask], label=lab, color=c, linestyle=build._line, marker=marker,markevery=(1 if len(ax[mask]) < 20 else math.ceil(len(ax[mask]) / 20)),drawstyle=drawstyle, fillstyle=fillstyle)
            error_type = self.scriptconfig('graph_error', 'result', result_type=result_type, default = "bar").lower()
            if error_type != 'none':
                if error_type == 'bar' or (error_type == None and not self.config('graph_error_fill')):
                    if error_type == 'barminmax':
                        axis.errorbar(ax[mask], ymin[mask], yerr=(ymin[mask],ymax[mask]), marker=' ', label=None, linestyle=' ', color=c, capsize=3)
                    else: #std dev
                        axis.errorbar(ax[mask], mean[mask], yerr=std[mask], marker=' ', label=None, linestyle=' ', color=c, capsize=3)
                else: #error type is fill or fillminmax
                    if not np.logical_or(np.zeros(len(y)) == e, np.isnan(y)).all():
                        if error_type=="fillminmax":
                            axis.fill_between(ax[mask], ymin[mask], ymax[mask], color=c, alpha=.4, linewidth=0)
                        elif error_type=="fill50":
                            perc25 = np.array([np.percentile(e[i][2],25) for i in order])[mask]
                            perc75 = np.array([np.percentile(e[i][2],75) for i in order])[mask]
                            axis.fill_between(ax[mask], perc25, perc75, color=c, alpha=.4, linewidth=0)
                        else:
                            axis.fill_between(ax[mask], mean[mask] - std[mask], mean[mask] + std[mask], color=c, alpha=.4, linewidth=0)

            xmin = min(xmin, min(ax[mask]))
            xmax = max(xmax, max(ax[mask]))

            self.write_labels(rects, plt, build._color, idx)

        if xmin == float('inf'):
            return False

        return True


    def set_axis_formatter(self, axis, format, unit, isLog, compact=False):
        mult=1
        if (unit and unit[0] == 'k'):
            unit=unit[1:]
            mult = 1024 if unit[0] == "B" else 1000
        axis.set_minor_locator(NullLocator())
        if format:
            formatter = FormatStrFormatter(format)
            axis.set_major_formatter(formatter)
            return True, False
        elif unit.lower() == "byte":
            axis.set_major_formatter(Grapher.ByteFormatter(unit="B",compact=compact,k=1024,mult=mult))
            return True, True
        elif (unit.lower() == "bps" or unit.lower() == "byteps"):
            if compact:
                u= "b" if unit.lower() == "bps" else "B"
            else:
                u = "Bits" if unit.lower() == "bps" else "Bytes"
            k = 1000 if unit.lower() == "bps" else 1024
            axis.set_major_formatter(Grapher.ByteFormatter(unit,"/s", compact=compact, k=k, mult=mult))
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

    def format_figure(self, axis, result_type, shift, key = None):
        yunit = self.scriptconfig("var_unit", "result", default="", result_type=result_type)
        yformat = self.scriptconfig("var_format", "result", default=None, result_type=result_type)
        yticks = self.scriptconfig("var_ticks", "result", default=None, result_type=result_type)
        shift = int(shift)
        tick_params = self.configdict("graph_tick_params",default={})
        if self.config_bool_or_in('var_grid',result_type):
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
            plt.yscale('symlog', basey=baseLog, linthreshy=thresh)
            isLog = True
        elif self.result_in_list('var_log', result_type):
            plt.yscale('symlog' if yformat else 'log')
            isLog = True
        whatever, handled = self.set_axis_formatter(axis.yaxis,yformat,yunit,isLog)
        yname = self.var_name("result", result_type=result_type)
        if yname != "result":
            if not handled and not '(' in yname and yunit and yunit.strip():
                yname = yname + ' (' + yunit + ')'
        axis.yname = yname

        if yticks:
            ticks = [variable.get_numeric(npf.parseUnit(y)) for y in yticks.split('+')]
            plt.yticks(ticks)

    def do_barplot(self, axis,vars_all, dyns, result_type, data, shift):
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

        stack = self.config_bool('graph_bar_stack')
        n_series = len(vars_all)
        bars_per_serie = 1 if stack else len(data)
        ind = np.arange(n_series)

        width = (1 - (2 * interbar)) / bars_per_serie
        if stack:
            last = 0
            for i, (x, y, e, build) in enumerate(data):
                y = np.asarray([0.0 if np.isnan(x) else x for x in y])
                last = last + y

            for i, (x, y, e, build) in enumerate(data):
                y = np.asarray([0.0 if np.isnan(x) else x for x in y])
                std = np.asarray([std for mean,std,raw in e])
                rects = axis.bar(ind, last, width,
                    label=str(build.pretty_name()), color=build._color, yerr=std,
                    edgecolor=edgecolor)
                last = last - y
        else:
            for i, (x, y, e, build) in enumerate(data):
                std = np.asarray([std for mean,std,raw in e])
                rects = axis.bar(interbar + ind + (i * width), y, width,
                    label=str(build.pretty_name()), color=build._color, yerr=std,
                    edgecolor=edgecolor)
                self.write_labels(rects, plt, build._color)

        ss = self.combine_variables(vars_all, dyns)

        if not bool(self.config_bool('graph_x_label', True)):
            ss = ["" for i in range(n_series)]

        plt.xticks(ind if stack else interbar + ind + (width * (len(data) - 1) / 2.0), ss,
                   rotation='vertical' if (sum([len(s) for s in ss]) > 80) else 'horizontal')
