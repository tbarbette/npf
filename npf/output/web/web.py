import uuid

from npf_web_extension import app

def prepare_web_export(datasets, all_results_df, path):
    # TODO: (error) this code loops but doesn't save the different datasets.
    # Getting parameters and measurements
    name = "undefined"
    parameters = []
    measurements = []
    x_axis = ""
    y_axis = ""
    for test, _, runs in datasets:
      name = test.get_title()
      for run, results in runs.items():
        measurements = list(results.keys())
        parameters = list(run.variables.keys())
        break

      # Titles of the axes: the names of the first variable and result (var_names), if any
      var_names = dict(test.config["var_names"])
      if parameters:
        x_axis = var_names.get(parameters[0], parameters[0])
      if measurements:
        y_axis = var_names.get("result-" + measurements[0], var_names.get(measurements[0], measurements[0]))
      break

    # Preparing configuration data
    configurationData = {
        "id": str(uuid.uuid4()),
        "name": name,
        "parameters": parameters,
        "measurements": ["y_" + m for m in measurements],
        "data": all_results_df.to_csv(index=True, index_label="index", sep=",", header=True),
        "settings": {
          "x": {
            "title": x_axis,
            "parameter": parameters[0] if len(parameters) > 0 else "undefined",
            "scale": 1
          },
          "y": {
            "title": y_axis,
            "parameter": "y_" + measurements[0] if len(measurements) > 0 else "undefined",
            "scale": 1
          },
          "split": {
            "x": {
                "enable": False,
                "parameter": "",
                "format": "",
                "placement": "before"
            },
            "y": {
                "enable": False,
                "parameter": "",
                "format": "",
                "placement": "before"
            },
          },
          "type": 0,
          "error_bars": False
        }
    }

    # Exporting
    app.export(configurationData, path)

