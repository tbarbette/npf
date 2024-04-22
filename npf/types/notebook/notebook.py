import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor, CellExecutionError
from jupyter_client.kernelspec import NoSuchKernel
from jinja2 import Template

from json import dumps
import re
import os
import time

INDENT_DATA = True


def prepare_notebook_export(datasets, all_results_df, path):
    # SIMTODO: (help) why could there be multiple datasets?
    dataset = datasets[0]
    test, build, runs = dataset
    var_names = dict(datasets[0][0].config["var_names"])

    x_vars = list(test.variables.dynamics().keys())
    y_vars = list(list(runs.values())[0].keys())

    # variables that get replaced in the template notebook
    variables = {
        "name": test.get_title(),
        "x_vars": x_vars,
        "x_names": get_name(x_vars, var_names),
        "y_vars": y_vars,
        "y_names": get_name(y_vars, var_names),
        "data": dumps(all_results_df.to_dict(orient="records"), indent=4 if INDENT_DATA else None),
        "dir_name": os.path.dirname(path),
        "file_path": ".".join(path.split(".")[:-1]),  # remove extension
        "file_name": ".".join(path.split("/")[-1].split(".")[:-1]),
    }

    # read template notebook
    with open("npf/types/notebook/template.ipynb") as f:
        nb = nbf.read(f, as_version=4)

    # replace variables in loaded template nb using jinja2
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


def get_name(var: str | list[str], var_names: dict[str, str]) -> str | list[str]:
    """Returns the name associated with a variable or a list of variables."""
    if isinstance(var, list):
        return [get_name(v, var_names) for v in var]
    return var_names[var] if var in var_names else var
