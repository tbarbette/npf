from typing import List
import pandas as pd

from npf.models.series import Series

def to_pandas(series: List[Series]):
    all_results_df = pd.DataFrame() # Empty dataframe
    for test, build, all_results in series:
        for i, (x,results) in enumerate(all_results.items()):
            if len(results) == 0:
                continue
            try:

                labels = [k[1] if type(k) is tuple else k for k,v in x.variables.items()]
                x_vars = [[(v[1] if type(v) is tuple else v) for k,v in x.variables.items()]]
                x_vars=pd.DataFrame(x_vars,index=[0],columns=labels)
                x_vars=pd.concat([pd.DataFrame({'build' :build.pretty_name()},index=[0]), pd.DataFrame({'test_index' :i},index=[0]), x_vars],axis=1)

                vals = all_results[x]
                if not vals:
                    continue
                x_data=pd.DataFrame.from_dict( {"y_"+k: v for k, v in vals.items()},orient='index').transpose() #Use orient='index' to handle lists with different lengths
                if len(x_data) == 0:
                    continue
                x_data['run_index']=x_data.index
                x_vars = pd.concat([x_vars]*len(x_data), ignore_index=True)
                x_df = pd.concat([x_vars, x_data],axis=1)
                all_results_df = pd.concat([all_results_df,x_df],ignore_index = True, axis=0)
            except Exception as e:
                print("ERROR: When trying to export serie %s:" % build.pretty_name())
    return all_results_df