import io
import math
import re
import natsort
from orderedset._orderedset import OrderedSet

from collections import OrderedDict
from typing import List
from matplotlib.ticker import LinearLocator, ScalarFormatter, Formatter, MultipleLocator
import matplotlib
import numpy as np

from npf.types import dataset
from npf.types.dataset import Run, XYEB
from npf.variable import is_numeric, get_numeric, numericable
from npf.section import SectionVariable
from npf import npf, variable
from matplotlib.lines import Line2D

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, FormatStrFormatter
import math
import os
import webcolors

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
    return tuple(a * p + (1-p) * n for a in c)

graphcolorseries = [graphcolor]
graphcolorseries.append(hexToList("#144c73 #185a88 #1b699e #1f77b4 #2385ca #2b93db #419ede"))
graphcolorseries.append(hexToList("#1c641c #217821 #278c27 #2ca02c #32b432 #37c837 #4bce4b"))
graphcolorseries.append(hexToList("#c15a00 #da6600 #f47200 #ff7f0e #ff8d28 #ff9a41 #ffa85b"))
graphcolorseries.append(hexToList("#951b1c #ab1f20 #c02324 #d62728 #db3b3c #df5152 #e36667"))
graphcolorseries.append(hexToList("#6e4196 #7b49a8 #8755b5 #9467bd #a179c5 #ad8bcc #ba9cd4"))

gridcolors = [ (0.7,0.7,0.7) ]
legendcolors = [ None ]
for clist in graphcolorseries[1:]:
    gridcolors.append(lighter(clist[(int)(len(clist) / 2)], 0.25, 200))
    legendcolors.append(lighter(clist[(int)(len(clist) / 2)], 0.45, 25))

def find_base(ax):
    if ax[0] == 0 and len(ax) > 2:
        base = ax[2] / ax[1]
    else:
        base = ax[1] / ax[0]
    if base != 2:
        base = 10
    return base


class Map(OrderedDict):
    def __init__(self, fname):
        super().__init__()
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
            if re.search(k,map_v):
                return v
        return None


