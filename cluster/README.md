For simple test case `--cluster client=user@server` argument is enough to configure an experiment to run the *client* role on the machine *server* using the username *user*. However to define more parameters for the server, such as the NIC orders and interface names, one must use a `.node` file. Typically, you will create a file named `server.node` in a folder named `cluster` alongside your NPF tests files that contains a few configuration variables for the machine named `server`.

Note : all communication is done through SSH. You should have passwordless connection set up using SSH keys.

3 global parameters are supported :
  * `addr=full_address_of_node` //if unset, the node name is used 
  * `path=path/to/npf`
  * `user=user_for_ssh_connection`

For instance, using `--cluster client=user01@server01.network.edu` is the same than using `--cluster client=server01` with the following `server01.node` file:
```
addr=server01.network.edu
user=user01
```

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
