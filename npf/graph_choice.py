from npf import npf


def decide_graph_type(grapher, key, vars_all, vars_values, result_type, ndyn, isubplot):
    graph_type = False
    if ndyn == 0:
        graph_type = "boxplot" if len(vars_all) == 1 else "simple_bar"
    elif ndyn == 1 and len(vars_all) > 2 and npf.all_num(vars_values[key]):
        graph_type = "line"
    graph_types = grapher.config("graph_type", [])

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
