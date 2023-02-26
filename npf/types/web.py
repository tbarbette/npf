
import json
import numpy as np
from ordered_set import OrderedSet


def prepare_web_export(datasets):

  output = {}

  # print(datasets)

  # Getting variable (default = first)
  variable = OrderedSet()
  for _, _, all_results in datasets:
    for run, results in all_results.items():
      print(run, results)
      first_variable_name = list(run.variables.keys())[0]
      first_variable = list(run.variables.values())[0]

  for testie, build, results in datasets:
    
    # Extracting data from test
    test_name = testie.get_name()
    output[test_name] = output[test_name] if test_name in output.keys() else {}

    for run, results in all_results.items():
      first_variable_name, first_variable = list(run.variables.items())[0]
      second_variable_name, second_variable = list(run.variables.items())[1]

      series = output[test_name].setdefault(str(second_variable), {})
      series[first_variable] = np.array(list(results.values())[0]).mean()

      print(first_variable, second_variable)


    # Preparing to store data
    # print(testie.get_name())

    # print(testie, build, results)

  # Debug output
  print(output)

  with open("tmp/test.json", "w") as f:
    json.dump(output, f)