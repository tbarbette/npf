import io
from collections import OrderedDict
from typing import List

import numpy as np
import matplotlib

from src.testie import Run

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter,ScalarFormatter
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
        if type(x) is str:
            return False
    return True

class Grapher:
    def __init__(self):
        self.scripts = set()

    def config(self, var, default=None):
        for script in self.scripts:
            if var in script.config:
                return script.config[var]
        return default

    def scriptconfig(self, var, key, default):
        for script in self.scripts:
            if var in script.config:
                return script.config.get_dict(var).get(key,default)
        return None


    def var_name(self, key):
        return self.scriptconfig("var_names",key,key);

    def var_unit(self, key):
        return self.scriptconfig("var_unit",key,default=None);

    def bits(self, x, pos):
        return self.formatb(x,pos,"Bits")
    def bytes(self, x, pos):
        return self.formatb(x,pos,"Bytes")

    def formatb(self,x, pos,unit):
        if (x >= 1000000000):
            return "%.2f G%s/s" % (x/1000000000,unit)
        elif (x >= 1000000):
            return "%.2f M%s/s" % (x/1000000,unit)
        elif (x >= 1000):
            return "%.2f K%s/s" % (x/1000,unit)
        else:
            return "%.2f %s/s" % (x,unit)

    def graph(self,filename, options, graph_variables:List[Run] = None, title=False, series=[]):
        """series is a list of triplet (script,build,results) where
        result is the output of a script.execute_all()"""
        vars_values = {}
        vars_all = set()
        versions=[]

        # if graph_variables:
        #     for i, gv in enumerate(graph_variables):
        #         for k,v in gv.variables.items():
        #             if type(v) is tuple:
        #                 graph_variables[i][k] = v[1]

        ymin,ymax=(float('inf'),0)
        filtered_series=[]

        #If no graph variables, use the first serie
        if graph_variables==None:
            graph_variables=[]
            for run,results in series[0][2].items():
                 graph_variables.append(run)

        #Data transformation
        for i,(testie,build,all_results) in enumerate(series):
            versions.append(build.pretty_name())
            self.scripts.add(testie)
            new_results = {}
            for run,results in all_results.items():
                if run in graph_variables:
                    if results:
                        if options.graph_reject_outliers:
                            results = self.reject_outliers(np.asarray(results), testie)
                        else:
                            results = np.asarray(results)
                        ymax = max(ymax, max(results))
                        ymin = min(ymin, min(results))
                        if not self.config('zero_is_error') or \
                            (ymax != 0 and ymin != 0) :
                            new_results[run] = results
                    vars_all.add(run)
                    for k,v in run.variables.items():
                        vars_values.setdefault(k,set()).add(v)

            if new_results:
                filtered_series.append((testie,build,new_results))
            else:
                print("No valid data for %s" % build)
        series=filtered_series
        vars_all = list(vars_all)
        vars_all.sort()

        is_multiscript = len(self.scripts) > 1


        #self.ydiv = math.exp(math.log(ymax,10),10)

        dyns = []

        for k,v in vars_values.items():
            if len(v) > 1:
                dyns.append(k)

        ndyn = len(dyns)
        nseries = len(series)

        if nseries == 1 and ndyn > 0 and not (ndyn == 1 and all_num(vars_values[dyns[0]]) and len(vars_values[dyns[0]]) > 2):
            """Only one serie: expand one dynamic variable as serie, but not if it was plotable as a line"""
            script,build,all_results = series[0]
            if self.config("var_series") and self.config("var_series") in dyns:
                key=self.config("var_series")
            else:
                key=None
                #First pass : use the non-numerical variable with the most points
                n_val=0
                for i in range(ndyn):
                    k=dyns[i]
                    if not all_num(vars_values[k]):
                        if (len(vars_values[k]) > n_val):
                            key = k
                            n_val = len(vars_values[k])
                #Second pass if that missed, use the numerical variable with the less point if dyn=2 or the most points
                n_val=0 if ndyn > 2 else 999
                for i in range(ndyn):
                    k=dyns[i]
                    if (ndyn > 2 and len(vars_values[k]) > n_val) or (ndyn <= 2 and len(vars_values[k]) < n_val):
                        key = k
                        n_val = len(vars_values[k])

            # if graph_serie:
            #     key=graph_serie
            dyns.remove(key)
            ndyn-=1
            series=[]
            versions=[]
            values = list(vars_values[key])
            values.sort()
            new_varsall = set()
            for value in values:
                newserie={}
                for run,results in all_results.items():
                    if (graph_variables and not run in graph_variables):
                        continue
                    if (run.variables[key] == value):
                        newrun = run.copy()
                        del newrun.variables[key]
                        newserie[newrun] = results
                        new_varsall.add(newrun)

                series.append((script,build,newserie))
                if type(value) is tuple:
                    value=value[1]
                versions.append(value)
                legend_title=self.var_name(key)
            nseries=len(series)
            vars_all = list(new_varsall)
            vars_all.sort()
        else:
            key="version"
            legend_title=None


        ax = plt.gca()


        xlog = False
        ax = plt.gca()
        yunit = self.var_unit("result").lower()
        if yunit and yunit[0] == '/':
            ydiv = 1000000000
        else:
            ydiv = 1

        if (yunit == "bps" or yunit == "byteps"):
            formatter = FuncFormatter(self.bits if self.var_unit("result").lower() == "bps" else self.bytes)
            ax.yaxis.set_major_formatter(formatter)
        else:
            ax.get_yaxis().get_major_formatter().set_useOffset(False)

        if ndyn == 0:
            """No dynamic variables : do a barplot X=version"""

            # If more than 20 bars, do not print bar edges
            if nseries > 20:
                edgecolor = "none"
                interbar = 0.05
            else:
                edgecolor = None
                interbar = 0.1

            data=[]
            for a in [all_results for script,build,all_results in series]:
                v = a[vars_all[0]]
                if v is not None:
                    data.append(np.mean(v))
                else:
                    data.append(np.nan)

            i=0

            nbars=len(versions)
            width = (1 - (2 * interbar)) / len(versions)

            xpos = np.arange(len(versions)) + interbar
            ticks = np.arange(len(versions)) + 0.5

            plt.bar(xpos,data,label=versions[i],color=graphcolor[i % len(graphcolor)],width=width)
            plt.xticks(ticks,versions, rotation='vertical' if (len(versions) > 10) else 'horizontal')
            plt.gca().set_xlim(0, len(versions))
        elif ndyn==1 and len(vars_all) > 2:
            """One dynamic variable used as X, series are version line plots"""
            if (ndyn > 0):
                key = dyns[0]


            xmin,xmax = (float('inf'),0)

            data=[]
            for all_results in [all_results for script,build,all_results in series]:
                x=[]
                y=[]
                e=[]
                for run in vars_all:
                    result = all_results.get(run, None)

                    x.append(run.print_variable(key))
                    if result is not None:
                        result = np.asarray(result) / ydiv
                        y.append(np.mean(result))
                        e.append(np.std(result))
                    else:
                        y.append(np.nan)
                        e.append(np.nan)
                order=np.argsort(x)
                data.append((np.array(x)[order],np.array(y)[order],np.array(e)[order]))

            for i,ax in enumerate(data):
                c = graphcolor[i % len(graphcolor)]
                plt.plot(ax[0],ax[1],label=versions[i],color=c)
                plt.errorbar(ax[0],ax[1],yerr=ax[2], fmt='o',label=None,color=c)
                xmin = min(xmin , min(ax[0]))
                xmax = max(xmax , max(ax[0]))

            if key in self.config('var_log',{}):
                xlog=True
            #Arrange the x limits
            if not xlog:
                var_lim = self.scriptconfig("var_lim",key,key)
                if var_lim and var_lim is not key:
                    xmin,xmax = (float(x) for x in var_lim.split('-'))
                else:
                    if abs(xmin) < 10 and abs(xmax) < 10:
                        xmin -= 1
                        xmax += 1
                        pass
                    else:
                        base = float(max(10,math.ceil((xmax - xmin) / 10)))
                        if (xmin > 0):
                            xmin = int(math.floor(xmin / base)) * base
                        if (xmax > 0):
                            xmax = int(math.ceil(xmax / base)) * base


                plt.gca().set_xlim(xmin,xmax)

            plt.legend(loc=self.config("legend_loc"), title=legend_title)
        else:
            """Barplot. X is all seen variables combination, series are version"""

            # If more than 20 bars, do not print bar edges
            maxlen = max([len(all_results) for (script, build, all_results) in series])

            if nseries * maxlen > 20:
                edgecolor = "none"
                interbar = 0.05
            else:
                edgecolor = None
                interbar = 0.1

            data=[]
            for all_results in [all_results for script,build,all_results in series]:
                y=[]
                e=[]
                for run in vars_all:
                    result = all_results.get(run,None)
                    if result is not None:
                        y.append(np.mean(result))
                        e.append(np.std(result))
                    else:
                        y.append(np.nan)
                        e.append(np.nan)
                data.append((y,e))

            width = (1-(2*interbar)) / len(versions)
            ind = np.arange(len(vars_all))

            for i,serie in enumerate(data):
                plt.bar(interbar + ind + (i * width),serie[0],width,
                        label=str(versions[i]),color=graphcolor[i % len(graphcolor)], yerr=serie[1],edgecolor=edgecolor)

            ss = []

            if ndyn==1:
                key = dyns[0]
                for run in vars_all:
                    s = []
                    for k,v in run.variables.items():
                        if k in dyns:
                            s.append("%s" % str(v[1] if type(v) is tuple else v))
                    ss.append(','.join(s))
            else:
                if ndyn == 0:
                    key = "version"
                else:
                    key = "Variables"

                use_short=False
                short_ss=[]
                for run in vars_all:
                    s = []
                    short_s = []
                    for k,v in run.variables.items():
                        if k in dyns:
                            v = str(v[1] if type(v) is tuple else v)
                            s.append("%s = %s" % (self.var_name(k),v))
                            short_s.append("%s = %s" % (k if len(k) < 6 else k[:3], v))
                    vs = ','.join(s)
                    ss.append(vs)
                    if len(vs) > 30:
                        use_short = True
                    short_ss.append(','.join(short_s))
                if use_short:
                    ss=short_ss

            plt.xticks(interbar + ind + (width * len(versions) / 2.0)  , ss, rotation='vertical' if (sum([len(s) for s in ss]) > 80) else 'horizontal')

        if ndyn > 0 and self.config('graph_legend',True):
            plt.legend(loc=self.config("legend_loc"), title=legend_title)

        if "result" in self.config('var_log',{}):
            plt.yscale('log')

        if xlog:
            plt.xscale('log')

        plt.xlabel(self.var_name(key))

        if "result" in self.config("var_names",{}):
            plt.ylabel(self.config("var_names")["result"])

        var_lim = self.scriptconfig("var_lim", "result", None)
        if var_lim:
            n = var_lim.split('-')
            if len(n) == 2:
                ymin, ymax = (float(x) for x in n)
                plt.ylim(ymin=ymin, ymax = ymax)
            else:
                plt.ylim(ymin=float(n[0]))
        else:
            if (ymin >= 0 and plt.ylim()[0] < 0):
                plt.ylim(0,plt.ylim()[1])

            if (ymin < ymax/5):
                plt.ylim(ymin=0)


        if options.graph_size:
            fig = plt.gcf()
            fig.set_size_inches(options.graph_size[0], options.graph_size[1])

        if title:
            plt.title(title)
        try:
            plt.tight_layout()
        except ValueError:
            print("WARNING: Too many points or variables to graph")
            print("Try reducing the number of dynamic variables : ")
            for dyn in dyns:
                print(dyn)
            return None

        if (not filename):
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            ret = buf.read()
        else:
            if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
                os.makedirs(os.path.dirname(filename))
            plt.savefig(filename)
            ret = None
            print("Graph of test written to %s" % filename)
        plt.clf()
        return ret

    def reject_outliers(self, result, testie):
        return testie.reject_outliers(result)

