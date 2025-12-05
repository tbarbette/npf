#!/bin/bash
# Run integration inside docker
docker build --tag npf .
docker run --rm -it npf /bin/bash -c "cd /npf/ && integration/integration.sh python3"