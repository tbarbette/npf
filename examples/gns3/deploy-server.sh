#!/bin/bash
# Installs a GNS3 server on a Linux host, as the testbed of NPF tests (see ../docker-testbed/README.md).
#
#   ssh HOST 'bash -s' < examples/gns3/deploy-server.sh
#
# Needs on HOST: sudo, docker (your user in the docker group), python3-venv, gcc, make, git, libpcap-dev.
# Everything is under $PREFIX (default /opt/gns3, a local disk: setuid does not work on NFS homes) and one systemd unit.
# The API listens on 127.0.0.1:3080 only and has no authentication: reach it with  ssh -L 3080:127.0.0.1:3080 HOST
# Remove with:
#   sudo systemctl disable --now gns3-server; sudo rm /etc/systemd/system/gns3-server.service; sudo rm -rf /opt/gns3
set -euo pipefail

PREFIX=${PREFIX:-/opt/gns3}
GNS3_SPEC=${GNS3_SPEC:-gns3-server<3}      # 2.2.x keeps the v2 API that NPF uses by default
PORT=${PORT:-3080}
RUN_USER=$(id -un)

getent group docker > /dev/null || { echo "No docker group on this host"; exit 1; }
id -nG | grep -qw docker || { echo "$RUN_USER is not in the docker group"; exit 1; }

sudo mkdir -p "$PREFIX"
sudo chown "$RUN_USER":docker "$PREFIX"
mkdir -p "$PREFIX"/{bin,projects,images,home}
cd "$PREFIX"

[ -x venv/bin/python ] || python3 -m venv venv
./venv/bin/pip install -q --upgrade pip wheel
./venv/bin/pip install -q --upgrade "$GNS3_SPEC"

# ubridge connects the Docker nodes to the links. It needs root: setuid, executable by the docker group only (who
# are root-equivalent anyway).
if [ -d src-ubridge ]; then git -C src-ubridge pull -q; else git clone -q --depth 1 https://github.com/GNS3/ubridge.git src-ubridge; fi
make -C src-ubridge > ubridge-build.log
sudo install -o root -g docker -m 4750 src-ubridge/ubridge bin/ubridge

cat > gns3_server.conf <<CONF
[Server]
host = 127.0.0.1
port = $PORT
auth = False
ubridge_path = $PREFIX/bin/ubridge
projects_path = $PREFIX/projects
images_path = $PREFIX/images
CONF

sudo tee /etc/systemd/system/gns3-server.service > /dev/null <<UNIT
[Unit]
Description=GNS3 server (API on 127.0.0.1:$PORT)
After=network-online.target docker.service
Wants=docker.service

[Service]
User=$RUN_USER
Group=docker
Environment=HOME=$PREFIX/home
ExecStart=$PREFIX/venv/bin/gns3server --config $PREFIX/gns3_server.conf --log $PREFIX/gns3server.log
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable gns3-server > /dev/null 2>&1
sudo systemctl restart gns3-server

for _ in $(seq 30); do
    if curl -fsS "http://127.0.0.1:$PORT/v2/version" 2> /dev/null; then echo; echo "GNS3 server is up"; exit 0; fi
    sleep 1
done
echo "GNS3 server did not answer, see: journalctl -u gns3-server; tail $PREFIX/gns3server.log"
exit 1
