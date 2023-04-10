
import numpy as np

from npf.types.web.configuration import Configuration, Experiment, Result, Run
from npf_web_extension import app

def datasets_to_configuration(datasets):

  # Configuration
  configuration = Configuration()

  # Iterating through all tests in datasets
  for testie, build, results in datasets:

    # Extracting data from test
    test_name = testie.get_name()

    # Preparing experiment
    experiment = Experiment()
    experiment.name = test_name

    # Storing experiment
    configuration.experiments.append(experiment)
    
    print(test_name) # Debug

    for run, result in results.items():

      # TODO clean this
      first_variable_name, first_variable = list(run.variables.items())[0]
      second_variable_name, second_variable = list(run.variables.items())[1]

      # Getting parameters
      parameters = str(second_variable)

      # Getting label
      label = first_variable

      # Getting value
      value = np.array(list(result.values())[0]).mean()

      # Preparing result
      result = Result()
      result.label = label
      result.value = value

      # Retrieving run with current parameters
      iterator = filter(lambda x: x.parameters == parameters, experiment.runs)
      try:
        r = next(iterator)
      except:
        # Creating run
        r = Run()
        r.parameters = parameters

        # Storing run
        experiment.runs.append(r)

      # Storing result
      r.results.append(result)

      # series = output[test_name].setdefault(str(second_variable), {})
      # series[first_variable] = np.array(list(results.values())[0]).mean()
      print(first_variable, second_variable) # Debug

  # print(configuration.to_json()) # Debug
  
  return configuration



def prepare_web_export(datasets):
  # Getting configuration from datasets
  configuration = datasets_to_configuration(datasets)
  print(configuration.to_json()) # Debug

  # Exporting app
  app.export(configuration.to_json(), "./tmp")