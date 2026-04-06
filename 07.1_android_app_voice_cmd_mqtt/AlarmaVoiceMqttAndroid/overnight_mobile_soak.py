#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import json
import os
import re
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


APP_DIR = Path("/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/07.1_android_app_voice_cmd_mqtt/AlarmaVoiceMqttAndroid")
BASE_DIR = APP_DIR.parent
TOOLCHAIN_BASE = Path("/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/.toolchain")
ADB = TOOLCHAIN_BASE / "android-sdk/platform-tools/adb"
ALARMA = APP_DIR / "alarma"
PACKAGE = "com.ctone.alarmamqtt"


RID_HOST = "com.ctone.alarmamqtt:id/etBrokerHost"
RID_CONNECT = "com.ctone.alarmamqtt:id/btnConnect"
RID_DISCONNECT = "com.ctone.alarmamqtt:id/btnDisconnect"
RID_PUBLISH_ON = "com.ctone.alarmamqtt:id/btnPublishOn"
RID_PUBLISH_OFF = "com.ctone.alarmamqtt:id/btnPublishOff"
RID_CONNECTION = "com.ctone.alarmamqtt:id/tvConnectionState"
RID_LAST_MESSAGE = "com.ctone.alarmamqtt:id/tvLastMessage"
RID_LOG = "com.ctone.alarmamqtt:id/tvLog"


def run(cmd: list[str], check: bool = True, timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, check=check, timeout=timeout)


def host_ip() -> str:
    cmd = "ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i==\"src\") {print $(i+1); exit}}'"
    out = run(["bash", "-lc", cmd], check=False).stdout.strip()
    if out:
        return out
    out = run(["bash", "-lc", "hostname -I | awk '{print $1}'"], check=False).stdout.strip()
    return out or "192.168.0.179"


