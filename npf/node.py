import os
import random

import re
import socket

from npf.executor.localexecutor import LocalExecutor
from npf.executor.sshexecutor import SSHExecutor
from npf.variable import Variable,get_bool
from npf.nic import NIC

class Node:
    _nodes = {}

    def __init__(self, name, executor):
        self.executor = executor
        self.name = name
        self.nics = []
        self.tags = []
        self.nfs = True
        self.addr = 'localhost'

        # Always fill 32 random nics address that will be overwriten by config eventually
        self._gen_random_nics()

        clusterFile = 'cluster/' + name + '.node'
        if (os.path.exists(clusterFile)):
            f = open(clusterFile, 'r')
            for i, line in enumerate(f):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = re.match(r'(?P<nic_idx>[0-9]+):(?P<type>' + NIC.TYPES + ')=(?P<val>[a-z0-9:.]+)', line,
                                 re.IGNORECASE)
                if match:
                    self.nics[int(match.group('nic_idx'))][match.group('type')] = match.group('val')
                    continue
                match = re.match(r'(?P<var>' + Variable.ALLOWED_NODE_VARS + ')=(?P<val>.*)', line,
                                 re.IGNORECASE)
                if match:
                    if match.group('var') == 'nfs':
                        self.nfs = get_bool(match.group('val'))
                    setattr(executor, match.group('var'), match.group('val'))
                    continue
                raise Exception("%s:%d : Unknown node config line %s" % (clusterFile, i, line))
        else:
            self._find_nics()

    def _find_nics(self):
        # TODO : find real nics
        pass

    def get_nic(self, nic_idx):
        return self.nics[nic_idx]

    @staticmethod
    def _addr_gen():
        mac = [0xAE, 0xAA, 0xAA,
               random.randint(0x01, 0x7f),
               random.randint(0x01, 0xff),
               random.randint(0x01, 0xfe)]
        macaddr = ':'.join(map(lambda x: "%02x" % x, mac))
        ip = [10, mac[3], mac[4], mac[5]]
        ipaddr = '.'.join(map(lambda x: "%d" % x, ip))
        return macaddr, ipaddr

    def _gen_random_nics(self):
        for i in range(32):
            mac, ip = self._addr_gen()
            nic = NIC(i, mac, ip, "eth%d" % i)
            self.nics.append(nic)

    @classmethod
    def makeLocal(cls, options):
        node = cls._nodes.get('localhost', None)
        if node is None:
            node = Node('localhost', LocalExecutor())
            cls._nodes['localhost'] = node
        node.ip = '127.0.0.1'
        return node

    @classmethod
    def makeSSH(cls, user, addr, path, options):
        if path is None:
            path = os.getcwd()
        node = cls._nodes.get(addr, None)
        if node is not None:
            return node
        sshex = SSHExecutor(user, addr, path)
        node = Node(addr, sshex)
        cls._nodes[addr] = node
        node.ip = socket.gethostbyname(node.executor.addr)
        if options.do_test and options.do_conntest:
            print("Testing connection to %s..." % node.executor.addr)
            pid, out, err, ret = sshex.exec(cmd="echo \"test\"")
            out = out.strip()
            if ret != 0 or out != "test":
                raise Exception("Could not communicate with node %s, got %s" %  (sshex.addr, out))
        return node
