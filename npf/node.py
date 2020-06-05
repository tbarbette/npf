import os
import random
import sys
import re
import socket
import time

from npf.executor.localexecutor import LocalExecutor
from npf.executor.sshexecutor import SSHExecutor
from npf.variable import Variable,get_bool
from npf.nic import NIC

class Node:
    _nodes = {}

    def __init__(self, name, executor, tags):
        self.executor = executor
        self.name = name
        self._nics = []
        self.tags = []
        self.nfs = True
        self.addr = 'localhost'
        self.port = 22
        self.arch = ''
        self.active_nics = range(32)
        self.multi = None
        self.mode = "bash"

        # Always fill 32 random nics address that will be overwriten by config eventually
        self._gen_random_nics()

        clusterFileName = 'cluster/' + name + '.node'
        for path in ['./', os.path.dirname(sys.argv[0])]:
          clusterFile = path + os.sep + clusterFileName
          if (os.path.exists(clusterFile)):
            f = open(clusterFile, 'r')
            for i, line in enumerate(f):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue
                match = re.match(r'((?P<tag>[a-zA-Z]+[a-zA-Z0-9]*):)?(?P<nic_idx>[0-9]+):(?P<type>' + NIC.TYPES + ')=(?P<val>[a-z0-9:_.]+)', line,
                                 re.IGNORECASE)
                if match:
                    if match.group('tag') and not match.group('tag') in tags:
                        continue
                    self._nics[int(match.group('nic_idx'))][match.group('type')] = match.group('val')
                    continue
                match = re.match(r'(?P<var>' + Variable.ALLOWED_NODE_VARS + ')=(?P<val>.*)', line,
                                 re.IGNORECASE)
                if match:
                    if match.group('var') == 'nfs':
                        self.nfs = get_bool(match.group('val'))
                    setattr(executor, match.group('var'), match.group('val'))
                    continue
                raise Exception("%s:%d : Unknown node config line %s" % (clusterFile, i, line))
            break
        else:
            self._find_nics()

    def _find_nics(self):
        # TODO : find real nics
        pass

    def get_nic(self, nic_idx):
        if nic_idx >= len(self.active_nics):
            raise Exception("ERROR: node %s has no nic number %d" % (self.name, nic_idx))

        return self._nics[self.active_nics[nic_idx]]

    def get_name(self):
        return self.name

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
            self._nics.append(nic)

    @classmethod
    def makeLocal(cls, options):
        node = cls._nodes.get('localhost', None)
        if node is None:
            node = Node('localhost', LocalExecutor(), options.tags)
            cls._nodes['localhost'] = node
        node.ip = '127.0.0.1'
        return node

    @classmethod
    def makeSSH(cls, user, addr, path, options, port=22):
        if path is None:
            path = os.getcwd()
        node = cls._nodes.get(addr, None)
        if node is not None:
            return node
        sshex = SSHExecutor(user, addr, path, port)
        node = Node(addr, sshex, options.tags)
        cls._nodes[addr] = node
        try:
            node.ip = socket.gethostbyname(node.executor.addr)
        except Exception as e:
            print("Could not resolve hostname '%s'" % node.executor.addr)
            raise(e)
        if options.do_test and options.do_conntest:
            print("Testing connection to %s..." % node.executor.addr)
            time.sleep(0.01)
            pid, out, err, ret = sshex.exec(cmd="if ! type 'unbuffer' ; then ( sudo apt install -y expect || sudo yum install -y expect ) && sudo echo 'test' ; else sudo echo 'test' ; fi", raw=True)
            out = out.strip()
            if ret != 0 or out.split("\n")[-1] != "test":
                raise Exception("Could not communicate with node %s, unbuffer (expect package) could not be installed, or passwordless sudo is not working, got %s" %  (sshex.addr, out))
        return node
