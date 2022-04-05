
class NIC:
    TYPES = "driver|ip|ip6|mac|raw_mac|ifname|pci|mask"

    def __init__(self, pci, mac, ip, ip6, ifname, mask='255.255.255.0'):
        self.pci = pci
        self.mac = mac
        self.ip = ip
        self.ip6 = ip6
        self.ifname = ifname
        self.mask = mask

    def __getitem__(self, item):
        item = str(item).lower()
        if item == 'pci':
            return self.pci
        elif item == 'mac':
            return self.mac
        elif item == 'raw_mac':
            return self.mac.replace(':', '')
        elif item == 'ip':
            return self.ip
        elif item == 'ip6':
            return self.ip6
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
        elif item == 'ip6':
            self.ip6 = val
        elif item == 'ifname':
            self.ifname = val
        elif item == 'mask':
            self.mask = val
        elif item == 'driver':
            self.driver = val
        else:
            raise Exception("Unknown type %s" % item)



