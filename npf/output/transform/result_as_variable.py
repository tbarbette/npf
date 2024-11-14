from collections import OrderedDict
from ordered_set import OrderedSet


from npf.models.units import numericable
from npf.models.units import get_numeric


def result_as_variable(series, result_types, var_name, vars_values):
    if len(var_name.split('-')) > 1:
        result_name=var_name.split('-')[1]
        var_name=var_name.split('-')[0]
    else:
        result_name="result-" + var_name
    result_to_variable_map = []

    for result_type in result_types.split('+'):
        result_to_variable_map.append(result_type)

    exploded_vars_values = vars_values.copy()
    vvalues = OrderedSet()

    untouched_series = []
    exploded_series = []
    for i, (test, build, all_results) in enumerate(series):
        exploded_results = OrderedDict()
        untouched_results = OrderedDict()

        for run, run_results in all_results.items():
            new_run_results_exp = OrderedDict() #Results that matched, key is the matched value
            untouched_run_results = OrderedDict()

            for result_type, results in run_results.items():
                match = False
                for stripout in result_to_variable_map:
                    if m := re.match(stripout, result_type):
                        match = m.group(1) if len(m.groups()) > 0 else result_type
                        break
                if match:
                    new_run_results_exp[match] = results
                else:
                    untouched_run_results[result_type] = results

            if len(new_run_results_exp) > 0:
                if numericable(new_run_results_exp.keys()):
                    nn = {}
                    for k, v in  new_run_results_exp.items():
                        nn[get_numeric(k)] = v
                    new_run_results_exp = OrderedDict(sorted(nn.items()))

                u = self.scriptconfig("var_unit", var_name, default="")
                mult = u in ['percent', '%']
                if mult:
                    tot = 0
                    for result_type, results in new_run_results_exp.items():
                        tot += np.mean(results)
                for extracted_val, results in new_run_results_exp.items(): #result-type
                    variables = run.variables.copy()
                    variables[var_name] = extracted_val
                    vvalues.add(extracted_val)
                    #nr = new_run_results.copy()
                    nr = {}
                    #If unit is percent, we multiply the value per the result
                    if mult:
                        m = np.mean(results)
                        tot += m
                        for result_type in nr:
                            nr[result_type] = nr[result_type].copy() * m / 100
                    nr[result_name] = results
                    exploded_results[Run(variables)] = nr


            untouched_results[run] = untouched_run_results

        if exploded_results:
            exploded_series.append((test, build, exploded_results))

        if untouched_results:
            untouched_series.append((test, build, untouched_results))

    exploded_vars_values[var_name] = vvalues

    return exploded_series, exploded_vars_values
