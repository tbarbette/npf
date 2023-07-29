import uuid

from npf_web_extension import app

def prepare_web_export(datasets, all_results_df, path):

    # Getting parameters and measurements
    name = "undefined"
    parameters = []
    measurements = []
    for test, _, runs in datasets:
      name = test.get_title()
      for run, results in runs.items():
        measurements = list(results.keys())
        parameters = list(run.variables.keys())
        break
      break

    # Preparing configuration data
    configurationData = {
        "id": str(uuid.uuid4()),
        "name": name,
        "parameters": parameters,
        "measurements": measurements,
        "data": all_results_df.to_csv(index=True, index_label="index", sep=",", header=True)
    }

    # Exporting
    app.export(configurationData, path)

