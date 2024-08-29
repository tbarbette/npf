from npf.types.dataset import convert_to_xyeb
from npf.variable import is_numeric, get_numeric
import numpy as np

class Graph:
    """
    This is a structure holder for data to build a graph
    """
    def __init__(self, grapher:'Grapher'):
        self.grapher = grapher
        self.subtitle = None
        self.data_types = None

    def statics(self):
        return dict([(var,list(values)[0]) for var,values in self.vars_values.items() if len(values) == 1])

    def dyns(self):
        return [var for var,values in self.vars_values.items() if len(values) > 1]

    #Convert the series into the XYEB format (see types.dataset)
    def dataset(self, kind=None):
        if not self.data_types:

            self.data_types = convert_to_xyeb(
                datasets = self.series,
                run_list = self.vars_all,
                key = self.key,
                max_series=self.grapher.config('graph_max_series'),
                do_x_sort=self.do_sort,
                series_sort=self.grapher.config('graph_series_sort'),
                options=self.grapher.options,
                statics=self.statics(),
                y_group=self.grapher.configdict('graph_y_group'),
                color=[get_numeric(v) for v in self.grapher.configlist('graph_color')],
                kind=kind
                )

        return self.data_types

    # Divide all series by the first one, making a percentage of difference
    @staticmethod
    def series_prop(series, prop, exclusions = []):
            if len(series) == 1:
                raise Exception("Cannot make proportional series with only one serie !")
            newseries = []
            if not is_numeric(prop):
                prop=1
            if len(series[0]) < 3:
                raise Exception("Malformed serie !")
            base_results=series[0][2]
            for i, (script, build, all_results) in enumerate(series[1:]):
                new_results={}
                for run,run_results in all_results.items():
                    if not run in base_results:
                        print(run,"FIXME is not in base")
                        continue

                    for result_type, results in run_results.items():
                        if not result_type in base_results[run]:
                            run_results[result_type] = None
                            print(result_type, "not in base for %s" % run)
                            continue
                        base = base_results[run][result_type]
                        if len(base) > len(results):
                            base = base[:len(results)]
                        elif len(results) > len(base):
                            results = results[:len(base)]
                        base = np.array(base)
                        results = np.array(results)
                        if result_type not in exclusions:
                            f = np.nonzero(base)
                            results = (results[f] / base[f] * float(abs(prop)) + (prop if prop < 0 else 0))
                        run_results[result_type] = results
                    new_results[run] = run_results
                build._pretty_name = build._pretty_name + " / " + series[0][1]._pretty_name
                newseries.append((script, build, new_results))
            return newseries
