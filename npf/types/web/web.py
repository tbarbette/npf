
import json
from zipfile import ZipFile
import numpy as np
from ordered_set import OrderedSet
import requests

from npf.types.web.configuration import Configuration, Experiment, Result, Run


def download_latest_release():
  url = 'https://github.com/dpcodebiz/npf-web-extension/releases/download/v0.1.0/release-0.1.0.zip'
  r = requests.get(url, allow_redirects=True)

  open('./tmp/release-0.1.0.zip', 'wb').write(r.content)


def export_app():

  with ZipFile('./tmp/release-0.1.0.zip') as myzip:
    myzip.extractall('./tmp/web/')


def hydrate_app(json_configuration):

  with open('./tmp/web/build/index.html', 'r', encoding='utf-8') as file:
    data = file.readlines()
  
  start_line = -1
  end_line = -1

  for index, line in enumerate(data):

    print(index, line.find("<!-- NPF_CONFIG_INSERTION_STARTT -->"), line)

    if start_line == -1:
      start_line = index if line.find("<!-- NPF_CONFIG_INSERTION_STARTT -->") != -1 else -1
    
    if end_line == -1:
      end_line = index if line.find("<!-- NPF_CONFIG_INSERTION_END -->") != -1 else -1

    if start_line != -1 and end_line != -1:
      break
  
  print(start_line, end_line)
  
  if start_line != -1 and end_line != -1:
    new_data = [x for i, x in enumerate(data) if i <= start_line or i >= end_line]
    new_data.insert(end_line-(len(data)-len(new_data)), f'\t<script type="text/javascript">setTimeout(() => window.updateConfiguration({json.dumps(json_configuration)}), 2500)</script>\n')
  
    with open('./tmp/web/build/index.html', 'w', encoding='utf-8') as file:
      file.writelines(new_data)

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

  output = {}

  # print(datasets)

  # Getting configuration from datasets
  configuration = datasets_to_configuration(datasets)
  print(configuration.to_json())

  # TODO find a solution to not download this in real time
  # download_latest_release()

  # Exporting app
  # export_app()

  # Hydrating app
  hydrate_app(configuration.to_json())

  with open("tmp/test.json", "w") as f:
    json.dump(configuration.to_json(), f)