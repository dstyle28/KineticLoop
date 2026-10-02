#!/bin/bash
set -euo pipefail
mkdir -p /run/kineticloop-local-db /evidence
printf '%s\n' "dedicated-container-daemon-v1" > /run/kineticloop-local-db/owner
exec dockerd --host=unix:///var/run/docker.sock --storage-driver=overlay2
