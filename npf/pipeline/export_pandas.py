import os

import pandas as pd

from npf.types.series import Series

def export_pandas(options, series:Series, fileprefix:str = None) -> None:
        # Add series to a pandas dataframe
        if options.pandas_filename is None:
                return

        #In pandas, we cant merge dataframe if two columns have the same name, which can happen
        # if some RESULT have the same name than the variables.
        # if that happens, we'll rename the result as y_XXX and add the name in overlapping
        all_X=pd.DataFrame() # Empty dataframe for X
        all_y=pd.DataFrame() # Empty dataframe for y
        for _, build, all_results in series:
                for i, x in enumerate(all_results):
                        try:

                                labels = [k[1] if type(k) is tuple else k for k,v in x.read_variables().items()]
                                x_vars = [[v[1] if type(v) is tuple else v for k,v in x.read_variables().items()]]
                                x_vars=pd.DataFrame(x_vars,index=[0],columns=labels)
                                x_vars=pd.concat([pd.DataFrame({'build' :build.pretty_name()},index=[0]), pd.DataFrame({'test_index' :i},index=[0]), x_vars],axis=1)
                                y_target=pd.DataFrame.from_dict(all_results[x],orient='index').transpose() #Use orient='index' to handle lists with different lengths

                                if len(y_target) == 0:
                                    continue

                                x_vars = pd.concat([x_vars]*len(y_target), ignore_index=True)
                                all_X = pd.concat([all_X,x_vars],ignore_index = True, axis=0)
                                y_target['run_index']=y_target.index
                                all_y = pd.concat([all_y,y_target],ignore_index = True, axis=0)


                        except Exception as e:
                                print(f"ERROR: When trying to export serie {build.pretty_name()}:")
                                raise(e)


        if dup_columns := set(all_X.columns).intersection(set(all_y.columns)):
                print("WARNING: The following outputs are also variable names. The columns for the output will be named with a y_ prefix.", dup_columns)
                all_y = all_y.rename(columns=dict([(c, f'y_{c}') for c in dup_columns]))


        try:
            all_results_df = pd.concat([all_X, all_y],axis=1)
        except Exception as e:
            print("ERROR: When trying to concatenate variables and features")
            print(all_X)
            print(all_y)
            raise(e)

            # Save the pandas dataframe into a csv
        pandas_df_name = (os.path.splitext(options.pandas_filename)[0] +
                          (f"-{fileprefix}" if fileprefix else "") + ".csv")
        # Create the destination folder if it doesn't exist
        df_path = os.path.dirname(pandas_df_name)
        if df_path and not os.path.exists(df_path):
            os.makedirs(df_path)

        all_results_df.to_csv(pandas_df_name, index=True, index_label="index", sep=",", header=True)
        print(f"Pandas dataframe written to {pandas_df_name}")