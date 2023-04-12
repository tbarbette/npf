
"""
The classes below are utility classes defined to ease the maintenance and extension
of the configuration that is sent to the npf-web-extension app
"""
class Configuration:

  # Data
  experiments = []
  
  def get_experiment(self, experiment):
    for e in self.experiments:
      if e.name == experiment.name:
        return e
    return None

  def append_experiment_data(self, experiment):

    # Getting stored experiment
    stored_experiment = self.get_experiment(experiment)

    # Creating experiment if not already there
    if stored_experiment == None:
      self.experiments.append()



  def to_json(self):
    return {
      "experiments": [e.to_json() for e in self.experiments]
    }


class Experiment:
   
  # Data
  name = "undefined"
  runs = []

  def to_json(self):
    return {
      "name": self.name,
      "runs": [r.to_json() for r in self.runs]
    }


class Run:

  # Data
  parameters = "undefined"
  results = []

  def results_to_dict(self):
    results_dict = {}

    for result in self.results:
      results_dict[result.label] = result.value
    
    print(self.parameters, [e.value for e in self.results])
    
    return results_dict


  def to_json(self):
    return {
      "parameters": self.parameters,
      "results": self.results_to_dict()
    }


class Result:
  
  # Data
  label = "undefined"
  value = None

  def to_json(self):
    return { "label": self.label, "value": self.value }
