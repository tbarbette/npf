import unittest
import argparse
from npf.cluster.node import Node, LocalExecutor
from npf import cmdline
import npf.globals
import npf.parsing

class TestCluster(unittest.TestCase):
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

    def test_node(self):
        args = self.get_args()
        args.do_test = False
        n1 = Node.makeSSH(addr="cluster01.sample.node", user=None, path=None)
        n2 = Node.makeSSH(addr="cluster01.sample", user=None, path=None)

        self.assertEqual(n1.executor.addr, "cluster01.example.com")
        self.assertEqual(n2.executor.addr, "cluster01.example.com")
        self.assertEqual(n1.executor.user, "user01")
        self.assertEqual(n2.executor.user, "user01")

    def test_local_executor(self):
        _ = self.get_args()
        l = LocalExecutor()
        pid, stdout, stderr, ret = l.exec("echo TEST")
        self.assertTrue(pid > 0)
        self.assertEqual(stdout, "TEST\n")
        self.assertEqual(stderr, "")
        self.assertEqual(ret, 0)

        pid, stdout, stderr, ret = l.exec("echo -n TEST")
        self.assertTrue(pid > 0)
        self.assertEqual(stdout, "TEST")
        self.assertEqual(stderr, "")
        self.assertEqual(ret, 0)

        pid, stdout, stderr, ret = l.exec("echo -n TEST 1>&2")
        self.assertTrue(pid > 0)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "TEST")
        self.assertEqual(ret, 0)

        pid, stdout, stderr, ret = l.exec("exit 1")
        self.assertTrue(pid > 0)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        self.assertEqual(ret, 1)


class TestRoleNotInCluster(unittest.TestCase):
    """A role missing from --cluster runs on localhost, with a warning when --cluster maps other roles"""

    def setUp(self):
        import npf.cluster.factory as factory
        self.factory = factory
        self.saved = dict(npf.globals.roles)
        npf.globals.roles.clear()
        npf.globals.roles['default'] = ['local']
        factory._warned_roles.clear()

    def tearDown(self):
        npf.globals.roles.clear()
        npf.globals.roles.update(self.saved)
        self.factory._warned_roles.clear()

    def lookup(self, role, **kwargs):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            nodes = self.factory.nodes_for_role(role, **kwargs)
        return nodes, out.getvalue()

    def test_silent_without_cluster(self):
        self.assertEqual(self.lookup('client'), (['local'], ''))

    def test_warns_once(self):
        npf.globals.roles['client'] = ['jaskier']
        nodes, out = self.lookup('sever')
        self.assertEqual(nodes, ['local'])
        self.assertIn("role sever is not in the cluster, which maps client", out)
        self.assertIn("sever=localhost", out)
        self.assertEqual(self.lookup('sever'), (['local'], ''))

    def test_mapped_roles_are_silent(self):
        npf.globals.roles['dut'] = ['dormeur']
        self.assertEqual(self.lookup('dut'), (['dormeur'], ''))
        self.assertEqual(self.lookup('server', default_role_map={'server': 'dut'}), (['dormeur'], ''))
        self.assertEqual(self.lookup(''), (['local'], ''))

    def test_default_role_map_to_a_missing_role(self):
        npf.globals.roles['client'] = ['jaskier']
        nodes, out = self.lookup('server', default_role_map={'server': 'dut'})
        self.assertEqual(nodes, ['local'])
        self.assertIn("role server (dut) is not in the cluster", out)
