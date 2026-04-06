#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/07.1_android_app_voice_cmd_mqtt/AlarmaVoiceMqttAndroid"
TOOLCHAIN_BASE="/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/.toolchain"
LAB_BIN="/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin"

ALARMA="$APP_DIR/alarma"
BUILD_SCRIPT="$APP_DIR/build_apk_on_ubuntu.sh"
ADB="$TOOLCHAIN_BASE/android-sdk/platform-tools/adb"
PUB="$LAB_BIN/amqtt_pub"
SUB="$LAB_BIN/amqtt_sub"

TOPIC="control_status_relay"
BROKER_URL="mqtt://mqttuser:mqttpass@127.0.0.1:18883"
DURATION_SECONDS=120

RUN_ID="${RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
WORK_DIR="/tmp/alarma_demo_${RUN_ID}"
READY_FILE="$WORK_DIR/ready"
FAIL_FILE="$WORK_DIR/fail"
LATEST_WORK_FILE="/tmp/alarma_demo_latest_workdir"
PIDS_FILE="$WORK_DIR/pids"

MODE="run"
if [[ "${1:-}" == "--dry-run" ]]; then
  MODE="dry-run"
elif [[ "${1:-}" == "--stop" ]]; then
  MODE="stop"
fi

need_file() {
  local f="$1"
  if [[ ! -e "$f" ]]; then
    echo "Missing required file: $f" >&2
    exit 1
  fi
}

need_file "$ALARMA"
need_file "$BUILD_SCRIPT"
need_file "$ADB"
need_file "$PUB"
need_file "$SUB"

if [[ "$MODE" == "stop" ]]; then
  echo "Stopping latest DEMO processes..."
  if [[ -f "$LATEST_WORK_FILE" ]]; then
    target_work_dir="$(cat "$LATEST_WORK_FILE" 2>/dev/null || true)"
    if [[ -n "${target_work_dir:-}" ]]; then
      pkill -f "${target_work_dir}/tab0[1-6]_" >/dev/null 2>&1 || true
      pkill -f "${target_work_dir}/wait_ready.sh" >/dev/null 2>&1 || true
      echo "Stopped tab processes from: $target_work_dir"
    fi
  fi

  pkill -f "amqtt_pub --url .* -t ${TOPIC}" >/dev/null 2>&1 || true
  pkill -f "amqtt_sub --url .* -t ${TOPIC}" >/dev/null 2>&1 || true

  "$ALARMA" stop >/dev/null 2>&1 || true
  echo "Broker stop requested via: $ALARMA stop"
  echo "Demo stop completed."
  exit 0
fi

mkdir -p "$WORK_DIR"
rm -f "$READY_FILE" "$FAIL_FILE"
rm -f "$PIDS_FILE"
echo "$WORK_DIR" > "$LATEST_WORK_FILE"

cat > "$WORK_DIR/common.env" <<EOF
export RUN_ID="$RUN_ID"
export DURATION_SECONDS="$DURATION_SECONDS"
export READY_FILE="$READY_FILE"
export FAIL_FILE="$FAIL_FILE"
export ALARMA="$ALARMA"
export BUILD_SCRIPT="$BUILD_SCRIPT"
export ADB="$ADB"
export PUB="$PUB"
export SUB="$SUB"
export TOPIC="$TOPIC"
export BROKER_URL="$BROKER_URL"
EOF

cat > "$WORK_DIR/wait_ready.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.env"

for _ in $(seq 1 180); do
  if [[ -f "$READY_FILE" ]]; then
    exit 0
  fi
  if [[ -f "$FAIL_FILE" ]]; then
    echo "[WAIT] Bootstrap failed, stopping tab." >&2
    exit 1
  fi
  sleep 1
done

echo "[WAIT] Timeout waiting for bootstrap." >&2
exit 1
EOF

cat > "$WORK_DIR/tab01_bootstrap.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.env"

trap 'echo "[BOOT][ERROR] bootstrap failed"; touch "$FAIL_FILE"' ERR

echo "======================================================"
echo "DEMO RUN: $RUN_ID"
echo "TAB [01] BOOTSTRAP_BUILD_INSTALL"
echo "======================================================"
echo "[01] Build APK..."
bash "$BUILD_SCRIPT"

echo "[01] Start broker..."
"$ALARMA" start

echo "[01] Install app..."
"$ALARMA" install

echo "[01] Launch app..."
"$ALARMA" launch

