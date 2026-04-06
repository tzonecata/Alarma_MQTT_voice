#!/usr/bin/env bash
set -euo pipefail

LAB_DIR="/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab"
VENV="$LAB_DIR/.venv"
PID_FILE="/tmp/alarma_wifi_broker.pid"
LOG_FILE="/tmp/alarma_wifi_broker.log"
PORT="18883"

need_venv() {
  if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Missing Python venv in $VENV"
    echo "Run first:"
    echo "  cd $LAB_DIR"
    echo "  bash scripts/bootstrap.sh"
    exit 1
  fi
}

get_ip() {
  local ip
  ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}') || true
  if [[ -z "${ip:-}" ]]; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}') || true
  fi

  if [[ -z "${ip:-}" ]]; then
    echo "<UNKNOWN>"
  else
    echo "$ip"
  fi
}

broker_pid() {
  local pid=""
  if [[ -f "$PID_FILE" ]]; then
    pid=$(cat "$PID_FILE" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$pid"
      return
    fi
  fi

  pid=$(ss -ltnp 2>/dev/null | sed -n "s/.*:${PORT} .*pid=\\([0-9]\\+\\).*/\\1/p" | head -n1)
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "$pid" > "$PID_FILE"
    echo "$pid"
  fi
}

is_running() {
  if ss -ltn 2>/dev/null | rg -q ":${PORT}\\b"; then
    broker_pid >/dev/null 2>&1 || true
    return 0
  fi
  return 1
}

print_banner() {
  local host_ip="$1"
  echo "========================================"
  echo "Wi-Fi test MQTT broker"
  echo "Broker bind: 0.0.0.0:${PORT}"
  echo "Use this Host in Android app: ${host_ip}"
  echo "Username: mqttuser"
  echo "Password: mqttpass"
  echo "Topic: control_status_relay"
  echo "Control: start/stop/status/logs"
  echo "========================================"
}

start_broker() {
  need_venv

  if is_running; then
    local existing_pid
    existing_pid=$(broker_pid || true)
    print_banner "$(get_ip)"
    if [[ -n "${existing_pid:-}" ]]; then
      echo "Broker already running (pid=${existing_pid})"
    else
      echo "Broker already running on port ${PORT}"
    fi
    echo "Logs: ${LOG_FILE}"
    return
  fi

  nohup bash "$0" --foreground </dev/null >"$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"
  sleep 2

  if is_running; then
    local started_pid
    started_pid=$(broker_pid || true)
    print_banner "$(get_ip)"
    if [[ -n "${started_pid:-}" ]]; then
      echo "Broker started in background (pid=${started_pid})"
    else
      echo "Broker started in background (port ${PORT})"
    fi
    echo "Logs: ${LOG_FILE}"
  else
    echo "Broker failed to start. See log: ${LOG_FILE}" >&2
    tail -n 50 "$LOG_FILE" || true
    exit 1
  fi
}

stop_broker() {
  local pid
  pid=$(broker_pid || true)
  if [[ -z "${pid:-}" ]]; then
    echo "Broker not running"
    rm -f "$PID_FILE"
    return
  fi

  kill "$pid" 2>/dev/null || true
  sleep 1

  if is_running; then
    echo "Broker still running on port ${PORT}"
    exit 1
  fi

  rm -f "$PID_FILE"
  echo "Broker stopped"
}

status_broker() {
  local host_ip
  host_ip=$(get_ip)
  print_banner "$host_ip"

  if is_running; then
    local pid
    pid=$(broker_pid || true)
    if [[ -n "${pid:-}" ]]; then
      echo "Status: RUNNING (pid=${pid})"
    else
      echo "Status: RUNNING"
    fi
  else
    echo "Status: STOPPED"
  fi

  echo "Logs: ${LOG_FILE}"
}

logs_broker() {
  if [[ ! -f "$LOG_FILE" ]]; then
    echo "No broker log yet: ${LOG_FILE}"
    exit 1
  fi

  tail -f "$LOG_FILE"
}

run_foreground() {
  need_venv

  exec "$VENV/bin/python" - <<'PY'
import asyncio
import signal
from pathlib import Path

from amqtt.broker import Broker
from passlib.apps import custom_app_context as pwd_context

RUNTIME = Path("/tmp/alarma_wifi_broker")
RUNTIME.mkdir(parents=True, exist_ok=True)
PASSWD = RUNTIME / "passwd.txt"
PASSWD.write_text("mqttuser:" + pwd_context.hash("mqttpass") + "\n", encoding="utf-8")

CONFIG = {
    "listeners": {
        "default": {
            "type": "tcp",
            "bind": "0.0.0.0:18883",
        }
    },
    "plugins": {
        "amqtt.plugins.authentication.AnonymousAuthPlugin": {
            "allow_anonymous": False,
        },
        "amqtt.plugins.authentication.FileAuthPlugin": {
            "password_file": str(PASSWD),
        },
        "amqtt.plugins.sys.broker.BrokerSysPlugin": {
            "sys_interval": 60,
        },
    },
}


async def main() -> None:
    broker = Broker(CONFIG)
    await broker.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    await stop_event.wait()
    await broker.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
PY
}

cmd="${1:-start}"
case "$cmd" in
  start) start_broker ;;
  --stop|stop) stop_broker ;;
  --status|status) status_broker ;;
  --logs|logs) logs_broker ;;
  --foreground) run_foreground ;;
  *)
    echo "Usage: $0 [start|stop|status|logs]"
    exit 2
    ;;
esac
