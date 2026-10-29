# From a GNS3 design to local, remote and real testbeds

The same test, `examples/docker-web.npf`, runs unchanged at every stage. Only the `--cluster`/`--gns3` arguments and
the tags change.

## 0. The node image

`Dockerfile` builds a generic node (bash, curl, tc, nginx, ...). NPF starts scripts with `docker exec`, so no sshd is
needed. In GNS3, import it as a Docker template (Edit > Preferences > Docker containers > New, image `npf-node`,
adapters as needed, start command `sleep infinity` for clients). Tools you need in addition must be in the image.

## 1. Design in GNS3

Draw the client, DUT and server nodes and the links. **Node names give the NPF roles**: `client-1`, `client2` and
`client` are role `client`; `server` is role `server`. `--gns3-map role=node-name` overrides this. Only Docker nodes
are used, other nodes (switches, clouds, VMs) are listed as ignored.

## 2. Run locally on the GNS3 project

```
npf --test examples/docker-web.npf local --gns3 my-project --gns3-start
npf --test examples/docker-web.npf local --gns3 my-project --gns3-start --tags real netem   # real websites
python -m npf.cluster.gns3 list my-project     # shows the roles and the equivalent --cluster
```

`--gns3-start` opens the project and starts its nodes, and stops them at the end (`--gns3-keep` to keep them). The
GNS3 server is `$GNS3_URL` or http://127.0.0.1:3080; credentials come from the URL, `--gns3-user` and `$GNS3_PASSWORD`
(use `--gns3-api 3` for GNS3 3.x).

GNS3 Docker nodes do not see your folders, so NPF copies the experiment files and software in the node (tar over
`docker exec`) the same way it does over SSH.

## 3. Remote GNS3 server

```
npf --test examples/docker-web.npf local --gns3 my-project --gns3-url http://lab:3080 --gns3-start
```

For a GNS3 server that is not on localhost, NPF reaches the Docker daemon of that machine with `docker -H ssh://lab`.
Override with `--gns3-docker-host ssh://user@host` (or `local`). You need ssh access with docker usable on the
server, and the `docker` CLI on the NPF machine. Note that GNS3 Docker nodes need Linux (ubridge, privileges): on
macOS or Windows run the GNS3 server on a Linux host.

## 4. Real machines

Replace the roles by SSH nodes, the test is the same:

```
npf --test examples/docker-web.npf local --cluster client=user@host1 server=user@host2
npf --test examples/docker-web.npf local --cluster client=user@host1 --tags real
```

## Scaling to real servers

With `--tags real` the `server` role is not used: the client fetches each URL of the `sites.txt` section of
`docker-web.npf`, one per `SITE_ID`. Put your list in that section and set the range, e.g. `--variables SITE_ID=[1-500]`.
Keep `n_runs` low and the request rate polite when hitting sites you do not own.

## Without GNS3

```
docker compose -f examples/docker-testbed/docker-compose.yml up -d --build
npf --test examples/docker-web.npf local --cluster client=docker://npf-client server=docker://npf-server
```

`docker://container[,dockerhost=ssh://user@host][,path=/remote/folder][,nfs=0|1]`: `dockerhost` selects a remote
daemon, `nfs=1` forces the shared mode (experiment folder mounted at the same path), `nfs=0` the copy mode, `path`
the folder used in copy mode (default: the same absolute path as locally).