touch "$READY_FILE"
heartbeat_loops=$((DURATION_SECONDS / 5))
if [[ "$heartbeat_loops" -lt 1 ]]; then heartbeat_loops=1; fi
echo "[01] READY: demo stack up. Running status heartbeat for ${DURATION_SECONDS}s..."

for i in $(seq 1 "$heartbeat_loops"); do
  now="$(date +%H:%M:%S)"
  echo
  echo "[01][$now] Heartbeat $i/$heartbeat_loops"
  "$ALARMA" status || true
  sleep 5
done

echo
echo "[01] Bootstrap tab finished."
echo "[01] Close this tab when done."
exec bash
EOF

cat > "$WORK_DIR/tab02_broker_log.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.env"
"$(dirname "$0")/wait_ready.sh"

echo "======================================================"
echo "DEMO RUN: $RUN_ID"
echo "TAB [02] BROKER_LOG_LIVE"
echo "======================================================"
echo "[02] Live broker log: /tmp/alarma_wifi_broker.log"
tail -n +1 -f /tmp/alarma_wifi_broker.log
EOF

cat > "$WORK_DIR/tab03_mqtt_sub.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.env"
"$(dirname "$0")/wait_ready.sh"

echo "======================================================"
echo "DEMO RUN: $RUN_ID"
echo "TAB [03] MQTT_SUBSCRIBER_LIVE"
echo "======================================================"
echo "[03] Subscribing topic: $TOPIC"
echo "[03] URL: $BROKER_URL"
echo "[03] Streamul MQTT ramane activ si dupa demo; opreste-l cu demo_live_5m.sh --stop sau inchizand tab-ul."

"$SUB" --url "$BROKER_URL" -t "$TOPIC" -q 1
EOF

cat > "$WORK_DIR/tab04_random_pub.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.env"
"$(dirname "$0")/wait_ready.sh"

echo "======================================================"
echo "DEMO RUN: $RUN_ID"
echo "TAB [04] RANDOM_ARM_DISARM_PUBLISHER_5M"
echo "======================================================"

start_ts="$(date +%s)"
end_ts="$((start_ts + DURATION_SECONDS))"
count=0
count_arm=0
count_disarm=0

while [[ "$(date +%s)" -lt "$end_ts" ]]; do
  rnd=$((RANDOM % 2))
  if [[ "$rnd" -eq 0 ]]; then
    payload="ARMEAZA"
    count_arm=$((count_arm + 1))
  else
    payload="DEZARMEAZA"
    count_disarm=$((count_disarm + 1))
  fi

  count=$((count + 1))
  now="$(date +%H:%M:%S)"
  "$PUB" --url "$BROKER_URL" -t "$TOPIC" -m "$payload" -q 1 >/dev/null 2>&1 || true
  echo "[04][$now] TX #$count payload=$payload"

  sleep_time=$((2 + RANDOM % 5))
  sleep "$sleep_time"
done

echo
echo "[04] Finished random publish for ${DURATION_SECONDS}s"
echo "[04] Total sent: $count | ARMEAZA=$count_arm | DEZARMEAZA=$count_disarm"
exec bash
EOF

cat > "$WORK_DIR/tab05_app_logcat.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.env"
"$(dirname "$0")/wait_ready.sh"

echo "======================================================"
echo "DEMO RUN: $RUN_ID"
echo "TAB [05] ANDROID_LOGCAT_MQTT"
echo "======================================================"
echo "[05] Clearing logcat and following AlarmaMqtt + AndroidRuntime..."

"$ADB" logcat -c || true
timeout "$((DURATION_SECONDS + 30))" "$ADB" logcat -v time -s AlarmaMqtt:V AndroidRuntime:E || true

echo
echo "[05] Logcat window finished."
exec bash
EOF

cat > "$WORK_DIR/tab06_status_watch.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.env"
"$(dirname "$0")/wait_ready.sh"

echo "======================================================"
echo "DEMO RUN: $RUN_ID"
echo "TAB [06] SYSTEM_STATUS_WATCH"
echo "======================================================"

loops=$((DURATION_SECONDS / 5))
if [[ "$loops" -lt 1 ]]; then loops=1; fi

for i in $(seq 1 "$loops"); do
  now="$(date +%H:%M:%S)"
  rem=$((loops - i))
  echo
  echo "[06][$now] Tick $i/$loops (remaining ~${rem}x5s)"
  "$ALARMA" status | sed 's/\x1b\[[0-9;]*m//g' || true
  echo "[06] Broker socket check:"
  ss -ltn | rg "18883" || true
  echo "[06] App PID:"
  "$ADB" shell pidof com.ctone.alarmamqtt || true
  sleep 5
