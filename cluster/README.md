Your own cluster can be defined using a simple node file describing different
 accessible computers intended to support a test script *role* such as *client* or *dut*.
All communication is done through SSH. You should have passwordless connection set up.

3 global parameters are supported :
  * `addr=full_address_of_node` //if unset, the node name is used 
  * `path=path/to/npf`
  * `user=user_for_ssh_connection`

Syncing NPF folder across your cluster improves performance as it avoids "rsyncing"
dependencies and scripts for each tests. One suggested option
is to use a NFS share, another possibility is to run sshfs on each node. If this is not possible for you, add the `nfs=0` global parameter in the repo file.

Test files can use special variables like `${role:0:ip}` to be replaced by the node's ip that run the given role. Allowed types such as ip are defined below.
Currently NPF does not support reading NIC's IP or MAC address neither ensuring a specific NIC order. By default, each node has 32 randomly generated NICs with reference 0 to 31, using ifname eth%d, random MAC address and a 10.0.0.0/8 random IP address.

Most testie reference the NIC 0 as the first dataplane NIC to run the test. Therefore you should set your data plane NICs as the first ones, reading testies %info section to understand topology specifics.

NICs parameters are defined in the format N:type where N is a NIC reference number,
and type is one of the following :
  * `ifname=interface_name`
  * `mac=ma:ca:dd:rr:es:s_`
  * `pci=0000:00:00.0`
  * `ip=static_address`

For tests using the standard networking stack, setting the `ip` and the `ifname` is enough, so each script can reference other node's IP address and use ifconfig tools using the ifname.

For tests using DPDK, and more generally L2 tests, the PCI adress and MAC should be defined.

See cluster01.node.sample for an example. Note that localhost.node is the default node used when roles are not defined or not mapped