def adb(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return run([str(ADB), *args], check=check)


def alarma(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return run([str(ALARMA), *args], check=check)


def parse_bounds(bounds: str) -> tuple[int, int]:
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not m:
        return (0, 0)
    x1, y1, x2, y2 = map(int, m.groups())
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def ui_root() -> ET.Element | None:
    adb(["shell", "uiautomator", "dump", "/sdcard/alarma_ui.xml"], check=False)
    xml = adb(["shell", "cat", "/sdcard/alarma_ui.xml"], check=False).stdout.strip()
    if not xml:
        return None
    try:
        return ET.fromstring(xml)
    except ET.ParseError:
        return None


def node_by_id(root: ET.Element, rid: str):
    for node in root.iter("node"):
        if node.attrib.get("resource-id") == rid:
            return node
    return None


def node_text(node) -> str:
    if node is None:
        return ""
    return html.unescape(node.attrib.get("text", ""))


def node_enabled(node) -> bool:
    if node is None:
        return False
    return node.attrib.get("enabled", "false") == "true"


def tap_node(node) -> bool:
    if node is None:
        return False
    cx, cy = parse_bounds(node.attrib.get("bounds", ""))
    if cx <= 0 or cy <= 0:
        return False
    adb(["shell", "input", "tap", str(cx), str(cy)], check=False)
    return True


def keyevent(code: int) -> None:
    adb(["shell", "input", "keyevent", str(code)], check=False)


def input_text(value: str) -> None:
    safe = value.replace(" ", "%s")
    adb(["shell", "input", "text", safe], check=False)


def scroll_to_top() -> None:
    adb(["shell", "input", "swipe", "540", "700", "540", "1900", "250"], check=False)


def ensure_top_fields(root: ET.Element) -> ET.Element:
    if node_by_id(root, RID_CONNECTION) is not None and node_by_id(root, RID_HOST) is not None:
        return root
    scroll_to_top()
    time.sleep(0.5)
    refreshed = ui_root()
    return refreshed if refreshed is not None else root


def ensure_broker() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect(("127.0.0.1", 18883))
            return "running"
        except OSError:
            pass

    start_out = alarma(["start"], check=False).stdout
    time.sleep(1.0)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect(("127.0.0.1", 18883))
            if "Broker started" in start_out:
                return "started"
            return "running"
        except OSError:
            pass
    return "failed"


def ensure_app_running() -> bool:
    adb(["shell", "input", "keyevent", "224"], check=False)  # wake up
    adb(
        [
            "shell",
            "am",
            "start",
            "-n",
            "com.ctone.alarmamqtt/.MainActivity",
        ],
        check=False,
    )
    time.sleep(1.0)
    pid = adb(["shell", "pidof", PACKAGE], check=False).stdout.strip()
    if pid:
        return True
    alarma(["launch"], check=False)
    time.sleep(1.0)
    pid = adb(["shell", "pidof", PACKAGE], check=False).stdout.strip()
    return bool(pid)


def ensure_host(root: ET.Element, expected_host: str) -> tuple[ET.Element | None, str]:
    host_node = node_by_id(root, RID_HOST)
    if host_node is None:
        scroll_to_top()
        time.sleep(0.5)
        root = ui_root()
        if root is None:
            return None, "ui-missing"
        host_node = node_by_id(root, RID_HOST)
    if host_node is None:
        return root, "host-missing"

    current = node_text(host_node).strip()
    if current == expected_host:
        return root, "host-ok"

    tap_node(host_node)
    time.sleep(0.2)
    keyevent(123)  # move end
    for _ in range(32):
        keyevent(67)  # delete
    input_text(expected_host)
    time.sleep(0.3)
    keyevent(4)  # hide keyboard
    time.sleep(0.4)
    return ui_root(), f"host-set:{current}->{expected_host}"


def tap_connect_if_needed(root: ET.Element) -> tuple[ET.Element | None, str]:
    status_node = node_by_id(root, RID_CONNECTION)
    status = node_text(status_node)
    status_upper = status.upper()
    is_connected = ("CONNECTED" in status_upper) and ("DISCONNECTED" not in status_upper)
    if is_connected:
        return root, "already-connected"

    btn = node_by_id(root, RID_CONNECT)
    if btn is None or not node_enabled(btn):
        return root, "connect-disabled"

    tap_node(btn)
    time.sleep(2.0)
    return ui_root(), "connect-tap"


def pulse_publish(root: ET.Element) -> tuple[ET.Element | None, str]:
    on_btn = node_by_id(root, RID_PUBLISH_ON)
    off_btn = node_by_id(root, RID_PUBLISH_OFF)
    if on_btn is None or off_btn is None:
        return root, "publish-buttons-missing"
    if not node_enabled(on_btn) or not node_enabled(off_btn):
        return root, "publish-disabled"

    tap_node(on_btn)
    time.sleep(0.8)
    tap_node(off_btn)
    time.sleep(0.8)
    return ui_root(), "publish-arm-disarm"


def state_snapshot(root: ET.Element) -> dict:
    status = node_text(node_by_id(root, RID_CONNECTION))
    host = node_text(node_by_id(root, RID_HOST)).strip()
    last_msg = node_text(node_by_id(root, RID_LAST_MESSAGE)).replace("\n", " | ")
    log_text = node_text(node_by_id(root, RID_LOG))
    log_lines = [line for line in log_text.splitlines() if line.strip()]
    log_tail = " || ".join(log_lines[-3:]) if log_lines else ""
    return {
        "status": status,
        "host": host,
        "last_message": last_msg,
        "log_tail": log_tail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Overnight mobile MQTT soak via ADB")
    parser.add_argument("--hours", type=float, default=12.0)
    parser.add_argument("--interval-seconds", type=float, default=25.0)
    args = parser.parse_args()

    if not ADB.exists():
        print(f"ADB not found: {ADB}", file=sys.stderr)
        return 2

    now = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = BASE_DIR / "soak_mobile_logs" / f"run_{now}"
    out_dir.mkdir(parents=True, exist_ok=True)
    timeline_file = out_dir / "timeline.jsonl"
    summary_file = out_dir / "summary.json"
    logcat_file = out_dir / "adb_logcat.txt"

    expected_host = host_ip()
    deadline = time.time() + (args.hours * 3600.0)
    total_cycles = 0
    connected_cycles = 0
    publish_cycles = 0

    adb(["logcat", "-c"], check=False)
    with open(logcat_file, "w", encoding="utf-8") as lf:
        logcat_proc = subprocess.Popen(
            [str(ADB), "logcat", "-v", "time", "-s", "AlarmaMqtt:I", "AndroidRuntime:E", "AlarmPingSender:D"],
            stdout=lf,
            stderr=subprocess.STDOUT,
            text=True,
        )

    print(f"SOAK_DIR={out_dir}")
    print(f"TARGET_HOST={expected_host}")
    print(f"DURATION_HOURS={args.hours}")

    try:
        alarma(["install"], check=False)
        alarma(["launch"], check=False)

        while time.time() < deadline:
            total_cycles += 1
            ts = dt.datetime.now().isoformat(timespec="seconds")

            broker_state = ensure_broker()
            app_running = ensure_app_running()
            root = ui_root()

            event = {
                "ts": ts,
                "cycle": total_cycles,
                "broker": broker_state,
                "app_running": app_running,
                "host_action": "",
                "connect_action": "",
                "publish_action": "",
            }

            if root is None:
                event["error"] = "ui_dump_failed"
                with open(timeline_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=True) + "\n")
                print(f"[{ts}] cycle={total_cycles} ui_dump_failed")
                time.sleep(args.interval_seconds)
                continue

            root, host_action = ensure_host(root, expected_host)
            event["host_action"] = host_action
            if root is None:
                event["error"] = "ui_after_host_failed"
                with open(timeline_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=True) + "\n")
                print(f"[{ts}] cycle={total_cycles} ui_after_host_failed")
                time.sleep(args.interval_seconds)
                continue

            root = ensure_top_fields(root)
            root, connect_action = tap_connect_if_needed(root)
            event["connect_action"] = connect_action
            if root is None:
                event["error"] = "ui_after_connect_failed"
                with open(timeline_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=True) + "\n")
                print(f"[{ts}] cycle={total_cycles} ui_after_connect_failed")
                time.sleep(args.interval_seconds)
                continue

            root = ensure_top_fields(root)
            snap = state_snapshot(root)
            event.update(snap)
            status_upper = snap["status"].upper()
            connected = ("CONNECTED" in status_upper) and ("DISCONNECTED" not in status_upper)
            if connected:
                connected_cycles += 1
                if total_cycles % 2 == 0:
                    root, publish_action = pulse_publish(root)
                    event["publish_action"] = publish_action
                    if publish_action == "publish-arm-disarm":
                        publish_cycles += 1
                        if root is not None:
                            event.update(state_snapshot(root))

            with open(timeline_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=True) + "\n")

            print(
                f"[{ts}] cycle={total_cycles} broker={broker_state} status={event.get('status','')} "
                f"host={event.get('host','')} connect={connect_action} publish={event.get('publish_action','')}"
            )
            time.sleep(args.interval_seconds)
    finally:
        logcat_proc.terminate()
        try:
            logcat_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logcat_proc.kill()

    summary = {
        "started_at": now,
        "duration_hours": args.hours,
        "interval_seconds": args.interval_seconds,
        "total_cycles": total_cycles,
        "connected_cycles": connected_cycles,
        "connected_ratio": (connected_cycles / total_cycles) if total_cycles else 0.0,
        "publish_cycles": publish_cycles,
        "timeline_file": str(timeline_file),
        "logcat_file": str(logcat_file),
    }
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("SUMMARY_FILE=" + str(summary_file))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
