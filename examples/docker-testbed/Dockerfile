FROM debian:bookworm-slim

# Generic NPF node: bash + the tools used by the examples. Scripts are started with `docker exec`, no sshd needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash curl ca-certificates iproute2 iputils-ping procps sudo nginx dnsutils \
    && rm -rf /var/lib/apt/lists/*

CMD ["nginx", "-g", "daemon off;"]
