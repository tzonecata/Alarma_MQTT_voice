#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/mqtt-lab" ]]; then
  echo "Virtualenv missing. Run: bash scripts/bootstrap.sh"
  exit 1
fi

source .venv/bin/activate
mqtt-lab smoke --config config/default.yaml "$@"
