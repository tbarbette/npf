import sys
from npf.graph import Graph
if sys.version_info < (3, 7):
    from orderedset import OrderedSet
else:
    from ordered_set import OrderedSet
from collections import OrderedDict

# Extract the variable key so it becomes a serie
def extract_variable_to_series(grapher, key, vars_values, all_results, dyns, build, script) -> Graph:
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
        if len(grapher.graphmarkers) > 0:
            nb._marker = grapher.graphmarkers[i % len(grapher.graphmarkers)]
        series.append((script, nb, newserie))
        grapher.glob_legend_title = grapher.var_name(key)
    vars_all = list(new_varsall)

    if len(dyns) == 1:
        key = dyns[0]
        do_sort = True
    elif len(dyns) == 0:
        do_sort = True
    else:
        key = "Variables"
        do_sort = False
    do_sort = grapher.config_bool_or_in('graph_x_sort', key, default=do_sort)
    if (do_sort):
        vars_all.sort()
    graph = Graph(grapher)
    graph.do_sort = do_sort
    graph.key = key
    graph.vars_all = vars_all
    graph.vars_values = vars_values
    graph.series = series
    return graph
