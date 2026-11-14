from typing import List
import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor, CellExecutionError
from jupyter_client.kernelspec import NoSuchKernel
from jinja2 import Template

from decimal import Decimal
import math
import re
import os
import sys
import time

import pandas as pd
from npf.output.graph.graph_choice import decide_graph_type

TIMEOUT = 60  # seconds
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.ipynb")
# Columns of the results that are not variables
NOT_VARIABLES = ("build", "test_index", "run_index", "index")


def _python_value(v):
    """A value of the results, as a Python literal: the data cell is Python, where JSON's NaN, null and true are not
    defined. Missing values become None, which pandas reads as NaN."""
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, "item"):  # numpy scalars
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def python_data(df):
    """The results of df, as the Python literal of a list of records"""
    return repr([{k: _python_value(v) for k, v in r.items()} for r in df.to_dict(orient="records")])


def prepare_notebook_export(datasets: List[tuple], all_results_df: pd.DataFrame, options, config):
    path = options.notebook_path

    dataset = datasets[0]
    test, _build, _runs = dataset
    var_names = dict(test.config["var_names"])

    # The variables that have several values in the results: test.variables.dynamics() names the variables of a
    # covariable group "covariable"
    x_vars = [c for c in all_results_df.columns if not c.startswith("y_") and c not in NOT_VARIABLES and
              all_results_df[c].nunique() > 1]

    # Results are the y_ columns: remove the prefix, not all leading y and _ (as lstrip does)
    y_vars = [c[2:] for c in all_results_df.columns if c.startswith("y_")]
    data = all_results_df.rename(columns=lambda c: c[2:] if c.startswith("y_") else c)

    # variables that get replaced in the template notebook
    variables = {
        "name": test.get_title(),
        "var_names": var_names,
        "x_vars": x_vars,
        "x_names": get_name(x_vars, var_names),
        "y_vars": y_vars,
        "y_names": get_name(y_vars, var_names),
        "data": python_data(data),
        "dir_name": os.path.dirname(path),
        "file_path": ".".join(path.split(".")[:-1]),  # drops the extension
        "file_name": ".".join(path.split("/")[-1].split(".")[:-1]),
    }

    # both update and force options are not allowed
    if options.update_nb and options.force_nb:
        print("\nBoth --update-nb and --force-nb options are not allowed together.")
        if not sys.stdin.isatty():
            options.force_nb = False
        elif input("Do you want to overwrite the notebook? (yes/no): ").lower() != 'yes':
            options.force_nb = False

    # check if the notebook already exists and ask the user if they want to overwrite it
    if os.path.exists(path) and not options.force_nb:
        if options.update_nb:
            update_notebook(path, variables.get("data"), options)
            return
        else:  # no update or force is specified
            print("\nNotebook already exists at the provided path. Use --update-nb to try to update the data or --force-nb to overwrite the notebook.")
            # Without a terminal (e.g. in a script), there is nobody to answer
            if not sys.stdin.isatty() or input("Do you want to overwrite it? (yes/no): ").lower() != 'yes':
                print("Cancelled notebook export.")
                return

    # TODO: there might be many result types
    result_type = y_vars[0] if y_vars else None

    if not x_vars:
        # No variable has several values: the mean of each result
        graph_type = "simple_bar"
    else:
        # TODO: Select a suitable key when there are multiple values
        key = x_vars[0]

        n_values = len(all_results_df[x_vars].value_counts())
        ndyn = len(x_vars)
        if ndyn > 1:
            ndyn -= 1

        graph_type = decide_graph_type(config, n_values, all_results_df, key, result_type, ndyn, isubplot=0)

    # read template notebook
    with open(options.template_nb_path or TEMPLATE) as f:
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
    """Executes the notebook, then writes it. NPF ran all the tests before: a notebook that cannot run is written as
    it is, with an error, but does not stop NPF."""
    try:
        ep = ExecutePreprocessor(timeout=TIMEOUT, kernel_name=options.nb_kernel)
        start_time = time.time()
        ep.preprocess(nb, {'metadata': {'path': os.path.dirname(path)}})
        print("Notebook executed in %.2f seconds." %
              (time.time() - start_time))
    except CellExecutionError as e:
        print("[ERROR] Notebook execution failed:\n%s" % str(e).strip().split("\n")[-1])
    except NoSuchKernel:
        print("\n[ERROR] No such kernel. Try the following to fix this issue:")
        print("\tList kernels with `jupyter kernelspec list` and specify another kernel.")
        print("\tIf no kernel exists, install one with `python3 -m pip install ipykernel` and `python3 -m ipykernel install --user`.\n")
    except RuntimeError as e:
        # The kernel could not start, e.g. its python has no ipykernel
        print("\n[ERROR] Could not run the notebook with the kernel %s: %s" % (options.nb_kernel, e))
        print("\tCheck that the python of the kernel (`jupyter kernelspec list`) has ipykernel, or use --nb-kernel, or "
              "--disable-nb-exec.\n")
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
        else:
            export_nb(nb, path)


def has_tag(cell, tag: str) -> bool:
    """Returns True if the cell has the specified tag or "all"."""
    tags = cell.metadata.get("tags", [])
    return tag in tags or "all" in tags


def get_name(var, var_names):
    """Returns the name associated with a variable or a list of variables."""
    if isinstance(var, list):
        return [get_name(v, var_names) for v in var]
    return var_names[var] if var in var_names else var
