FROM ubuntu:20.04
RUN apt-get update && apt-get install -y python3 python3-pip git && rm -rf /var/lib/apt/lists/*
COPY . /npf
RUN cd /npf && python3 -m pip install -r /npf/requirements.txt
CMD [""]
