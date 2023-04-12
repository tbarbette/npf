
import numpy as np
import pandas as pd
from functools import reduce

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
      second_variable_name, second_variable = list(run.variables.items())[1] if len(run.variables.items()) > 1 else ("","")

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
      print(f"Value added: {label}:{value}")

      # Retrieving run with current parameters
      iterator = filter(lambda x: x.parameters == parameters, experiment.runs)
      try:
        r = next(iterator)
        print("Iterator found!")
      except:
        print("Iterator created!")
        # Creating run
        r = Run()
        r.parameters = parameters

        # Storing run
        experiment.runs.append(r)

      # Storing result
      r.results.append(result)
      print(r.parameters)

      # series = output[test_name].setdefault(str(second_variable), {})
      # series[first_variable] = np.array(list(results.values())[0]).mean()
      print(first_variable, second_variable) # Debug

  # print(configuration.to_json()) # Debug
  
  return configuration


def datasets_to_dataframe(datasets):

  # Runs intermediary data structure
  configuration = Configuration()

  columns = []

  # Iterating through results
  for _, _, runs in datasets:
    for run, results in runs.items():
      for experiment, result in results.items():
        # Getting experiment data
        for variable_name, variable_value in run.variables.items():
          # Storing variable as a column in the dataframe
          if variable_name not in columns:
            columns.append(variable_name)
        # print(run.variables, experiment, result)
  
  # Adding extra columns
  columns.append('experiment')
  columns.append('results')

  # Creating dataframe
  df = pd.DataFrame(columns = columns)

  # Iterating again, this time to add data into the df
  for _, _, runs in datasets:
    for run, results in runs.items():
      for experiment, result in results.items():
        frame_data = {}

        # Adding each variable
        for i, value in enumerate(run.variables.values()):
          frame_data[columns[i]] = str(value)

        frame_data['experiment'] = experiment # Adding experiment name
        frame_data['results'] = [result] # Adding results

        # Adding to dataframe
        frame = pd.DataFrame(frame_data)
        df = pd.concat([df, frame])

  # Debug
  print(df)

  return df



def prepare_web_export(datasets):
  # Getting configuration from datasets
  #configuration = datasets_to_configuration(datasets)
  #print(configuration.to_json()) # Debug

  df = datasets_to_dataframe(datasets)
  columns = df.columns
  main_variable = columns[0] # Take into account the real variable!
  columns_to_group_by = list(np.concatenate(
    [
      ["experiment"], 
      list(filter(lambda x: x not in [main_variable, "experiment", "results"],columns))
    ],
    axis=None
  ))

  # Grouping dataframe by variables
  # This will ideally be done by npf-web-extension
  df_grouped_by_variables = df.groupby(columns_to_group_by)['results'].apply(list).to_dict()
  print(df_grouped_by_variables)

  # Converting each group into an experiment data dict
  df_grouped_as_experiment_dict = [
    {
      "name": k[0] if type(k) is tuple else k, 
      "runs": 
        [{ 
          "parameters": k[1:] if type(k) is tuple else "none", 
          "results": dict([(i, np.mean(v)) for i, v in enumerate(v) ]) # TODO instead of enumerate, put the real value of DF
        }]
      } 
    for k, v in df_grouped_by_variables.items()
  ]
  print(df_grouped_as_experiment_dict)

  # Merging all experiment data 
  experiments = []
  for data in df_grouped_as_experiment_dict:

    current_experiment_configuration = None
    for experiment_configuration in experiments:
      # If there is already an experiment configuration within the experiments structure
      if experiment_configuration["name"] == data["name"]:
        current_experiment_configuration = experiment_configuration
        break
    
    # No configuration so far so we create a new one
    if current_experiment_configuration == None:
      current_experiment_configuration = dict.copy(data)
      experiments.append(current_experiment_configuration)
      continue
      
    # Merging runs data
    current_experiment_configuration["runs"] = list(np.concatenate([ 
      current_experiment_configuration["runs"], data["runs"]
    ]))
      
  configuration = { "experiments": experiments }
  print(configuration) # Debug

  # Exporting app
  app.export(configuration, "./tmp")
  # print(f"file:///C:/ucl/memoire/npf/tmp/index.html")
  pass