done

echo
echo "[06] Status watch finished."
exec bash
EOF

chmod +x "$WORK_DIR"/*.sh

if [[ "$MODE" == "dry-run" ]]; then
  echo "DEMO script prepared in: $WORK_DIR"
  ls -la "$WORK_DIR"
  echo "Run without --dry-run to launch tabs."
  exit 0
fi

TERMINAL="${DEMO_TERMINAL:-}"
HEADLESS="${DEMO_HEADLESS:-0}"

if [[ -z "${DISPLAY:-}" ]]; then
  HEADLESS="1"
fi

if [[ "$HEADLESS" != "1" ]]; then
  if [[ -z "$TERMINAL" ]]; then
    if command -v x-terminal-emulator >/dev/null 2>&1; then
      TERMINAL="x-terminal-emulator"
    elif command -v gnome-terminal >/dev/null 2>&1; then
      TERMINAL="gnome-terminal"
    else
      echo "No supported terminal launcher found, switching to headless mode."
      HEADLESS="1"
    fi
  fi
fi

launch_window() {
  local title="$1"
  local script="$2"

  if [[ "$TERMINAL" == "x-terminal-emulator" ]]; then
    # x-terminal-emulator works reliably on Ubuntu alternatives; launch one window per stream.
    x-terminal-emulator -T "$title" -e bash -lc "$script" &
  elif [[ "$TERMINAL" == "gnome-terminal" ]]; then
    gnome-terminal --title="$title" -- bash -lc "$script" &
  else
    echo "Unsupported DEMO_TERMINAL value: $TERMINAL" >&2
    exit 1
  fi

  echo "$!" >> "$PIDS_FILE"
}

launch_headless() {
  local name="$1"
  local script="$2"
  local logfile="$WORK_DIR/${name}.log"
  nohup bash -lc "$script" > "$logfile" 2>&1 &
  echo "$!" >> "$PIDS_FILE"
  echo "HEADLESS stream: $name -> $logfile"
}

if [[ "$HEADLESS" == "1" ]]; then
  launch_headless "01_BOOTSTRAP_BUILD_INSTALL" "$WORK_DIR/tab01_bootstrap.sh"
  launch_headless "02_BROKER_LOG_LIVE" "$WORK_DIR/tab02_broker_log.sh"
  launch_headless "03_MQTT_SUBSCRIBER_LIVE" "$WORK_DIR/tab03_mqtt_sub.sh"
  launch_headless "04_RANDOM_ARM_DISARM_PUBLISHER_5M" "$WORK_DIR/tab04_random_pub.sh"
  launch_headless "05_ANDROID_LOGCAT_MQTT" "$WORK_DIR/tab05_app_logcat.sh"
  launch_headless "06_SYSTEM_STATUS_WATCH" "$WORK_DIR/tab06_status_watch.sh"
else
  launch_window "[${RUN_ID}] 01_BOOTSTRAP_BUILD_INSTALL" "$WORK_DIR/tab01_bootstrap.sh"
  sleep 0.2
  launch_window "[${RUN_ID}] 02_BROKER_LOG_LIVE" "$WORK_DIR/tab02_broker_log.sh"
  sleep 0.2
  launch_window "[${RUN_ID}] 03_MQTT_SUBSCRIBER_LIVE" "$WORK_DIR/tab03_mqtt_sub.sh"
  sleep 0.2
  launch_window "[${RUN_ID}] 04_RANDOM_ARM_DISARM_PUBLISHER_5M" "$WORK_DIR/tab04_random_pub.sh"
  sleep 0.2
  launch_window "[${RUN_ID}] 05_ANDROID_LOGCAT_MQTT" "$WORK_DIR/tab05_app_logcat.sh"
  sleep 0.2
  launch_window "[${RUN_ID}] 06_SYSTEM_STATUS_WATCH" "$WORK_DIR/tab06_status_watch.sh"
fi

echo "DEMO launched."
echo "RUN_ID=$RUN_ID"
echo "WORK_DIR=$WORK_DIR"
echo "TERMINAL=${TERMINAL:-headless}"
echo "HEADLESS=$HEADLESS"
echo "To stop demo: $0 --stop"
if [[ "$HEADLESS" == "1" ]]; then
  echo "To watch all logs live:"
  echo "tail -n +1 -f \"$WORK_DIR\"/*.log"
fi
