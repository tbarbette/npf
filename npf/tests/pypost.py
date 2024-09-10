


from typing import List

from npf.types.series import Series


def execute_pypost(series: List[Series]):
        # Get all scripts, and execute pypost
        for i, (test, build, all_results) in enumerate(series):

            if hasattr(test, 'pypost'):
                def common_divide(a,b):
                    m = min(len(a),len(b))
                    return np.array(a)[:m] / np.array(b)[:m]
                def results_divide(res,a,b):
                    for RUN, RESULTS in all_results.items():
                        if a in RESULTS and b in RESULTS:
                            all_results[RUN][res] = common_divide(RESULTS[a], RESULTS[b])
                vs = {'ALL_RESULTS': all_results, 'common_divide': common_divide, 'results_divide': results_divide}
                try:
                    exec(test.pypost.content, vs)
                except Exception as e:
                    print("ERROR WHILE EXECUTING PYPOST SCRIPT:")
                    print(e)
