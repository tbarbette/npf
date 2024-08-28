from npf import npf
from npf.graph import Graph
from npf.variable_to_series import extract_variable_to_series

# Convert a list of series to a graph object
#  if the list has a unique item and there are dynamic variables, one
#  dynamic variable will be extracted to make a list of serie
def series_to_graph(grapher, series, dyns, vars_values, vars_all):
    nseries = len(series)

    ndyn = len(dyns)
    if grapher.options.do_transform and (nseries == 1 and ndyn > 0 and not grapher.options.graph_no_series and not (
                        ndyn == 1 and npf.all_num(vars_values[dyns[0]]) and len(vars_values[dyns[0]]) > 2) and dyns[0] != "time"):
        """Only one serie: expand one dynamic variable as serie, but not if it was plotable as a line"""
        script, build, all_results = series[0]
        if grapher.config("var_serie") and grapher.config("var_serie") in dyns:
            key = grapher.config("var_serie")
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
            graph = extract_variable_to_series(grapher, key, vars_values, all_results, dyns, build, script)

    else:
        grapher.glob_legend_title = None
        if ndyn == 0:
            key = "version"
            do_sort = False
        elif ndyn == 1:
            key = dyns[0]
            do_sort = True
        else:
            key = "Variables"
            do_sort = False
        graph = Graph(grapher)
        graph.key = key
        graph.do_sort = do_sort
        graph.vars_all = vars_all
        graph.vars_values = vars_values
        graph.series = series
    return graph
