import csv
import io

import re
import natsort
from orderedset._orderedset import OrderedSet

from collections import OrderedDict
from typing import List
from matplotlib.ticker import LinearLocator,ScalarFormatter
import matplotlib
import numpy as np

from npf.types import dataset
from npf.types.dataset import Run, XYEB
from npf.variable import is_numeric, get_numeric
from npf.section import SectionVariable
from npf import npf, variable
from matplotlib.lines import Line2D

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

graphlines = ['-', '--', '-.', ':']


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
        return "result-" + result_type in self.config(var, []) or "result" in self.config(var, [])

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

        # If no graph variables, use the first serie
        if graph_variables is None:
            graph_variables = set()
            for serie in series:
                for run, results in serie[2].items():
                    graph_variables.add(run)

        # Get all scripts
        for i, (testie, build, all_results) in enumerate(series):
            self.scripts.add(testie)

        # Combine variables as per the graph_combine_variables config parameter
        for tocombine in self.configlist('graph_combine_variables', []):
            tomerge = tocombine.split('+')
            newgraph_variables = []
            run_map = {}
            for run in graph_variables:
                newrun = run.copy()
                vals = []
                for var, val in run.variables.items():
                    if var in tomerge:
                        del newrun.variables[var]
                        vals.append(str(val[1] if type(val) is tuple else val))
                newrun.variables[tocombine] = ', '.join(OrderedSet(vals))
                newgraph_variables.append(newrun)
                run_map[run] = newrun

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

        graphmarkers = self.configlist("graph_markers")

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
                if len(graphmarkers) > 0:
                    build._marker = graphmarkers[i % len(graphmarkers)]
                filtered_series.append((testie, build, new_results))
            else:
                print("No valid data for %s" % build)
        series = filtered_series

        # Transform results to variables as the graph_result_as_variable config
        #  option. It is a dict in the format
        #  result-a+result-b+result-c:new_name
        #  i.e. the first is a + separated list of result and the second member
        #  a new name for the combined variable
        for result_types, var_name in self.configdict('graph_result_as_variable', {}).items():
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
                    nodata = True
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

                    for result_type, results in new_run_results_exp.items():
                        variables = run.variables.copy()
                        variables[var_name] = result_type
                        vvalues.add(result_type)
                        nr = new_run_results.copy()
                        nr.update({'result-'+var_name: results})
                        new_results[Run(variables)] = nr

                if new_results:
                    transformed_series.append((testie, build, new_results))
            if vvalues:
                vars_values[var_name] = vvalues
            series = transformed_series

        # List of static variables to use in filename
        statics = {}

        # Set lines types
        for i, (script, build, all_results) in enumerate(series):
            build._line = graphlines[i % len(graphlines)]
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
                        nbuild._line = graphlines[i % len(graphlines)]
                    nbuild.statics[to_get_out] = value
                    transformed_series.append((testie, nbuild, data))

            series = transformed_series

        versions = []
        vars_all = set()
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

        if nseries == 1 and ndyn > 0 and not (
                            ndyn == 1 and all_num(vars_values[dyns[0]]) and len(vars_values[dyns[0]]) > 2):
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
            for i, value in enumerate(values):
                newserie = {}
                for run, run_results in all_results.items():
                    #                    if (graph_variables and not run in graph_variables):
                    #                        continue
                    if (run.variables[key] == value):
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
                legend_title = self.var_name(key)
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
            legend_title = None
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
                print(statics)
                print(graph_series_label)
                v = {}
                v.update(statics)
                v.update(build.statics)
                build._pretty_name=SectionVariable.replace_variables(v, graph_series_label)

        data_types = dataset.convert_to_xyeb(series, vars_all, key, max_series=self.config('graph_max_series'),
                                             do_x_sort=do_sort, series_sort=self.config('graph_series_sort'))

        if options.output is not None:
            for result_type, data in data_types.items():
                type_filename = npf.build_filename(testie, build, options.output, statics, 'csv', result_type)
                with open(type_filename, 'w') as csvfile:
                    wr = csv.writer(csvfile, delimiter=' ',
                                    quotechar='"', quoting=csv.QUOTE_MINIMAL)
                    for i, (x, y, e, b) in enumerate(data):
                        if (i == 0):
                            wr.writerow(x)
                        wr.writerow(y)
                print("Output written to %s" % type_filename)

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

        for result_type, data in data_types.items():
            if result_type not in matched_set:
                plots[result_type] = ([result_type],1)

        ret = {}
        for i, (figure,n_cols) in plots.items():
            text = self.config("graph_text")

            if len(self.configlist("graph_display_statics")) > 0:
                for stat in self.configlist("graph_display_statics"):
                    if text == '' or text[-1] != "\n":
                        text += "\n"
                    text += self.var_name(stat) + " : " + ', '.join([str(val) for val in vars_values[stat]])
            n_lines = math.ceil((len(figure) + (1 if text else 0)) / float(n_cols))
            fig_name = "subplot" + str(i)

            for isubplot, result_type in enumerate(figure):
                data = data_types[result_type]
                ymin, ymax = (float('inf'), 0)

                plt.subplot(n_lines, n_cols, isubplot + 1)

                if ndyn == 0:
                    """No dynamic variables : do a barplot X=version"""
                    self.do_simple_barplot(result_type, data)
                elif ndyn == 1 and len(vars_all) > 2 and all_num(vars_values[key]):
                    """One dynamic variable used as X, series are version line plots"""
                    self.do_line_plot(key, result_type, data)
                else:
                    """Barplot. X is all seen variables combination, series are version"""
                    self.do_barplot(vars_all, dyns, result_type, data)

                type_config = "" if not result_type else "-" + result_type

                lgd = None
                if ndyn > 0 and bool(self.config_bool('graph_legend', True)):
                    loc = self.config("legend_loc")
                    if loc.startswith("outer"):
                        loc = loc[5:].strip()
                        lgd = plt.legend(loc=loc,bbox_to_anchor=(0., 1, 1., .0), mode=self.config("legend_mode"), borderaxespad=0.,ncol=self.config("legend_ncol"), title=legend_title,bbox_transform=plt.gcf().transFigure)
                    else:
                        lgd = plt.legend(loc=loc,ncol=self.config("legend_ncol"), title=legend_title)

                if key in self.config('var_log', {}):
                    ax = data[0][0]
                    if ax is not None and len(ax) > 1:
                        if ax[0] == 0 and len(ax) > 2:
                            base = ax[2] / ax[1]
                        else:
                            base = ax[1] / ax[0]
                        if base != 2:
                            base = 10
                        plt.xscale('symlog',basex=base)
                        plt.xticks(data[0][0])
                    else:
                        plt.xscale('symlog')


                    xticks = self.scriptconfig("var_ticks", key, default=None)
                    if xticks:
                        plt.xticks([variable.get_numeric(x) for x in xticks.split('+')])
                    plt.gca().xaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter('%d'))


                plt.xlabel(self.var_name(key))

                yname = self.var_name("result", result_type=result_type)
                if yname != "result":
                    plt.ylabel(yname)
                elif len(figure) > 0:
                    plt.ylabel(result_type)

                var_lim = self.scriptconfig("var_lim", "result" + type_config, None)
                if var_lim:
                    n = var_lim.split('-')
                    if len(n) == 2:
                        ymin, ymax = (float(x) for x in n)
                        plt.ylim(ymin=ymin, ymax=ymax)
                    else:
                        plt.ylim(ymax=float(n[0]))
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
                    print("WARNING: Too many points or variables to graph")
                    print("Try reducing the number of dynamic variables : ")
                    for dyn in dyns:
                        print(dyn)
                    return None

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
                type_filename = npf.build_filename(testie, build, options.graph_filename, statics, 'pdf', result_type)
                plt.savefig(type_filename, bbox_extra_artists=(lgd,) if lgd else [], bbox_inches='tight')
                ret[result_type] = None
                print("Graph of test written to %s" % type_filename)
            plt.clf()
        return ret

    def reject_outliers(self, result, testie):
        return testie.reject_outliers(result)

    def do_simple_barplot(self, result_type, data):
        i = 0
        interbar = 0.1
        x = [s[0][0] for s in data]
        y = [s[1][0] for s in data]
        e = [s[2][0] for s in data]
        ndata = len(x)
        nseries = 1
        width = (1 - (2 * interbar)) / nseries

        ticks = np.arange(ndata) + 0.5

        self.format_figure(result_type)
        rects = plt.bar(ticks, y, label=x, color=graphcolor[i % len(graphcolor)], width=width, yerr=e)
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

    def do_line_plot(self, key, result_type, data : XYEB):
        xmin, xmax = (float('inf'), 0)

        for i, (x, y, e, build) in enumerate(data):
            self.format_figure(result_type)
            c = graphcolor[i % len(graphcolor)]

            if not all_num(x):
                if variable.numericable(x):
                    ax = [variable.get_numeric(v) for i, v in enumerate(x)]
                else:
                    ax = [i + 1 for i, v in enumerate(x)]
            else:
                ax = x

            order = np.argsort(ax)

            ax = [ax[i] for i in order]
            y = [y[i] for i in order]
            e = [e[i] for i in order]


            lab = build.pretty_name()
            while lab.startswith('_'):
                lab = lab[1:]
            plt.plot(ax, y, label=lab, color=c, linestyle=build._line, marker=build._marker)
            plt.errorbar(ax, y, yerr=e, marker=' ', label=None, linestyle=' ', color=c)
            xmin = min(xmin, min(ax))
            xmax = max(xmax, max(ax))

        # Arrange the x limits
        if not (key in self.config('var_log', {})):
            var_lim = self.scriptconfig("var_lim", key, key)
            if var_lim and var_lim is not key:
                xmin, xmax = (float(x) for x in var_lim.split('-'))
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
            # plt.gca().set_xlim(xmin, xmax)


    def format_figure(self, result_type):
        ax = plt.gca()

        yunit = self.scriptconfig("var_unit", "result", default="", result_type=result_type)
        yformat = self.scriptconfig("var_format", "result", default=None, result_type=result_type)
        yticks = self.scriptconfig("var_ticks", "result", default=None, result_type=result_type)
        if self.result_in_list('var_grid',result_type):
            plt.grid(True)
        isLog = False
        if self.result_in_list('var_log', result_type):
            plt.yscale('symlog' if yformat else 'log')
            isLog = True
        if yformat is not None:
            formatter = FormatStrFormatter(yformat)
            ax.yaxis.set_major_formatter(formatter)
        elif (yunit.lower() == "bps" or yunit.lower() == "byteps"):
            formatter = FuncFormatter(self.bits if yunit.lower() == "bps" else self.bytes)
            ax.yaxis.set_major_formatter(formatter)
        elif (yunit.lower() == "%" or yunit.lower().startswith("percent")):
            def to_percent(y, position):
                s = str(100 * y)

                if matplotlib.rcParams['text.usetex'] is True:
                    return s + r'$\%$'
                else:
                    return s + '%'

            ax.yaxis.set_major_formatter(FuncFormatter(to_percent))
        else:
            if not isLog:
                ax.get_yaxis().get_major_formatter().set_useOffset(False)
        if yticks:
            plt.yticks([variable.get_numeric(y) for y in yticks.split('+')])

    def do_barplot(self, vars_all, dyns, result_type, data):
        nseries = len(data)

        self.format_figure(result_type)

        # If more than 20 bars, do not print bar edges
        maxlen = max([len(serie_data[0]) for serie_data in data])

        if nseries * maxlen > 20:
            edgecolor = "none"
            interbar = 0.05
        else:
            edgecolor = None
            interbar = 0.1

        width = (1 - (2 * interbar)) / len(data)
        ind = np.arange(len(vars_all))

        for i, (x, y, e, build) in enumerate(data):
            plt.bar(interbar + ind + (i * width), y, width,
                    label=str(build.pretty_name()), color=graphcolor[i % len(graphcolor)], yerr=e,
                    edgecolor=edgecolor)

        ss = self.combine_variables(vars_all, dyns)

        if not bool(self.config_bool('graph_x_label', True)):
            ss = ["" for i in range(len(vars_all))]
        plt.xticks(interbar + ind + (width * len(data) / 2.0), ss,
                   rotation='vertical' if (sum([len(s) for s in ss]) > 80) else 'horizontal')
