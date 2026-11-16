"""The options of the %config section: each one can be set from a test script, and each alias leads to one"""
import argparse
import os
import shutil
import tempfile
import unittest

import npf.globals
from npf.tests.sections import SectionConfig
from npf.tests.test import Test


class TestConfigOptions(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.options = argparse.Namespace(show_files=False, quiet=True, debug=False, no_build_deps=[],
                                          force_build_deps=[], ignore_deps=[], keep_env=[], rand_env=0,
                                          allow_mp=False, preserve_temp=False, design="full",
                                          experiment_folder=self.test_dir, search_path=[], cwd=os.getcwd())
        npf.globals.options = self.options

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def parse(self, config):
        path = os.path.join(self.test_dir, 'test.npf')
        with open(path, 'w') as f:
            f.write("%config\n" + config + "\n\n%script\necho RESULT 1\n")
        return Test(path, self.options)

    def test_aliases_lead_to_options(self):
        config = SectionConfig()
        for alias, option in config.aliases.items():
            self.assertIn(option, config.vlist, "alias %s" % alias)

    def test_options_read_by_the_graphs(self):
        # These had no default, so a test script could not set them ("Unknown variable")
        test = self.parse("graph_only={THROUGHPUT}\ngraph_bar_inter=0.2\ngraph_bar_hatch=1\nlegend_mode=expand\n"
                          "graph_labels={A,B}\ngraph_x_label=0\ngraph_filter={LATENCY:x<10}\n"
                          "graph_line_params={linewidth:2}\ngraph_map_inline={a:b}\nsubplot_legend_loc={best}")
        self.assertEqual(test.config["graph_only"], "THROUGHPUT")
        self.assertEqual(test.config["graph_bar_inter"], 0.2)
        self.assertEqual(test.config["legend_mode"], "expand")
        self.assertEqual(test.config.get_list("graph_labels"), ["A", "B"])

    def test_result_as_variables(self):
        # The name graph.rst documents: the graphs read graph_result_as_variable
        test = self.parse("result_as_variables={COUNT-Q(.*):QUEUE}")
        self.assertEqual(dict(test.config.get_dict("graph_result_as_variable")), {"COUNT-Q(.*)": "QUEUE"})


if __name__ == '__main__':
    unittest.main()