class Grapher:
    def __init__(self):
        self.scripts = set()

    def config_bool(self, var, default=None):
        val = self.config(var, default)
        if val == "0" or val == "F" or val == "False" or val == "false":
            return False
        return val

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
        for script in self.scripts:
            if var in script.config:
                d = script.config.get_dict(var)
                lk = key.lower()
                if result_type is None:
                    #Search for the exact key if there is no result_type
                    for k, v in d.items():
                        if k.lower() == lk:
                            return v
                    return default
                else:
                    #Search for "key-result_type", such as result-throughput
                    lkr = (key + "-" + result_type).lower()
                    for k, v in d.items():
                        if k.lower() == lkr:
                            return v
                    for k, v in d.items():
                        if k.lower() == lk:
                            return v
                    #Search for result type alone such as throughput
                    lkr = (result_type).lower()
                    for k, v in d.items():
                        if k.lower() == lkr:
                            return v
                    for k, v in d.items():
                        if k.lower() == lk:
                            return v

                    return default
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
                short_s = []
                for k, v in run.variables.items():
                    if k in variables_to_merge:
                        v = str(v[1] if type(v) is tuple else v)
                        s.append("%s = %s" % (self.var_name(k), v))
                        short_s.append("%s = %s" % (k if len(k) < 6 else k[:3], v))
                vs = ','.join(s)
                ss.append(vs)
                if len(vs) > 30:
                    use_short = True
                short_ss.append(','.join(short_s))
            if use_short:
                ss = short_ss
        return ss

    def graph(self, filename, options, graph_variables: List[Run] = None, title=False, series=None):
        """series is a list of triplet (script,build,results) where
        result is the output of a script.execute_all()"""
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

        #Overwrite markers and lines from user
        graphmarkers = self.configlist("graph_markers")
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
                        if options.graph_reject_outliers:
                            results = self.reject_outliers(np.asarray(results), testie)
                        else:
                            results = np.asarray(results)
                        if options.graph_select_max:
                            results = np.sort(results)[-options.graph_select_max:]

                        ydiv = dataset.var_divider(testie, "result", result_type)
                        new_results.setdefault(run, OrderedDict())[result_type] = results / ydiv
                    for k, v in run.variables.items():
                        vars_values.setdefault(k, OrderedSet()).add(v)

            if new_results:
                if len(graphmarkers) > 0:
                    build._marker = graphmarkers[i % len(graphmarkers)]
                filtered_series.append((testie, build, new_results))
            else:
                print("No valid data for %s" % build)
        series = filtered_series


        #If graph_series_as_variables, take the series and make them as variables
        if self.config_bool('graph_series_as_variables',False):
            new_results = {}
            vars_values['serie'] = set()
            for i, (testie, build, all_results) in enumerate(series):
                for run, run_results in all_results.items():
                    run.variables['serie'] = build.pretty_name()
                    vars_values['serie'] = build.pretty_name()
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
        for result_types, var_name in self.configdict('graph_result_as_variable', {}).items():
            if len(var_name.split('-')) > 1:
                result_name=var_name.split('-')[1]
                var_name=var_name.split('-')[0]
            else:
                result_name=var_name
            result_to_variable_map = []

            for result_type in result_types.split('+'):
                result_to_variable_map.append(result_type)
            vvalues = set()

            transformed_series = []
            for i, (testie, build, all_results) in enumerate(series):
                new_results = {}

                for run, run_results in all_results.items():
                    new_run_results = {}
                    new_run_results_exp = {}

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
                            new_run_results[result_type] = results

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
                            if tot <= 99:
                                new_run_results_exp['Other'] = [100-tot]

                        if var_name in run.variables:
                            results = new_run_results_exp[run.variables[var_name]]
                            nr = new_run_results.copy()
                            #If unit is percent, we multiply the value per the result
                            if mult:
                                m = np.mean(results)
                                tot += m
                                for result_type in nr:
                                    nr[result_type] = nr[result_type].copy() * m / 100
                            nr.update({'result-'+result_name: results})

                            new_results[run] = nr
                        else:
                            for result_type, results in new_run_results_exp.items():
                                variables = run.variables.copy()
                                variables[var_name] = result_type
                                vvalues.add(result_type)
                                nr = new_run_results.copy()
                                #If unit is percent, we multiply the value per the result
                                if mult:
                                    m = np.mean(results)
                                    tot += m
                                    for result_type in nr:
                                        nr[result_type] = nr[result_type].copy() * m / 100
                                nr.update({'result-'+result_name: results})
                                new_results[Run(variables)] = nr

                    else:
                        new_results[run] = new_run_results

                if new_results:
                    transformed_series.append((testie, build, new_results))
                if vvalues:
                    assert(npf.all_num(vvalues))
                    vars_values[var_name] = vvalues
            series = transformed_series

        #Divide a serie by another
        prop = self.config('graph_series_prop')
        if prop:
            newseries = []
            if not is_numeric(prop):
                prop=1
            base_results=series[0][2]
            for i, (script, build, all_results) in enumerate(series[1:]):
                new_results={}
                for run,run_results in all_results.items():
                    if not run in base_results:
                        print(run,"not in base")
                        continue

                    for result_type, results in run_results.items():
                        if not result_type in base_results[run]:
                            run_results[result_type] = None
                            continue
                        base = base_results[run][result_type]
                        if len(base) > len(results):
                            base = base[:len(results)]
                        elif len(results) > len(base):
                            results = results[:len(base)]
                        results = results / base * prop
                        run_results[result_type] = results
                    new_results[run] = run_results
                newseries.append((script, build, new_results))
            series = newseries


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
            values = natsort.natsorted(vars_values[to_get_out])
            if len(values) == 1:
                statics[to_get_out] = list(values)[0]
            del vars_values[to_get_out]

            transformed_series = []
            for i, (testie, build, all_results) in enumerate(series):
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
                    nbuild._pretty_name = ' - '.join(([nbuild.pretty_name()] if len(series) > 1 else []) + ["%s = %s" % (self.var_name(to_get_out), str(value))])
                    if len(graphmarkers) > 0:
                        nbuild._marker = graphmarkers[i % len(graphmarkers)]
                    if len(series) == 1: #If there is one serie, expand the line types
                        nbuild._line = self.graphlines[i % len(self.graphlines)]
                    nbuild.statics[to_get_out] = value
                    transformed_series.append((testie, nbuild, data))

            series = transformed_series

        #Map and combine variables values
        for map_k, fmap in self.configdict('graph_map',{}).items():
            fmap = Map(fmap)
            transformed_series = []
            for i, (testie, build, all_results) in enumerate(series):
                new_results={}
                for run, run_results in all_results.items():
                    if not map_k in run.variables:
                        new_results[run] = run_results
                        continue
                    map_v = run.variables[map_k]
                    new_v = fmap.search(map_v)
                    if new_v:
                        if map_v in vars_values[map_k]:
                            vars_values[map_k].remove(map_v)
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
            series = transformed_series


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
                statics[k] = list(v)[0]

        ndyn = len(dyns)
        nseries = len(series)

        if nseries == 1 and ndyn > 0 and not options.graph_no_series and not (
                            ndyn == 1 and npf.all_num(vars_values[dyns[0]]) and len(vars_values[dyns[0]]) > 2):
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

            # if graph_serie:
            #     key=graph_serie
            dyns.remove(key)
            ndyn -= 1
            series = []
            versions = []
            values = list(vars_values[key])
            try:
                values.sort()
            except TypeError:
                print("ERROR : Cannot sort the following values :", values)
                return
            new_varsall = set()
            for i, value in enumerate(values):
                newserie = {}
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
                if len(graphmarkers) > 0:
                    nb._marker = graphmarkers[i % len(graphmarkers)]
                series.append((script, nb, newserie))
                glob_legend_title = self.var_name(key)
            nseries = len(series)
            vars_all = list(new_varsall)
            vars_all.sort()
            if ndyn == 1:
                key = dyns[0]
                do_sort = True
            else:
                key = "Variables"
                do_sort = False

        else:
            glob_legend_title = None
            if ndyn == 0:
                key = "version"
                do_sort = False
            elif ndyn == 1:
                key = dyns[0]
                do_sort = True
            else:
                key = "Variables"
                do_sort = False

        graph_series_label = self.config("graph_series_label")
        if graph_series_label:
            for i, (testie, build, all_results) in enumerate(series):
                v = {}
                v.update(statics)
                v.update(build.statics)
                build._pretty_name=SectionVariable.replace_variables(v, graph_series_label)

        data_types = dataset.convert_to_xyeb(series, run_list = vars_all, key = key, max_series=self.config('graph_max_series'), do_x_sort=do_sort, series_sort=self.config('graph_series_sort'), options=options, statics=statics)

        plots = OrderedDict()
        matched_set = set()
        for i,(result_type_list, n_cols) in enumerate(self.configdict('graph_subplot_results', {}).items()):
            for result_type in re.split('[,]|[+]', result_type_list):
                matched = False
                for k in data_types.keys():
                    if re.match(result_type, k):
                        if variable.is_numeric(n_cols):
                            n_cols = variable.get_numeric(n_cols)
                        else:
                            n_cols = 1
                        plots.setdefault(i,([],n_cols))[0].append((k))
                        matched_set.add(k)
                        matched = True
                if not matched:
                    print("WARNING: Unknown data type to include as subplot : %s" % result_type)

        for result_type, data in sorted(data_types.items()):
            if result_type not in matched_set:
                plots[result_type] = ([result_type],1)

        ret = {}
        subplot_type=self.config("graph_subplot_type")
        for i, (figure,n_cols) in plots.items():
            text = self.config("graph_text")

            if len(self.configlist("graph_display_statics")) > 0:
                for stat in self.configlist("graph_display_statics"):
                    if text == '' or text[-1] != "\n":
                        text += "\n"
                    text += self.var_name(stat) + " : " + ', '.join([str(val) for val in vars_values[stat]])
            n_lines = math.ceil((len(figure) + (1 if text else 0)) / float(n_cols))
            fig_name = "subplot" + str(i)

            axiseis = []
            for isubplot, result_type in enumerate(figure):
                data = data_types[result_type]
                ymin, ymax = (float('inf'), 0)

                if subplot_type=="subplot":
                    if isubplot > 0:
                        axis = plt.subplot(n_lines, n_cols, isubplot + 1, sharex=axiseis[0])
                        plt.setp(axiseis[0].get_xticklabels(), visible=False)
                        axiseis[0].set_xlabel("")
                    else:
                        axis = plt.subplot(n_lines, n_cols, isubplot + 1)

                    shift = 0
                else:
                    if isubplot == 0:
                        fix,axis=plt.subplots()
                    else:
                        axis=axis.twinx()
                    if len(figure) > 1:
                        shift = isubplot + 1
                        for i, (x, y, e, build) in enumerate(data):
                            build._line=self.graphlines[isubplot]
                    else:
                        shift = 0
                axiseis.append(axis)

                gcolor = self.configlist('graph_color')
                gi = {} #Index per-color
                for i, (x, y, e, build) in enumerate(data):
                    if not gcolor and shift == 0:
                        build._color=graphcolorseries[0][i % len(graphcolorseries[0])]
                    else:
                        if gcolor:
                            s=gcolor[i]
                            tot = gcolor.count(s)
                        else:
                            s=shift
                            tot = len(data)
                        gi.setdefault(s,0)
                        slen = len(graphcolorseries[s])
                        n = slen / tot
                        if n < 0:
                            n = 1
                        #For the default colors we take them in order
                        if s == 0:
                            f = gi[s]
                        else:
                            f = round((gi[s] + (0.33 if gi[s] < tot / 2 else 0.66)) * n)
                        gi[s]+=1
                        build._color=graphcolorseries[s % len(graphcolorseries)][f % len(graphcolorseries[s % len(graphcolorseries)])]

                r = True
                if ndyn == 0:
                    """No dynamic variables : do a barplot X=version"""
                    r = self.do_simple_barplot(axis,result_type, data, shift)
                elif ndyn == 1 and len(vars_all) > 2 and npf.all_num(vars_values[key]):
                    """One dynamic variable used as X, series are version line plots"""
                    r = self.do_line_plot(axis, key, result_type, data,shift)
                else:
                    """Barplot. X is all seen variables combination, series are version"""
                    self.do_barplot(axis,vars_all, dyns, result_type, data, shift)

                if not r:
                    continue

                type_config = "" if not result_type else "-" + result_type

                lgd = None
                if legendcolors[shift]:
                    axis.yaxis.label.set_color(legendcolors[shift])
                    axis.tick_params(axis='y',colors=legendcolors[shift])
                xunit = self.scriptconfig("var_unit", key, default="")
                xformat = self.scriptconfig("var_format", key, default="")
                isLog = key in self.config('var_log', {})
                baseLog = self.scriptconfig('var_log_base', key, default=None)
                if baseLog:
                    isLog = True
                if isLog:
                    ax = data[0][0]
                    if ax is not None and len(ax) > 1:
                        if baseLog:
                            base = float(baseLog)
                        else:
                            base = find_base(ax)
                        plt.xscale('symlog',basex=base)
                        xticks = data[0][0]
                        if len(xticks) > 8:
                            n =int(math.ceil(len(xticks) / 8))
                            index = np.array(range(len(xticks)))[1::n]
                            if index[-1] != len(xticks) -1:
                                index = np.append(index,[len(xticks)-1])
                            xticks = np.delete(xticks,np.delete(np.array(range(len(xticks))),index))
                        plt.xticks(xticks)
                    else:
                        plt.xscale('symlog')
                    plt.gca().xaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter('%d'))
                formatterSet, unithandled = self.set_axis_formatter(plt.gca().xaxis, xformat, xunit.strip(), isLog, True)


                xticks = self.scriptconfig("var_ticks", key, default=None)
                if xticks:
                    if isLog:
                        plt.gca().xaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
                    plt.xticks([variable.get_numeric(x) for x in xticks.split('+')])

                plt.xlabel(self.var_name(key))

                var_lim = self.scriptconfig("var_lim", "result", result_type=result_type, default=None)
                if var_lim:
                    n = var_lim.split('-')
                    if len(n) == 2:
                        ymin, ymax = (npf.parseUnit(x) for x in n)
                        plt.ylim(ymin=ymin, ymax=ymax)
                    else:
                        f=float(n[0])
                        if f==0:
                            plt.ylim(ymin=f)
                        else:
                            plt.ylim(ymax=f)
                else:
                    if (ymin >= 0 > plt.ylim()[0]):
                        plt.ylim(0, plt.ylim()[1])

                    if (ymin < ymax / 5):
                        plt.ylim(ymin=0)

                if options.graph_size:
                    fig = plt.gcf()
                    fig.set_size_inches(options.graph_size[0], options.graph_size[1])

                if title and isubplot == 0:
                    plt.title(title)

                # if len(figure > 0):
                #                    plt.title(self.var_name())

                try:
                    plt.tight_layout()
                except ValueError:
                    print("Could not make the graph fit. It may be because you have too many points or variables to graph")
                    print("Try reducing the number of dynamic variables : ")
                    for dyn in dyns:
                        print(dyn)
                    return None

            for isubplot, result_type in enumerate(figure):
                axis = axiseis[isubplot]
                if ndyn > 0 and bool(self.config_bool('graph_legend', True)):
                    loc = self.config("legend_loc")
                    if subplot_type=="axis" and len(figure) > 1:
                        if not loc.startswith("outer"):

                            if self.configlist("subplot_legend_loc"):
                                loc=self.configlist("subplot_legend_loc")[isubplot]
                            else:
                                if isubplot == 0:
                                    loc = 'upper left'
                                else:
                                    loc = 'lower right'

                        else:
                            if isubplot > 0:
                                continue
                        legend_title = self.var_name("result",result_type=result_type)
                    else:
                        legend_title = glob_legend_title

                    if loc and loc.startswith("outer"):
                        loc = loc[5:].strip()
                        legend_bbox=self.configlist("legend_bbox")
                        lgd = axis.legend(loc=loc,bbox_to_anchor=legend_bbox, mode=self.config("legend_mode"), borderaxespad=0.,ncol=self.config("legend_ncol"), title=legend_title,bbox_transform=plt.gcf().transFigure)
                    else:
                        lgd = axis.legend(loc=loc,ncol=self.config("legend_ncol"), title=legend_title)



            if text:
                plt.subplot(n_lines, n_cols, len(figure) + 1)
                plt.axis('off')
                plt.figtext(.05, (0.5 / (len(figure) + 1)), text.replace("\\n", "\n"), verticalalignment='center',
                            horizontalalignment='left')

            if len(figure) > 1:
                if isubplot < len(figure) - 1:
                    continue
                else:
                    result_type = fig_name
            if not filename:
                buf = io.BytesIO()
                plt.savefig(buf, format='png', bbox_extra_artists=(lgd,) if lgd else [], bbox_inches='tight')
                buf.seek(0)
                ret[result_type] = buf.read()
            else:
                type_filename = npf.build_filename(testie, build, filename if not filename is True else None, statics, 'pdf', result_type, show_serie=False)
                plt.savefig(type_filename, bbox_extra_artists=(lgd,) if lgd else [], bbox_inches='tight', dpi=options.graph_dpi, transparent=True)
                ret[result_type] = None
                print("Graph of test written to %s" % type_filename)
            plt.clf()
        return ret

    def reject_outliers(self, result, testie):
        return testie.reject_outliers(result)

    def do_simple_barplot(self,axis, result_type, data,shift=0):
        i = 0
        interbar = 0.1
        x = np.asarray([s[0][0] for s in data])
        y = np.asarray([s[1][0] for s in data])
        e = np.asarray([s[2][0] for s in data])

        ndata = len(x)

        mask = np.isfinite(y)

        if len(x[mask]) == 0:
            return False

        nseries = 1
        width = (1 - (2 * interbar)) / nseries

        ticks = np.arange(ndata) + 0.5

        self.format_figure(axis,result_type,shift)
        rects = plt.bar(ticks, y, label=x, color=data[0][3]._color, width=width, yerr=e)

        for i, v in enumerate(y):
            if np.isnan(v):
                continue
            axis.text(ticks[i], v + (np.nanmax(y) / 20), "%.02f" % v, color=data[0][3]._color, fontweight='bold', horizontalalignment='center')

        if self.config('graph_show_values',False):
            def autolabel(rects, ax):
                for rect in rects:
                    height = rect.get_height()
                    ax.text(rect.get_x() + rect.get_width()/2., 1.05*height,
                        '%0.2f' % height,
                         ha='center', va='bottom')
            autolabel(rects, plt)
        plt.xticks(ticks, x, rotation='vertical' if (ndata > 8) else 'horizontal')
        plt.gca().set_xlim(0, len(x))
        return True

    def do_line_plot(self, axis, key, result_type, data : XYEB,shift=0):
        xmin, xmax = (float('inf'), 0)

        for i, (x, y, e, build) in enumerate(data):
            self.format_figure(axis, result_type, shift)
            c = build._color

            if not npf.all_num(x):
                if variable.numericable(x):
                    ax = [variable.get_numeric(v) for i, v in enumerate(x)]
                else:
                    ax = [i + 1 for i, v in enumerate(x)]
            else:
                ax = x

            order = np.argsort(ax)

            ax = np.asarray([float(ax[i]) for i in order])
            y = np.array([y[i] for i in order])
            e = np.array([e[i] for i in order])

            mask = np.isfinite(y)

            if len(ax[mask]) == 0:
                continue

            lab = build.pretty_name()
            while lab.startswith('_'):
                lab = lab[1:]
            if self.config_bool("graph_scatter"):
                axis.scatter(ax[mask], y[mask], label=lab, color=c, linestyle=build._line, marker=build._marker)
            else:
                axis.plot(ax[mask], y[mask], label=lab, color=c, linestyle=build._line, marker=build._marker,markevery=(1 if len(ax[mask]) < 20 else math.ceil(len(ax[mask]) / 20)))
            if not self.config('graph_error_fill'):
                axis.errorbar(ax[mask], y[mask], yerr=e[mask], marker=' ', label=None, linestyle=' ', color=c, capsize=3)
            else:
                if not np.logical_or(np.zeros(len(e)) == e, np.isnan(e)).all():
                    axis.fill_between(ax[mask], (y-e)[mask], (y+e)[mask], color=c, alpha=.4, linewidth=0)

            xmin = min(xmin, min(ax[mask]))
            xmax = max(xmax, max(ax[mask]))

        if xmin == float('inf'):
            return False

        # Arrange the x limits
        if not (key in self.config('var_log', {})):
            var_lim = self.scriptconfig("var_lim", key, key)
            if var_lim and var_lim is not key:
                matches = re.match("([-]?[0-9.]+)[-]([-]?[0-9.]+)", var_lim)
                xmin, xmax = (float(x) for x in matches.groups())
            # else:
            #     if abs(xmin) < 10 and abs(xmax) < 10:
            #         if (xmin != 1):
            #             xmin -= 1
            #         xmax += 1
            #         pass
            #     else:
            #         base = float(max(10, math.ceil((xmax - xmin) / 10)))
            #         if (xmin > 0):
            #             xmin = int(math.floor(xmin / base)) * base
            #         if (xmax > 0):
            #             xmax = int(math.ceil(xmax / base)) * base
            #
                axis.set_xlim(xmin, xmax)
        return True


    def set_axis_formatter(self, axis, format, unit, isLog, compact=False):
        mult=1
        if (unit and unit[0] == 'k'):
            unit=unit[1:]
            mult = 1024 if unit[0] == "B" else 1000
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

    def format_figure(self, axis, result_type, shift):
        yunit = self.scriptconfig("var_unit", "result", default="", result_type=result_type)
        yformat = self.scriptconfig("var_format", "result", default=None, result_type=result_type)
        yticks = self.scriptconfig("var_ticks", "result", default=None, result_type=result_type)
        if self.result_in_list('var_grid',result_type):
            axis.grid(True,linestyle=self.graphlines[( shift - 1 if shift > 0 else 0) % len(self.graphlines)],color=gridcolors[shift])
            axis.set_axisbelow(True)
        isLog = False
        baseLog = self.scriptconfig('var_log_base', "result",result_type=result_type, default=None)
        if baseLog:
            plt.yscale('symlog', basey=float(baseLog))
            isLog = True
        elif self.result_in_list('var_log', result_type):
            plt.yscale('symlog' if yformat else 'log')
            isLog = True
        whatever, handled = self.set_axis_formatter(axis.yaxis,yformat,yunit,isLog)

        yname = self.var_name("result", result_type=result_type)
        if yname != "result":
            if not handled and not '(' in yname and yunit and yunit.strip():
                yname = yname + ' (' + yunit + ')'
            plt.ylabel(yname)

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
                axis.bar(ind, last, width,
                    label=str(build.pretty_name()), color=build._color, yerr=e,
                    edgecolor=edgecolor)
                last = last - y


        else:
            for i, (x, y, e, build) in enumerate(data):
                axis.bar(interbar + ind + (i * width), y, width,
                    label=str(build.pretty_name()), color=build._color, yerr=e,
                    edgecolor=edgecolor)

        ss = self.combine_variables(vars_all, dyns)

        if not bool(self.config_bool('graph_x_label', True)):
            ss = ["" for i in range(n_series)]
        plt.xticks(ind if stack else interbar + ind + (width * len(data) / 2.0), ss,
                   rotation='vertical' if (sum([len(s) for s in ss]) > 80) else 'horizontal')
