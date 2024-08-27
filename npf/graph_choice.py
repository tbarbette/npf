from npf import npf

# types of graphs: bar, line, boxplot, simple_bar


def decide_graph_type(config, n_values, vars_values, key, result_type, ndyn, isubplot):
    graph_type = "bar"
    if ndyn == 0:
        graph_type = "boxplot" if n_values == 1 else "simple_bar"
    elif ndyn == 1 and n_values > 2 and npf.all_num(vars_values[key]):
        graph_type = "line"
    graph_types = config("graph_type", [])

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
        graph_type = graph_types[isubplot if isubplot < len(
            graph_types) else len(graph_types) - 1]

    if ndyn == 0 and graph_type == "line":
        print("WARNING: Cannot graph", graph_type,
              "as a line without dynamic variables")
        graph_type = "simple_bar"

    return graph_type
