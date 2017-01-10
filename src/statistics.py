from typing import List, Dict

import pydotplus as pydotplus
from sklearn import tree
import numpy as np

from src.build import Build
from src.testie import Run, Testie, Dataset


class Statistics:
    @staticmethod
    def run(build:Build, all_results:Dataset, testie:Testie,max_depth=3):
        X,y = Statistics.buildDataset(all_results,testie)
        clf = tree.DecisionTreeRegressor(max_depth=max_depth)
        clf = clf.fit(X,y)

        dot_data = tree.export_graphviz(clf, out_file=None, filled=True,rounded=True,special_characters=True,
                                        feature_names=testie.variables.dtype()['names'])
        graph = pydotplus.graph_from_dot_data(dot_data)
        f = build.result_path(testie,'pdf',suffix='_clf')
        graph.write_pdf(f)
        print("Decision tree visualization written to %s" % f)
        print("Feature importances :")
        for key,f in zip(testie.variables.dtype()['names'],clf.feature_importances_):
            print("%s : %0.2f" % (key,f))


    @classmethod
    def buildDataset(cls, all_results:Dataset, testie:Testie):
        dtype = testie.variables.dtype()
        y=[]
        dataset = []
        for i,(run,results) in enumerate(all_results.items()):
            vars = np.array(list(run.variables.values()))
            dataset.append(vars)
            y.append(np.mean(results))
        return np.array(dataset,dtype=dtype),np.array(y,dtype=[('result',float)])