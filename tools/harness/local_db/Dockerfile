# Dedicated daemon: never mount the host Docker socket or host directories here.
FROM ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc AS uv
FROM ubuntu:24.04@sha256:a853f94d226358a79c740cfc7bce0c289748f3fe3488d921d038ccd752c61b60
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git python3 python3-venv docker.io docker-compose-v2 iptables \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /uvx /usr/local/bin/
COPY entrypoint.sh /usr/local/bin/kineticloop-local-db
ENTRYPOINT ["/usr/local/bin/kineticloop-local-db"]
