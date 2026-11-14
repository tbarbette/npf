FROM ubuntu:24.04
RUN apt-get update && apt-get install -y python3 python3-venv git bc && rm -rf /var/lib/apt/lists/*
COPY . /npf
# Ubuntu does not let pip install in the system Python (PEP 668): install NPF in a virtual environment
RUN python3 -m venv /opt/npf && cd /npf && /opt/npf/bin/pip install --no-cache-dir -r /npf/requirements.txt
ENV PATH=/opt/npf/bin:$PATH
CMD [""]
