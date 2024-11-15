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

INDENT_DATA = False
TIMEOUT = 60  # seconds


def prepare_notebook_export(datasets: List[tuple], all_results_df: pd.DataFrame, options, config):
    path = options.notebook_path

    dataset = datasets[0]
    test, _build, _runs = dataset
    var_names = dict(test.config["var_names"])

    x_vars = list(test.variables.dynamics().keys())

    y_vars = list(filter(lambda x: x.startswith("y_"), all_results_df.columns))
    y_vars = [y.lstrip('y_') for y in y_vars]
    data = all_results_df.rename(columns=lambda c: c.lstrip("y_"))

    # variables that get replaced in the template notebook
    variables = {
        "name": test.get_title(),
        "var_names": var_names,
        "x_vars": x_vars,
        "x_names": get_name(x_vars, var_names),
        "y_vars": y_vars,
        "y_names": get_name(y_vars, var_names),
        "data": dumps(data.to_dict(orient="records"), indent=4 if INDENT_DATA else None),
        "dir_name": os.path.dirname(path),
        "file_path": ".".join(path.split(".")[:-1]),  # drops the extension
        "file_name": ".".join(path.split("/")[-1].split(".")[:-1]),
    }

    # both update and force options are not allowed
    if options.update_nb and options.force_nb:
        print("\nBoth --update-nb and --force-nb options are not allowed together.")
        user_input = input("Do you want to overwrite the notebook? (yes/no): ")
        if user_input.lower() != 'yes':
            options.force_nb = False

    # check if the notebook already exists and ask the user if they want to overwrite it
    if os.path.exists(path) and not options.force_nb:
        if options.update_nb:
            update_notebook(path, variables.get("data"), options)
            return
        else:  # no update or force is specified
            print("\nNotebook already exists at the provided path. Use --update-nb to try to update the data or --force-nb to overwrite the notebook.")
            user_input = input("Do you want to overwrite it? (yes/no): ")
            if user_input.lower() != 'yes':
                print("Cancelled notebook export.")
                return

    # TODO: Select a suitable key when there are multiple values
    key = x_vars[0]

    # TODO: there might be many result types
    result_type = y_vars[0]

    n_values = len(all_results_df[x_vars].value_counts())
    ndyn = len(x_vars)
    if ndyn > 1:
        ndyn -= 1

    graph_type = decide_graph_type(config, n_values, all_results_df, key, result_type, ndyn, isubplot=0)

    # read template notebook
    with open(options.template_nb_path) as f:
        nb = nbf.read(f, as_version=4)

    # keep only cells with the specified tag
    nb.cells = [cell for cell in nb.cells if has_tag(cell, graph_type)]

    # remove cell tags except for the "data" tag
    for cell in nb.cells:
        if "data" in cell.metadata.get("tags", []):
            cell.metadata.tags = ["data"]
        else:
            cell.metadata.pop("tags", None)

    # render cells by replacing variables in the template using jinja2
    for cell in nb.cells:
        cell_template = Template(cell.source)
        cell.source = cell_template.render(variables)

    if options.execute_nb:
        exec_and_export_nb(nb, path, options)
    else:
        export_nb(nb, path)


def export_nb(nb, path: str):
    """Exports the notebook to the specified path."""
    with open(path, 'w') as f:
        nbf.write(nb, f)  # write notebook to file
        print("Notebook exported to", path)


def exec_and_export_nb(nb, path: str, options):
    try:
        ep = ExecutePreprocessor(timeout=TIMEOUT, kernel_name=options.nb_kernel)
        start_time = time.time()
        ep.preprocess(nb, {'metadata': {'path': os.path.dirname(path)}})
        print("Notebook executed in %.2f seconds." %
              (time.time() - start_time))
    except CellExecutionError:
        print("Notebook execution failed.")
        raise
    except NoSuchKernel:
        print("\n[ERROR] No such kernel. Try the following to fix this issue:")
        print("\tList kernels with `jupyter kernelspec list` and specify another kernel.")
        print("\tIf no kernel exists, install one with `python3 -m pip install ipykernel` and `python3 -m ipykernel install --user`.\n")
        raise
    finally:
        export_nb(nb, path)


def update_notebook(path: str, new_data: str, options):
    """Replace the data in the existing notebook and execute it."""
    # read the existing notebook
    with open(path) as f:
        nb = nbf.read(f, as_version=4)

        # find the cell with the data tag and replace the data
        updated = 0
        for cell in nb.cells:
            if has_tag(cell, "data"):
                updated += 1
                cell.source = "data = " + new_data

        if updated >= 1:
            print("Data updated in the notebook.")
        else:
            print("No cell with the 'data' tag found in the notebook.")

        if options.execute_nb:
            exec_and_export_nb(nb, path, options)


def has_tag(cell, tag: str) -> bool:
    """Returns True if the cell has the specified tag or "all"."""
    tags = cell.metadata.get("tags", [])
    return tag in tags or "all" in tags


def get_name(var, var_names):
    """Returns the name associated with a variable or a list of variables."""
    if isinstance(var, list):
        return [get_name(v, var_names) for v in var]
    return var_names[var] if var in var_names else var
