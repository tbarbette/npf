#!/bin/bash

if ! ssh -f -q -o BatchMode=yes -o StrictHostKeyChecking=no $USER@127.0.0.100 -C "whoami" ; then
    echo "Warning: there's no SSH working to 127.0.0.100, cannot try ssh executor"
    exit 0
fi

set -e

mkdir -p /tmp/npf
python3 ./npf-run.py local/$(pwd)/libs/ --test integration/localcopy.npf --cluster dut=tbarbette@127.0.0.100:/tmp/npf/,nfs=0 --show-all --force-retest
rm -rf /tmp/npf


python3 ./npf-run.py local/$(pwd)/libs/ --test integration/localcopy.npf --cluster dut=tbarbette@127.0.0.100 --show-all --force-retest


