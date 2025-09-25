        
from collections import OrderedDict
from typing import List

from ordered_set import OrderedSet

from npf.models.units import numericable
from npf.models.series import Series
from npf.models.units import get_numeric


def combine_variables(series: List[Series], tocombine, graph_variables):
    """
    Combines variables in a dataset based on specified criteria and updates the series and graph variables.

    Args:
        series (List[Series]): A list of tuples where each tuple contains test, build, and all_results.
                               `all_results` is a dictionary mapping runs to their results.
        tocombine (Union[str, Tuple[str, str]]): The variable(s) to combine.
                                                 If a tuple, the first element specifies the variables to combine (separated by '+'),
                                                 and the second element specifies the name of the new combined variable.
                                                 If just a string, it is used as both the variables to combine and the name of the new variable.
        graph_variables (List[Run]): A list of `Run` objects, each containing a dictionary of variables.

    Returns:
        List[Series]: A new list of series with updated variables and results after combining the specified variables.

    Notes:
        - If the combined variable values are numeric, they are converted to numeric types.
        - The function ensures that the combined variable names are unique.
        - The `run_map` is used to map old runs to their updated versions with combined variables.
    """

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
    for i, (test, build, all_results) in enumerate(series):
        new_all_results = {}
        for run, run_results in all_results.items():
            newrun = run_map.get(run, None)
            if newrun is not None:
                new_all_results[newrun] = run_results
        newseries.append((test, build, new_all_results))

    return newseries, graph_variables
