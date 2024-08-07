from typing import List
import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor, CellExecutionError
from jupyter_client.kernelspec import NoSuchKernel
from jinja2 import Template

from json import dumps
import re
import os
import time

import pandas as pd
from npf.graph_choice import decide_graph_type

TEMPLATE_PATH = "npf/types/notebook/template.ipynb"
INDENT_DATA = False


def prepare_notebook_export(datasets: List[tuple], all_results_df: pd.DataFrame, path: str, config):
    # SIMTODO: (help) why could there be multiple datasets?
    # TODO: with npf-compare there might be multiple dataset. Try the netperf vs iperf experiment from the examples
    dataset = datasets[0]
    test, build, runs = dataset
    var_names = dict(test.config["var_names"])

    x_vars = list(test.variables.dynamics().keys())
    y_vars = list(filter(lambda x: x.startswith("y_"), all_results_df.columns))

    # variables that get replaced in the template notebook
    variables = {
        "name": test.get_title(),
        "var_names": var_names,
        "x_vars": x_vars,
        "x_names": get_name(x_vars, var_names),
        "y_vars": y_vars,
        "y_names": get_name([y.lstrip('y_') for y in y_vars], var_names),
        "data": dumps(all_results_df.to_dict(orient="records"), indent=4 if INDENT_DATA else None),
        "dir_name": os.path.dirname(path),
        "file_path": ".".join(path.split(".")[:-1]),  # remove extension
        "file_name": ".".join(path.split("/")[-1].split(".")[:-1]),
    }

    key = x_vars[0]
    # TODO : Select a suitable key when there are multiple values

    # TODO : there might be many result types
    result_type = y_vars[0]

    n_values = len(all_results_df[x_vars].value_counts())

    # TODO: when there are multiple series, we should select one that is in the legend (the other is in the y-axis)
    # graph type is decided based on the configuration and the data
    graph_type = decide_graph_type(config,
                                   n_values,
                                   data_for_key=sorted(all_results_df[key].unique().tolist()),
                                   result_type=result_type.lstrip("y_"),
                                   ndyn=len(x_vars), isubplot=0)

    print("> Notebook graph type:", graph_type)

    # read template notebook
    with open(TEMPLATE_PATH) as f:
        nb = nbf.read(f, as_version=4)

    # keep only cells with the specified tag
    nb.cells = [cell for cell in nb.cells if has_tag(cell, graph_type)]

    # remove cell tags
    for cell in nb.cells:
        cell.metadata.pop("tags", None)

    # render cells by replacing variables in the template using jinja2
    for cell in nb.cells:
        cell_template = Template(cell.source)
        cell.source = cell_template.render(variables)

    # execute notebook and save it to file
    try:
        # SIMTODO: specify timeout, and kernel_name?
        ep = ExecutePreprocessor(timeout=60, kernel_name='python3')
        start_time = time.time()
        ep.preprocess(nb, {'metadata': {'path': os.path.dirname(path)}})
        print("Notebook executed in %.2f seconds." %
              (time.time() - start_time))
    except CellExecutionError:
        print("Notebook execution failed.")
        raise
    except NoSuchKernel:
        print("\n[ERROR] No such kernel. Try the following to fix this issue:")
        # SIMTODO: add argument
        print("\tList kernels with `jupyter kernelspec list` and specify another kernel.")
        print("\tIf no kernel exists, install one with `python3 -m pip install ipykernel` and `python3 -m ipykernel install --user`.\n")
        raise
    finally:
        with open(path, 'w') as f:
            nbf.write(nb, f)  # write notebook to file
            print("Notebook exported to", path)


def has_tag(cell, tag) -> bool:
    """Returns True if the cell has the specified tag or "all"."""
    tags = cell.metadata.get("tags", [])
    return tag in tags or "all" in tags


def get_name(var: str | list[str], var_names: dict[str, str]) -> str | list[str]:
    """Returns the name associated with a variable or a list of variables."""
    if isinstance(var, list):
        return [get_name(v, var_names) for v in var]
    return var_names[var] if var in var_names else var
