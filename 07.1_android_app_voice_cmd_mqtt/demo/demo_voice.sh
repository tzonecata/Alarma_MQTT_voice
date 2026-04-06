#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/07.1_android_app_voice_cmd_mqtt"
DEMO_SCRIPT="$ROOT_DIR/demo/run_demo.py"

exec python3 "$DEMO_SCRIPT" \
  --mode random_broker_then_listen \
  --random-duration 60 \
  --random-min-interval 2 \
  --random-max-interval 5 \
  "$@"
