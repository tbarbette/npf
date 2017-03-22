import os
import random

import re

from src.executor.localexecutor import LocalExecutor
from src.executor.sshexecutor import SSHExecutor


class NIC:
    TYPES = "ip|mac|ifname|pci|mask"

    def __init__(self, pci, mac, ip, ifname, mask='255.255.255.0'):
        self.pci = pci;
        self.mac = mac;
        self.ip = ip;
        self.ifname = ifname;
        self.mask = mask;

    def __getitem__(self, item):
        item = str(item).lower()
        if item == 'pci':
            return self.pci
        elif item == 'mac':
            return self.mac
        elif item == 'ip':
            return self.ip
        elif item == 'ifname':
            return self.ifname
        elif item == 'mask':
            return self.mask
        else:
            raise Exception("Unknown type %s" % item)

    def __setitem__(self, item, val):
        item = str(item).lower()
        if item == 'pci':
            self.pci = val
        elif item == 'mac':
            self.mac = val
        elif item == 'ip':
            self.ip = val
        elif item == 'ifname':
            self.ifname = val
        elif item == 'mask':
            self.mask = val
        else:
            raise Exception("Unknown type %s" % item)


class Node:
    VARS = 'path|user|addr'

    def __init__(self, name, executor):
        self.executor = executor
        self.name = name
        self.nics = []

        # Always fill 32 random nics address that will be overwriten by config eventually
        self._gen_random_nics()

        clusterFile = 'cluster/' + name + '.node'
        if (os.path.exists(clusterFile)):
            f = open(clusterFile, 'r')
            for i,line in enumerate(f):
                line=line.strip()
                if not line or line.startswith("#"):
                    continue;
                match = re.match(r'(?P<nic_idx>[0-9]+):(?P<type>' + NIC.TYPES + ')=(?P<val>[a-z0-9:.]+)', line,
                                 re.IGNORECASE)
                if match:
                    self.nics[int(match.group('nic_idx'))][match.group('type')] = match.group('val')
                    continue
                match = re.match(r'(?P<var>' + Node.VARS + ')=(?P<val>.*)', line,
                                 re.IGNORECASE)
                if match:
                    setattr(executor, match.group('var'), match.group('val'))
                    continue
                raise Exception("%s:%d : Unkown node config line %s" % (clusterFile,i,line))
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
    def makeLocal(cls):
        return Node('localhost', LocalExecutor())

    @classmethod
    def makeSSH(cls, user, addr, path):
        sshex = SSHExecutor(user, addr, path)
        node = Node(addr, sshex)
        print("Testing connection to %s..." % node.executor.addr)
        pid, out, err, ret = sshex.exec(cmd="echo \"test\"", terminated_event=None)
        out = out.strip()
        if ret != 0 or out != "test":
            raise Exception("Could not communicate with node %s, got %s", sshex.addr, out)
        return node
