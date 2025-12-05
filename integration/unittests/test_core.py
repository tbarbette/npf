import unittest
import argparse
import os
import tempfile
import shutil
import numpy as np
from npf.tests.test import Test
from npf.tests.build import Build
from npf.repo.repository import Repository
from npf.tests.test_driver import Comparator
from npf.output.grapher import Grapher
from npf.cluster.node import Node
import npf.globals
import npf.parsing
from npf import cmdline
from npf.repo import repository

class TestNPFTest(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, 'test.npf')
        with open(self.test_file, 'w') as f:
            f.write("""%info
Test Info

%config
n_runs=1

%variables
VAR=[1-2]
STAT=1

%script
echo "VAR=$VAR"
""")
        
        # Mock options
        self.options = argparse.Namespace()
        self.options.show_files = False
        self.options.quiet = True
        self.options.debug = False
        self.options.no_build_deps = []
        self.options.force_build_deps = []
        self.options.ignore_deps = []
        self.options.keep_env = []
        self.options.rand_env = 0
        self.options.allow_mp = False
        self.options.preserve_temp = False
        self.options.design = "full"
        self.options.experiment_folder = self.test_dir
        self.options.search_path = []
        self.options.cwd = os.getcwd()
        
        npf.globals.options = self.options

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_parse_test(self):
        test = Test(self.test_file, self.options)
        self.assertEqual(test.info.content.strip(), "Test Info")
        self.assertEqual(test.config["n_runs"], 1)
        self.assertTrue("VAR" in test.variables.dynamics())
        self.assertTrue("STAT" in test.variables.statics())
        
    def test_expand_folder(self):
        # Mock cluster factory to avoid needing real nodes
        import npf.cluster.factory
        from npf.cluster.node import Node
        # Mock local node
        local_node = npf.cluster.factory.create_local()
        
        tests = Test.expand_folder(self.test_dir, self.options)
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0].filename, 'test.npf')

class TestCore(unittest.TestCase):
    def get_args(self):
        parser = argparse.ArgumentParser(description='NPF Tester')
        cmdline.add_verbosity_options(parser)
        cmdline.add_building_options(parser)
        cmdline.add_graph_options(parser)
        cmdline.add_testing_options(parser)
        args = parser.parse_args(args = [])
        args.tags = {}
        npf.globals.set_args(args)
        npf.parsing.parse_nodes(args)
        return args

    def get_repo(self):
        args = self.get_args()
        r = Repository('click-2022', args)
        return r

    def test_paths(self):
        """
        This test verifies the path management.
        It creates local and SSH nodes, modifies their executor paths,
        and then checks if the constants are updated correctly for each node type.
        """

        args = self.get_args()
        args.do_test = False
        args.do_conntest = False
        args.experiment_folder = "test_root"


        local = Node.makeLocal(test_access=False)
        ssh = Node.makeSSH(addr="cluster01.sample", user=None, path=None)
        ssh2 = Node.makeSSH(addr="cluster01.sample", user=None, path=None)
        ssh.executor.path = npf.npf_root_path() + "/tmp/"
        ssh2.executor.path = npf.experiment_path() + os.sep

        #Test the constants are correct

        test = Test("examples/math.npf", options=args, tags=args.tags)
        repo = self.get_repo()
        build = Build(repo, "version")
        v={}
        test.update_constants(v, build, ssh.experiment_path() + "/test-1/", out_path=None)
        v2={}
        test.update_constants(v2, build, ssh2.experiment_path() + "/test-1/", out_path=None)
        vl={}
        test.update_constants(vl, build, local.experiment_path() + "/test-1/", out_path=None)
        for d in [vl,v,v2]:
            self.assertEqual(v['NPF_REPO'], 'Click_2022')
            self.assertEqual(v['NPF_ROOT_PATH'], '../..')
            self.assertEqual(v['NPF_SCRIPT_PATH'], '../../examples')
            self.assertEqual(v['NPF_RESULT_PATH'], '../../results/click-2022')

    def test_core(self):
        parser = argparse.ArgumentParser(description='NPF test')
        v = cmdline.add_verbosity_options(parser)
        b = cmdline.add_building_options(parser)
        t = cmdline.add_testing_options(parser, regression=False)
        a = cmdline.add_graph_options(parser)
        parser.add_argument('repo', metavar='repo name', type=str, nargs='?', help='name of the repo/group of builds', default=None)

        full_args = ["--test", "integration/sections.npf",'--force-retest']
        args = parser.parse_args(full_args)
        npf.parsing.initialize(args)
        npf.parsing.create_local()

        repo_list = [repository.Repository.get_instance("local", options=args)]

        comparator = Comparator(repo_list)

        series, time_series = comparator.run(test_name=args.test_files,
                                             tags=args.tags,
                                             options=args)
        self.assertEqual(len(series), 1)
        r = series[0][2]
        self.assertEqual(len(r.items()), 1)
        run,results = list(r.items())[0]
        self.assertEqual(run.variables["N"], 1)
        self.assertTrue(np.all(np.array(results["SCRIPT"]) == 42))
        self.assertTrue(np.all(np.array(results["CLEANUP"]) == 1))
        self.assertTrue(np.all(np.array(results["PY"]) == 1))


        filename = npf.build_output_filename(repo_list)
        grapher = Grapher()

        print("Generating graphs...")
        g = grapher.graph(series=series,
                          filename=filename,
                          options=args
                          )

    def test_test_main(self):
        t = Test("examples/iperf.npf", options = npf.globals.options)

    def test_import_mains(self):
        import npf
        import npf_regress
        import npf_watch
