#!/usr/bin/env bash
# Start Umeed. No dependencies beyond Python 3.8+.
#
#   ./run.sh                      # start on http://localhost:8000
#   UMEED_PORT=9000 ./run.sh      # choose a port
#   UMEED_MANAGER_PASSCODE=secret ./run.sh   # set the manager passcode
set -euo pipefail
cd "$(dirname "$0")"
exec python3 server.py "$@"
