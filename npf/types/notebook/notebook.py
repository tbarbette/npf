import nbformat as nbf
from json import dumps
import re

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
        "file_path": ".".join(path.split(".")[:-1]),  # remove extension
        "file_name": ".".join(path.split("/")[-1].split(".")[:-1]),
    }

    # read template notebook
    with open("npf/types/notebook/template.ipynb") as f:
        nb = nbf.read(f, as_version=4)

    # replace variables in loaded template nb
    for cell in nb.cells:
        # if cell.cell_type == "code": # SIMTODO: should we replace only in code cells?
        for name, value in variables.items():
            cell.source = cell.source.replace(
                "{{" + name + "}}", str(value))  # replaces {{name}} by value

        # Find all occurrences of {{var[index]}} in the cell source
        for name, index in re.findall(r'{{(\w+)\[(\d+)\]}}', cell.source):
            index = int(index)

            # Replace {{var[index]}} with the actual value from the variables dictionary
            if name in variables and index < len(variables[name]):
                cell.source = cell.source.replace(
                    '{{' + name + '[' + str(index) + ']}}', str(variables[name][index]))

    # write notebook to file
    with open(path, 'w') as f:
        nbf.write(nb, f)
        print("Notebook exported to", path)


def get_name(var: str | list[str], var_names: dict[str, str]) -> str | list[str]:
    """Returns the name associated with a variable or a list of variables."""
    if isinstance(var, list):
        return [get_name(v, var_names) for v in var]
    return var_names[var] if var in var_names else var
