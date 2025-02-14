

import numpy as np
from npf.tests.build import Build
from npf.models.units import get_numeric
from npf.models.dataset import XYEB


def do_heatmap(graph, axis, key, result_type, data : XYEB, xdata : XYEB, vars_values: dict, shift=0, idx=0, sparse=False,show_values=False):
        isLog = graph.format_figure(axis, result_type, shift, key=key)
        nseries = 0
        yvals = []
        for x,y,e,build in data:
            nseries = max(len(y), nseries)
            y = get_numeric(build._pretty_name)
            yvals.append(y)


        if not key in vars_values:
            print("WARNING: Heatmap with an axis of size 1")
            xvals = [1]
        else:
            xvals = list(vars_values[key])

        if sparse:
            xmin=min(xvals)
            xmax=max(xvals)
            ymin=min(yvals)
            ymax=max(yvals)
        else:
            xmin=0
            xmax=len(xvals) - 1
            ymin=0
            ymax=len(yvals) - 1

        data = [data[i] for i in np.argsort(yvals)]
        yvals = [yvals[i] for i in np.argsort(yvals)]


        matrix = np.empty(tuple((ymax-ymin + 1,xmax-xmin + 1)))
        matrix[:] = np.nan

        if len(data) <= 1 or nseries <= 1:
            print("WARNING: Heatmap needs two dynamic variables. The map will have a weird ratio")


        for i, (x, ys, e, build) in enumerate(data): #X index
            assert(isinstance(build,Build))
            for yi in range(nseries): #index in the array of Y, so it is the index of X
                #dest = np.argsort(yvals)[yi]
                val = ys[yi]
                if sparse:
                    matrix[ymax - yvals[i],xvals[yi] - xmin] = val
                else:
                    matrix[ymax - i,yi] = val

        axis.yname = graph.glob_legend_title

        pos = axis.imshow(matrix)
        axis.figure.colorbar(pos, ax=axis)

        if show_values:
                mean = np.mean(matrix)
                for i in range(len(data)):
                        for j in range(nseries):
                                v = matrix[i, j]
                                text = axis.text(
                                    j,
                                    i,
                                    f'%0.{str(show_values - 1)}f' %v,
                                    ha="center",
                                    va="center",
                                    color="w" if v< mean else "black",
                                )

        if sparse:
            prop = xmax-xmin / ymax-ymin
            if prop < 0:
                ny = min(len(yvals),9)
                nx = max(2,int(ny*prop))
            else:
                nx = min(len(xvals),9)
                ny = max(2,int(nx/prop))

            axis.set_yticks(np.linspace(0,ymax-ymin,num=ny))
            axis.set_yticklabels(["%d" % f for f in reversed(np.linspace(ymin,ymax,num=ny))])
            axis.set_xticks(np.linspace(0,xmax-xmin,num=nx))
            axis.set_xticklabels(["%d" % f for f in np.linspace(xmin,xmax,num=nx)])
        else:
            axis.set_xticks(range(xmax+1))
            axis.set_xticklabels(sorted(xvals))
            axis.set_yticks(range(ymax+1))
            axis.set_yticklabels(reversed(yvals))

        return True, nseries
