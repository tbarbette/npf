
"""
The classes below are utility classes defined to ease the maintenance and extension
of the configuration that is sent to the npf-web-extension app
"""
class Configuration:

  # Data
  experiments = []
  
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
