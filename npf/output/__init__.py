from typing import Dict, List, Tuple
from npf.models.series import Series

def generate_outputs(filename: str, series: Series , time_series:Series, options) -> Tuple['Dataset',Dict]:
    """
    The function merge different series together, finding common variables

    :param filename: The name of the file to which the output will be exported
    :param series: The "series" parameter refers to the data series that you want to export. It could be
    a list, array, or any other data structure that contains the data you want to export
    :param kind_series: The `kind_series` parameter is used to specify the type of series to be
    exported. It can take values such as "line", "bar", "scatter", etc., depending on the type of chart
    or graph you want to export
    :param options: The "options" parameter is a dictionary that contains various options for exporting
    the output. These options can include things like the file format, the delimiter to use, whether or
    not to include headers, etc
    """
    import npf
    from npf.output.statistics import Statistics
    from npf.tests import pypost
    from npf.tests.regression import Grapher, OrderedDict, npf

    if series is None:
        return

    #Group repo if asked to do so with --group-repo. If the user called NPF with multiple series like 'npf.py repo1 repo2 --group-repo ...' it will move repo1 and repo2 as a variable instead of keeping it as different series.
    if options.group_repo:
        repo_series=OrderedDict()
        for test, build, dataset in series:
            repo_series.setdefault(build.repo.reponame,(test,build,OrderedDict()))
            for run, run_results in dataset.items():
                run.write_variables()['SERIE'] = build.pretty_name()
                repo_series[build.repo.reponame][2][run] = run_results
        series = []
        for reponame, (test, build, dataset) in repo_series.items():
            build._pretty_name = reponame
            build.version = reponame
            series.append((test, build, dataset))

    # Merge series with common name
    # If user launched with 'npf.py local+VAR=1:Test local+VAR=2:Test', despite the two series having the same name they won't be merged by default. This options will merge resutls as if they were part of the same serie.
    if options.group_series:
        merged_series = OrderedDict()
        for test, build, dataset in series:
            #Group series by serie name
            merged_series.setdefault(build.pretty_name(), []).append((test, build, dataset))

        series = []
        for sname, slist in merged_series.items():
                if len(slist) == 1:
                    series.append(slist[0])
                else:
                    all_r = {}
                    for results in [l[2] for l in slist]:
                        all_r.update(results)
                    series.append((slist[0][0], slist[0][1], all_r))

    # We must find the common variables to all series, and change dataset to reflect only those
    all_variables = []
    for test, build, dataset in series:
        v_list = set()
        for run, results in dataset.items():
            v_list.update(run.read_variables().keys())
        all_variables.append(v_list)

        if options.statistics:
            Statistics.run(build,
                           dataset,
                           test,
                           max_depth=options.statistics_maxdepth,
                           filename=options.statistics_filename or npf.build_output_filename([build.repo for t,build,d in series]))

    common_variables = set.intersection(*map(set, all_variables))

    #Remove variables that are totally defined by the series, that is
    # variables that only have one value inside each serie
    # but have different values accross series
    useful_variables=[]
    for variable in common_variables:
        all_values = set()
        all_alone=True
        for test, build, dataset in series:
            serie_values = set()
            for run, result_types in dataset.items():
                if variable in run.read_variables():
                    val = run.read_variables()[variable]
                    serie_values.add(val)
            if len(serie_values) > 1:
                all_alone = False
                break
        if not all_alone:
            useful_variables.append(variable)

    if options.group_repo:
        useful_variables.append('SERIE')

    for v in series[0][0].config.get_list("graph_hide_variables"):
        if v in useful_variables:
            useful_variables.remove(v)

    #Keep only the variables in Run that are usefull as defined above
    if options.remove_parameters:
        for i, (test, build, dataset) in enumerate(series):
            new_dataset: Dict[Run,List] = OrderedDict()
            for run, results in dataset.items():
                m = run.intersect(useful_variables)
                if m in new_dataset:
                    print(f"WARNING: You are comparing series with different variables. Results of series '{build.pretty_name()}' are merged.")
                    for output, data in results.items():
                        if output in new_dataset[m]:
                            new_dataset[m][output].extend(data)
                        else:
                            new_dataset[m][output] = data
                else:
                    new_dataset[m] = results
            series[i] = (test, build, new_dataset)

    #Keep only the variables in Time Run that are usefull as defined above
    if options.do_time:
        n_time_series = OrderedDict()
        for test, build, time_dataset in time_series:
            for kind, dataset in time_dataset.items():
              new_dataset = OrderedDict()
              n_time_series.setdefault(kind,[])
              for run, results in dataset.items():
                new_dataset[run.intersect(useful_variables + [kind])] = results
              if new_dataset:
                n_time_series[kind].append((test, build, new_dataset))

    grapher = Grapher()
    print("Generating graphs...")

    pypost.execute_pypost(series=series)

    g = grapher.graph(series=series,
                      filename=filename,
                      options=options,
                      title=options.graph_title)

    if options.do_time:
        for time_ns,series in n_time_series.items():
            if len(series):
                print(f"Generating graph for time serie '{time_ns}'...")
                g = grapher.graph(  series=series,
                                    filename=filename,
                                    fileprefix=time_ns,
                                    options=options,
                                    title=options.graph_title)
    return series, time_series