import csv
import io

from orderedset._orderedset import OrderedSet

from collections import OrderedDict
from typing import List

import matplotlib
import numpy as np

from npf.types import dataset
from npf.types.dataset import Run
from npf.variable import is_numeric, get_numeric
from npf import npf, variable

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, FormatStrFormatter
import math
import os

graphcolor = [(31, 119, 180), (174, 199, 232), (255, 127, 14), (255, 187, 120),
              (44, 160, 44), (152, 223, 138), (214, 39, 40), (255, 152, 150),
              (148, 103, 189), (197, 176, 213), (140, 86, 75), (196, 156, 148),
              (227, 119, 194), (247, 182, 210), (127, 127, 127), (199, 199, 199),
              (188, 189, 34), (219, 219, 141), (23, 190, 207), (158, 218, 229)]
for i in range(len(graphcolor)):
    r, g, b = graphcolor[i]
    graphcolor[i] = (r / 255., g / 255., b / 255.)


def all_num(l):
    for x in l:
        if type(x) is not int and type(x) is not float:
            return False
    return True


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
                if result_type is None:
                    return d.get(key, default)
                else:
                    if key + "-" + result_type in d:
                        return d.get(key + "-" + result_type)
                    else:
                        return d.get(key, default)

        return default

    def var_name(self, key, result_type=None):
        return self.scriptconfig("var_names", key, key, result_type)

    def bits(self, x, pos):
        return self.formatb(x, pos, "Bits")

    def bytes(self, x, pos):
        return self.formatb(x, pos, "Bytes")

    def formatb(self, x, pos, unit):
        if (x >= 1000000000):
            return "%.2f G%s/s" % (x / 1000000000, unit)
        elif (x >= 1000000):
            return "%.2f M%s/s" % (x / 1000000, unit)
        elif (x >= 1000):
            return "%.2f K%s/s" % (x / 1000, unit)
        else:
            return "%.2f %s/s" % (x, unit)

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

        versions = []

        ymin, ymax = (float('inf'), 0)

        # If no graph variables, use the first serie
        if graph_variables is None:
            graph_variables = []
            for run, results in series[0][2].items():
                graph_variables.append(run)

        #Get all scripts, find versions
        for i, (testie, build, all_results) in enumerate(series):
            self.scripts.add(testie)

        # Combine variables as per the graph_combine_variables config parameter
        for tocombine in self.configlist('graph_combine_variables',[]):
            tomerge=tocombine.split('+')
            newgraph_variables=[]
            run_map = {}
            for run in graph_variables:
                newrun = run.copy()
                vals=[]
                for var,val in run.variables.items():
                    if var in tomerge:
                        del newrun.variables[var]
                        vals.append(str(val[1] if type(val) is tuple else val))
                newrun.variables[tocombine] = ', '.join(OrderedSet(vals))
                newgraph_variables.append(newrun)
                run_map[run] = newrun

            graph_variables=newgraph_variables

            newseries = []
            for i, (testie, build, all_results) in enumerate(series):
                new_all_results = {}
                for run, run_results in all_results.items():
                    newrun = run_map.get(run,None)
                    if newrun is not None:
                        new_all_results[newrun] = run_results
                newseries.append((testie,build,new_all_results))
            series = newseries

        # Data transformation : reject outliers, transform list to arrays, filter according to graph_variables, count var_alls and vars_values
        filtered_series = []
        vars_values = {}
        for i, (testie, build, all_results) in enumerate(series):
            new_results = {}
            for run, run_results in all_results.items():
                if run in graph_variables:
                    for result_type, results in run_results.items():
                        if options.graph_reject_outliers:
                            results = self.reject_outliers(np.asarray(results), testie)
                        else:
                            results = np.asarray(results)
                        new_results.setdefault(run, {})[result_type] = results
                    for k, v in run.variables.items():
                        vars_values.setdefault(k, set()).add(v)

            if new_results:
                filtered_series.append((testie, build, new_results))
                versions.append(build.pretty_name())
            else:
                print("No valid data for %s" % build)
        series = filtered_series

        print(series)

        # Transform results to variables as the graph_result_as_variable options asks
        for result_types,var_name in self.configdict('graph_result_as_variable',{}).items():
            result_to_variable_map=set()
            for result_type in result_types.split('+'):
                result_to_variable_map.add(result_type)
            vars_values[var_name]=result_to_variable_map

            transformed_series = []
            for i, (testie, build, all_results) in enumerate(series):
                new_results = {}

                for run, run_results in all_results.items():
                    for stripout in result_to_variable_map:
                        variables = run.variables.copy()
                        new_run_results = {}
                        nodata=True
                        for result_type, results in run_results.items():
                            if result_type in result_to_variable_map:
                                if result_type == stripout:
                                    variables[var_name] = result_type
                                    nodata=False
                                    new_run_results[var_name] = results
                            else:
                                new_run_results[result_type] = results

                        if not nodata:
                            new_results[Run(variables)] = new_run_results

                if new_results:
                    transformed_series.append((testie, build, new_results))
            series = transformed_series
        vars_all = set()
        for i, (testie, build, all_results) in enumerate(series):
            for run, run_results in all_results.items():
                 vars_all.add(run)
        vars_all = list(vars_all)
        vars_all.sort()

        dyns = []
        statics = {}
        for k, v in vars_values.items():
            if len(v) > 1:
                dyns.append(k)
            else:
                statics[k] = list(v)[0]

        ndyn = len(dyns)
        nseries = len(series)

        if nseries == 1 and ndyn > 0 and not (
                    ndyn == 1 and all_num(vars_values[dyns[0]]) and len(vars_values[dyns[0]]) > 2):
            """Only one serie: expand one dynamic variable as serie, but not if it was plotable as a line"""
            script, build, all_results = series[0]
            if self.config("var_series") and self.config("var_series") in dyns:
                key = self.config("var_series")
            else:
                key = None
                # First pass : use the non-numerical variable with the most points
                n_val = 0
                nonums=[]
                for i in range(ndyn):
                    k = dyns[i]
                    if not all_num(vars_values[k]):
                        nonums.append(k)
                        if len(vars_values[k]) > n_val:
                            key = k
                            n_val = len(vars_values[k])
                if key is None:
                    # Second pass if that missed, use the numerical variable with the less point if dyn==2 (->lineplot) else the most points
                    n_val = 0 if ndyn > 2 else 999
                    for i in range(ndyn):
                        k = dyns[i]
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
            values.sort()
            new_varsall = set()
            for value in values:
                newserie = {}
                for run, run_results in all_results.items():
