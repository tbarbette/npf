from pygtrie import Trie
from npf.models.dataset import mask_from_filter
from npf.models.units import np


from npf.output.graph.colors import lighter
import matplotlib.pyplot as plt
import numpy as np


def do_barplot(graph, axis, vars_all, dyns, result_type, data, shift, show_values=False, horizontal=False, data_types=None):
        nseries = len(data)

        isLog = graph.format_figure(axis,result_type,shift)

        # If more than 20 bars, do not print bar edges
        maxlen = max([len(serie_data[0]) for serie_data in data])

        if nseries * maxlen > 20:
            edgecolor = "none"
            interbar = 0.05
        else:
            edgecolor = None
            interbar = 0.1

        #Filters allow to hatch bars where a value of another variable is higher than something. Stack not implemented yet.
        filters = graph.configdict("graph_filter_by", default={})

        interbar = graph.config('graph_bar_inter', default=interbar)
        stack = graph.config_bool('graph_bar_stack')
        do_hatch = graph.config_bool('graph_bar_hatch', default=False)
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

        def common_args(build):
            return {
                'label':str(build.pretty_name()),
                'yerr':std if not horizontal else None,
                'xerr':std if horizontal else None,
                }

        def hatch_args(build):
            return {
                'color':lighter(build._color, 0.6, 255),
                'edgecolor':lighter(build._color, 0.6, 0),
                'hatch':patterns[i]
                }

        def nohatch_args(build):
            return {
                'color':build._color,
                'edgecolor':edgecolor,
                'hatch':None
                }

        if stack:
            last = 0
            for i, (x, y, e, build) in enumerate(data):
                y = np.asarray([0.0 if np.isnan(x) else x for x in y])
                last = last + y

            for i, (x, y, e, build) in enumerate(data):
                y = np.asarray([0.0 if np.isnan(x) else x for x in y])
                std = np.asarray([std for mean,std,raw in e])
                rects = func(ind, last, width,
                    **common_args(build),
                    **(hatch_args(build) if do_hatch else nohatch_args(build))
                    )
                last = last - y
        else:
            for i, (x, y, e, build) in enumerate(data):
                std = np.asarray([std for mean,std,raw in e])
                fx = interbar + ind + (i * width)
                if result_type in filters:
                    mask = mask_from_filter(filters[result_type],data_types,build,ax=x,y=y)

                    args = common_args(build)
                    nargs = {'label':args['label']}
                    if mask is None:
                        continue
                    from itertools import compress
                    rects = func(list(compress(fx, ~mask)), list(compress(y,~mask)), width,
                            **nargs,
                            yerr = list(compress(args['yerr'], ~mask)) if args['yerr'] is not None else None,
                            **hatch_args(build)
                    )

                    func(list(compress(fx,mask)), list(compress(y,mask)), width,
                        **nargs,
                        yerr = list(compress(args['yerr'], mask)) if args['yerr'] is not None else None,
                        **nohatch_args(build)
                    )
                else:
                    rects = func(fx, y, width,
                        **common_args(build),
                        **(hatch_args(build) if do_hatch else nohatch_args(build))
                    )
                graph.write_labels(show_values, rects, plt, build._color, isLog=isLog)

        ss = combine_variables_late(graph, vars_all, dyns)

        if not bool(graph.config_bool('graph_x_label', True)):
            ss = ["" for i in range(n_series)]

        ticks(ind if stack else interbar + ind + (width * (len(data) - 1) / 2.0), ss,
                   rotation='vertical' if (sum([len(s) for s in ss]) > 80) and not horizontal  else 'horizontal')
        return True, len(data)

def combine_variables_late(graph, run_list, variables_to_merge):
        ss = []
        if len(variables_to_merge) == 1:
            for run in run_list:
                s = []
                for k, v in run.read_variables().items():
                    if k in variables_to_merge:
                        s.append("%s" % str(v[1] if type(v) is tuple else v))
                ss.append(','.join(s))
        else:
            use_short = False
            short_ss = []
            for run in run_list:
                s = []
                short_s = {}
                for k, v in run.read_variables().items():
                    if k in variables_to_merge:
                        v = str(v[1] if type(v) is tuple else v)
                        s.append("%s = %s" % (graph.var_name(k), v))
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
