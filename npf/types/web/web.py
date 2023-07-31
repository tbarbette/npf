import uuid

from npf_web_extension import app

def prepare_web_export(datasets, all_results_df, path):

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

      for var, var_name in test.config["var_names"]:
        x_axis = var_name if len(parameters) > 0 and var == parameters[0] else parameters[0]
        y_axis = var_name if len(measurements) > 0 and var == measurements[0] else measurements[0]
      break

    # Preparing configuration data
    configurationData = {
        "id": str(uuid.uuid4()),
        "name": name,
        "parameters": parameters,
        "measurements": measurements,
        "data": all_results_df.to_csv(index=True, index_label="index", sep=",", header=True),
        "settings": {
          "x": {
            "title": x_axis,
            "parameter": parameters[0] if len(parameters) > 0 else "undefined",
            "scale": 1
          },
          "y": {
            "title": y_axis,
            "parameter": measurements[0] if len(measurements) > 0 else "undefined",
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