#                    if (graph_variables and not run in graph_variables):
#                        continue
                    if (run.variables[key] == value):
                        newrun = run.copy()
                        del newrun.variables[key]
                        newserie[newrun] = run_results
                        new_varsall.add(newrun)

                series.append((script, build, newserie))
                if type(value) is tuple:
                    value = value[1]
                versions.append(value)
                legend_title = self.var_name(key)
            nseries = len(series)
            vars_all = list(new_varsall)
            vars_all.sort()
        else:
            legend_title = None

        if ndyn == 0:
            key = "version"
        elif ndyn == 1:
            key = dyns[0]
        else:
            key = "Variables"

        data_types = dataset.convert_to_xye([(all_results,script) for script, build, all_results in series],vars_all,key)

        if options.output is not None:
            for result_type,data in data_types.items():
                type_filename = npf.build_filename(testie, build, options.output, statics, 'csv', result_type)
                with open(type_filename, 'w') as csvfile:
                    wr = csv.writer(csvfile, delimiter=' ',
                                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
                    for i,(x,y,e) in enumerate(data):
                        if (i == 0):
                            wr.writerow(x)
                        wr.writerow(y)
                print("Output written to %s" % type_filename)

        plots=OrderedDict()
        for result_type, data in data_types.items():
            if result_type in self.configlist('graph_subplot_results',[]):
                plots.setdefault('common',[]).append(result_type)
            else:
                plots[result_type] = [result_type]

        ret = {}
        for whatever,figure in plots.items():
            for isubplot,result_type in enumerate(figure):
                data = data_types[result_type]

                if len(figure) > 1:
                    plt.subplot(len(figure), 1, isubplot + 1)

                if ndyn == 0:
                    """No dynamic variables : do a barplot X=version"""
                    self.do_simple_barplot(versions, result_type, data)
                elif ndyn == 1 and len(vars_all) > 2:
                    """One dynamic variable used as X, series are version line plots"""
                    self.do_line_plot(versions, key, result_type, data)
                else:
                    """Barplot. X is all seen variables combination, series are version"""
                    self.do_barplot(series, vars_all, dyns, versions, result_type, data)

                type_config = "" if not result_type else "-" + result_type


                if ndyn > 0 and bool(self.config_bool('graph_legend', True)):
                    plt.legend(loc=self.config("legend_loc"), title=legend_title)

                if "result-" + result_type in self.config('var_log', {}) or "result" in self.config('var_log', {}):
                    plt.yscale('log')

                if key in self.config('var_log', {}):
                    plt.xscale('log')

                plt.xlabel(self.var_name(key))

                yname = self.var_name("result", result_type=result_type)
                if yname != "result":
                    plt.ylabel(yname)

                var_lim = self.scriptconfig("var_lim", "result" + type_config, None)
                if var_lim:
                    n = var_lim.split('-')
                    if len(n) == 2:
                        ymin, ymax = (float(x) for x in n)
                        plt.ylim(ymin=ymin, ymax=ymax)
                    else:
                        plt.ylim(ymin=float(n[0]))
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

                try:
                    plt.tight_layout()
                except ValueError:
                    print("WARNING: Too many points or variables to graph")
                    print("Try reducing the number of dynamic variables : ")
                    for dyn in dyns:
                        print(dyn)
                    return None

                if len(figure) > 1:
                    if isubplot < len(figure) -1:
                        continue
                    else:
                        result_type = 'common'
                if not filename:
                    buf = io.BytesIO()
                    plt.savefig(buf, format='png')
                    buf.seek(0)
                    ret[result_type] = buf.read()
                else:
                    type_filename =  npf.build_filename(testie, build, options.graph_filename, statics, 'pdf', result_type)
                    plt.savefig(type_filename)
                    ret[result_type] = None
                    print("Graph of test written to %s" % type_filename)
                plt.clf()
        return ret

    def reject_outliers(self, result, testie):
        return testie.reject_outliers(result)

    def do_simple_barplot(self, versions, result_type, data):
        i = 0
        interbar = 0.1
        ndata = len(versions)
        nseries = 1
        width = (1 - (2 * interbar)) / nseries

        ticks = np.arange(ndata) + 0.5

        y = [s[1] for s in data]
        self.format_figure(result_type)
        plt.bar(ticks, y, label=versions[i], color=graphcolor[i % len(graphcolor)], width=width)
        plt.xticks(ticks, versions, rotation='vertical' if (len(versions) > 10) else 'horizontal')
        plt.gca().set_xlim(0, len(versions))


    def do_line_plot(self, versions, key, result_type, data):

        xmin, xmax = (float('inf'), 0)

        for i, ax in enumerate(data):
            self.format_figure(result_type)
            c = graphcolor[i % len(graphcolor)]

            if not all_num(ax[0]):
                if variable.numericable(ax[0]):
                    x = [variable.get_numeric(v) for i,v in enumerate(ax[0])]
                else:
                    x = [i + 1 for i,v in enumerate(ax[0])]
            else:
                x = ax[0]
            data = np.asarray((x,ax[1],ax[2]))
            data = data[data[:, 1].argsort()]
            plt.plot(data[0], data[1], label=versions[i], color=c)
            plt.errorbar(data[0], data[1], yerr=data[2], fmt='o', label=None, color=c)
            xmin = min(xmin, min(x))
            xmax = max(xmax, max(x))

        # Arrange the x limits
        if not (key in self.config('var_log', {})):
            var_lim = self.scriptconfig("var_lim", key, key)
            if var_lim and var_lim is not key:
                xmin, xmax = (float(x) for x in var_lim.split('-'))
            else:
                if abs(xmin) < 10 and abs(xmax) < 10:
                    if (xmin != 1):
                        xmin -= 1
                    xmax += 1
                    pass
                else:
                    base = float(max(10, math.ceil((xmax - xmin) / 10)))
                    if (xmin > 0):
                        xmin = int(math.floor(xmin / base)) * base
                    if (xmax > 0):
                        xmax = int(math.ceil(xmax / base)) * base

            plt.gca().set_xlim(xmin, xmax)


    def format_figure(self, type):
        ax = plt.gca()

        yunit = self.scriptconfig("var_unit", "result", default="", result_type=type)
        yformat = self.scriptconfig("var_format", "result", default=None, result_type=type)

        if yformat is not None:
            formatter = FormatStrFormatter(yformat)
            ax.yaxis.set_major_formatter(formatter)
        elif (yunit.lower() == "bps" or yunit.lower() == "byteps"):
            formatter = FuncFormatter(self.bits if yunit.lower() == "bps" else self.bytes)
            ax.yaxis.set_major_formatter(formatter)
        else:
            ax.get_yaxis().get_major_formatter().set_useOffset(False)

    def do_barplot(self, series, vars_all, dyns, versions, result_type, data):
        nseries = len(series)

        self.format_figure(result_type)

        # If more than 20 bars, do not print bar edges
        maxlen = max([len(serie_data[0]) for serie_data in data])

        if nseries * maxlen > 20:
            edgecolor = "none"
            interbar = 0.05
        else:
            edgecolor = None
            interbar = 0.1

        width = (1 - (2 * interbar)) / len(versions)
        ind = np.arange(len(vars_all))

        for i, (x,y,e) in enumerate(data):
            plt.bar(interbar + ind + (i * width), y, width,
                    label=str(versions[i]), color=graphcolor[i % len(graphcolor)], yerr=e,
                    edgecolor=edgecolor)

        ss = self.combine_variables(vars_all, dyns)

        if not bool(self.config_bool('graph_x_label', True)):
            ss = ["" for i in range(len(vars_all))]
        plt.xticks(interbar + ind + (width * len(versions) / 2.0), ss,
                   rotation='vertical' if (sum([len(s) for s in ss]) > 80) else 'horizontal')

