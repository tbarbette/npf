import unittest
from unittest import mock

import numpy as np


class Build:
    _color = "red"

    def pretty_name(self):
        return "A"


class TestCDF(unittest.TestCase):
    def draw(self, data):
        from npf.output.grapher import Grapher
        g = Grapher()
        g.graphlines = []
        g.glob_legend_title = None
        g.var_name = lambda k, **kwargs: k
        axis = mock.MagicMock()
        axis.yname = "N"
        with mock.patch.object(Grapher, "format_figure", return_value=False):
            g.do_cdf(axis, "X", "N", data, None)
        return g, axis.plot.call_args_list

    def test_steps(self):
        """The CDF of each value of X goes up by 1/N at each result, from 0 to 100%"""
        g, plots = self.draw([(["1", "2"], [0, 0], [(0, 0, [3, 1, 2]), (0, 0, [5, np.nan, 4])], Build())])
        self.assertEqual(len(plots), 2)
        x, y = plots[0].args
        self.assertEqual(list(x), [1, 1, 2, 3])
        np.testing.assert_allclose(y, [0, 100 / 3, 200 / 3, 100])
        x, y = plots[1].args
        self.assertEqual(list(x), [4, 4, 5])  # NaN results are left out
        np.testing.assert_allclose(y, [0, 50, 100])
        self.assertEqual(plots[0].kwargs["drawstyle"], "steps-post")

    def test_colors(self):
        """With one series, each value of X has its color and the legend is titled X. With more, each series has its
        color and each value of X its line style."""
        g, plots = self.draw([(["1", "2"], [0, 0], [(0, 0, [1]), (0, 0, [2])], Build())])
        self.assertNotEqual(plots[0].kwargs["color"], plots[1].kwargs["color"])
        self.assertEqual([p.kwargs["label"] for p in plots], ["1", "2"])
        self.assertEqual(g.glob_legend_title, "X")

        b = Build()
        b._color = "blue"
        g, plots = self.draw([(["1", "2"], [0, 0], [(0, 0, [1]), (0, 0, [2])], Build()),
                              (["1", "2"], [0, 0], [(0, 0, [1]), (0, 0, [2])], b)])
        self.assertEqual([p.kwargs["color"] for p in plots], ["red", "red", "blue", "blue"])
        self.assertNotEqual(plots[0].kwargs["linestyle"], plots[1].kwargs["linestyle"])
        self.assertEqual(plots[0].kwargs["label"], "A, 1")
