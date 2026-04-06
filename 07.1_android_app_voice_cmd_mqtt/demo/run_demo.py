#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import random
import re
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT_DIR = Path("/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/07.1_android_app_voice_cmd_mqtt")
APP_DIR = ROOT_DIR / "AlarmaVoiceMqttAndroid"
TOOLCHAIN_BASE = Path("/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/.toolchain")
LAB_BIN = Path("/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin")

ADB = TOOLCHAIN_BASE / "android-sdk/platform-tools/adb"
BUILD_SCRIPT = APP_DIR / "build_apk_on_ubuntu.sh"
BROKER_SCRIPT = APP_DIR / "start_wifi_broker.sh"
APK_PATH = APP_DIR / "app/build/outputs/apk/debug/app_Voice_HA_mgtt.apk"
PUB = LAB_BIN / "amqtt_pub"
SUB = LAB_BIN / "amqtt_sub"

PACKAGE = "com.ctone.alarmamqtt"
ACTIVITY = f"{PACKAGE}/.MainActivity"
BROKER_PORT = 18883
ADB_REVERSE_SPEC = f"tcp:{BROKER_PORT}"

RID_HOST = f"{PACKAGE}:id/etBrokerHost"
RID_PORT = f"{PACKAGE}:id/etBrokerPort"
RID_USERNAME = f"{PACKAGE}:id/etUsername"
RID_PASSWORD = f"{PACKAGE}:id/etPassword"
RID_TOPIC = f"{PACKAGE}:id/etTopic"
RID_CONNECT = f"{PACKAGE}:id/btnConnect"
RID_PUBLISH_ON = f"{PACKAGE}:id/btnPublishOn"
RID_PUBLISH_OFF = f"{PACKAGE}:id/btnPublishOff"
RID_CONNECTION = f"{PACKAGE}:id/tvConnectionState"
RID_LAST_MESSAGE = f"{PACKAGE}:id/tvLastMessage"
RID_LOG = f"{PACKAGE}:id/tvLog"

PAYLOAD_ARM = "ARMEAZA"
PAYLOAD_DISARM = "DEZARMEAZA"
DEFAULT_BROKER_SEQUENCE = f"{PAYLOAD_ARM},{PAYLOAD_DISARM}"
DEFAULT_PHONE_SEQUENCE = DEFAULT_BROKER_SEQUENCE
DEFAULT_RANDOM_PAYLOADS = DEFAULT_BROKER_SEQUENCE
DEFAULT_RANDOM_DEMO_DURATION_SECONDS = 60
DEFAULT_RANDOM_MIN_INTERVAL_SECONDS = 2
DEFAULT_RANDOM_MAX_INTERVAL_SECONDS = 5
SEQUENCE_SETTLE_SECONDS = 1.5
AUTO_DEMO_HEARTBEAT_SECONDS = 15
MODE_RANDOM_BROKER_THEN_LISTEN = "random_broker_then_listen"
MODE_CONTINUOUS_BIDIRECTIONAL = "continuous_bidirectional"
MANUAL_STOP_SIGNALS = {"SIGINT", "KEYBOARD_INTERRUPT"}


class DemoTermination(KeyboardInterrupt):
    def __init__(self, signal_name: str) -> None:
        super().__init__(signal_name)
        self.signal_name = signal_name


def log(message: str) -> None:
    now = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {message}", flush=True)


def parse_sequence(raw_value: str, option_name: str) -> list[str]:
    normalized_map = {
        PAYLOAD_ARM: PAYLOAD_ARM,
        PAYLOAD_DISARM: PAYLOAD_DISARM,
        "ARM": PAYLOAD_ARM,
        "DISARM": PAYLOAD_DISARM,
        "ON": PAYLOAD_ARM,
        "OFF": PAYLOAD_DISARM,
    }

    cleaned_value = raw_value.strip()
    if not cleaned_value:
        return []

    sequence: list[str] = []
    for item in cleaned_value.split(","):
        token = item.strip().upper()
        if not token:
            continue
        payload = normalized_map.get(token)
        if payload is None:
            accepted = ", ".join(sorted(normalized_map))
            raise ValueError(f"{option_name} contine payload invalid: {item!r}. Acceptate: {accepted}")
        sequence.append(payload)
    return sequence


def run(
    cmd: list[str],
    *,
    check: bool = True,
    timeout: float | None = None,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        check=check,
        timeout=timeout,
        capture_output=capture_output,
    )


def adb(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run([str(ADB), *args], check=check)


def host_ip() -> str:
    route_cmd = "ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i==\"src\") {print $(i+1); exit}}'"
    out = run(["bash", "-lc", route_cmd], check=False).stdout.strip()
    if out:
        return out
    out = run(["bash", "-lc", "hostname -I | awk '{print $1}'"], check=False).stdout.strip()
    if out:
        return out
    return "192.168.1.100"


def broker_is_up() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect(("127.0.0.1", BROKER_PORT))
            return True
        except OSError:
            return False


def wait_for_broker(timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if broker_is_up():
            return True
        time.sleep(0.5)
    return False


def ensure_device() -> str:
    result = adb(["devices"])
    devices = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices attached"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    if not devices:
        raise RuntimeError("Nu am gasit niciun telefon conectat prin ADB.")
    return devices[0]


def setup_adb_reverse() -> None:
    log(f"Activez adb reverse pentru portul {BROKER_PORT}")
    result = adb(["reverse", ADB_REVERSE_SPEC, ADB_REVERSE_SPEC], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Nu am putut activa adb reverse pe portul {BROKER_PORT}.")


def remove_adb_reverse() -> None:
    adb(["reverse", "--remove", ADB_REVERSE_SPEC], check=False)


def wake_and_unlock() -> None:
    adb(["shell", "input", "keyevent", "224"], check=False)
    adb(["shell", "input", "keyevent", "82"], check=False)
    adb(["shell", "wm", "dismiss-keyguard"], check=False)
    time.sleep(0.5)


def start_broker(artifacts_dir: Path) -> tuple[subprocess.Popen[str] | None, bool]:
    if broker_is_up():
        log("Brokerul MQTT este deja pornit pe 127.0.0.1:18883")
        return None, False

    broker_log = artifacts_dir / "broker.log"
    log(f"Pornesc brokerul MQTT cu {BROKER_SCRIPT}")
    log_file = broker_log.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        ["bash", str(BROKER_SCRIPT)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )

    if not wait_for_broker(timeout_seconds=20):
        raise RuntimeError(f"Brokerul nu a pornit. Vezi logul: {broker_log}")

    (artifacts_dir / "broker.pid").write_text(f"{proc.pid}\n", encoding="utf-8")
    log(f"Broker pornit cu PID {proc.pid}")
    return proc, True


def stop_process(proc: subprocess.Popen[str] | None, name: str, *, announce: bool = True) -> None:
    if proc is None:
        return
    if announce:
        log(f"Opresc {name} (pid={proc.pid})")
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.2)

    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def build_apk() -> None:
    log("Compilez APK-ul")
    result = run(["bash", str(BUILD_SCRIPT)], check=False)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError("Build-ul APK a esuat.")
    log("APK compilat cu succes")


def install_apk() -> None:
    log("Instalez APK-ul pe telefon")
    result = adb(["install", "-r", str(APK_PATH)], check=False)
    if result.returncode != 0 or "Success" not in result.stdout:
        raise RuntimeError(f"Instalarea APK a esuat:\n{result.stdout}\n{result.stderr}")
    log("APK instalat cu succes")


def launch_app() -> None:
    log("Lansez aplicatia pe telefon")
    wake_and_unlock()
    adb(["shell", "am", "start", "-n", ACTIVITY], check=False)
    time.sleep(2.0)


def stop_app() -> None:
    log("Opresc aplicatia de pe telefon pentru a inchide voice loop-ul")
    adb(["shell", "am", "force-stop", PACKAGE], check=False)
    time.sleep(0.5)


def stop_voice_loop(*, announce: bool = True) -> None:
    if announce:
        log("Trimit comanda catre aplicatie sa opreasca doar voice loop-ul")
    adb(
        ["shell", "am", "start", "-n", ACTIVITY, "-a", f"{PACKAGE}.action.STOP_VOICE_LOOP"],
        check=False,
    )
    time.sleep(1.0)


def should_stop_app_on_exit(summary: dict[str, object]) -> bool:
    stop_signal = summary.get("stop_signal")
    return stop_signal not in MANUAL_STOP_SIGNALS


def start_logcat_stream(artifacts_dir: Path) -> subprocess.Popen[str]:
    app_log = artifacts_dir / "app_logcat.log"
    cleanup_stale_logcat_streams()
    log("Pornesc logcat live pentru aplicatie")
    adb(["logcat", "-c"], check=False)
    app_log.write_text("", encoding="utf-8")
    logcat_cmd = (
        f"stdbuf -oL -eL {shlex.quote(str(ADB))} logcat -v time -s "
        f"AlarmaMqtt:V AndroidRuntime:E | tee -a {shlex.quote(str(app_log))}"
    )
    proc = subprocess.Popen(
        ["bash", "-lc", logcat_cmd],
        start_new_session=True,
        env={
            **dict(os.environ),
            "PYTHONUNBUFFERED": "1",
        },
    )
    (artifacts_dir / "logcat.pid").write_text(f"{proc.pid}\n", encoding="utf-8")
    log(f"Logcat pornit cu PID {proc.pid}; va ramane activ pana la Ctrl+C")
    time.sleep(1.0)
    return proc


def cleanup_stale_logcat_streams() -> None:
    artifacts_root = ROOT_DIR / "demo" / "artifacts"
    if not artifacts_root.exists():
        return

    cleaned = 0
    for pid_file in sorted(artifacts_root.glob("run_*/logcat.pid")):
        pid_text = pid_file.read_text(encoding="utf-8", errors="replace").strip()
        try:
            pid = int(pid_text)
        except ValueError:
            pid_file.unlink(missing_ok=True)
            continue

        try:
            os.killpg(pid, signal.SIGTERM)
            cleaned += 1
        except ProcessLookupError:
            pass
        finally:
            pid_file.unlink(missing_ok=True)

    if cleaned:
        log(f"Am curatat {cleaned} sesiuni logcat ramase din demo-uri anterioare")


def input_text(value: str) -> None:
    safe = value.replace(" ", "%s")
    adb(["shell", "input", "text", safe], check=False)


def keyevent(code: int) -> None:
    adb(["shell", "input", "keyevent", str(code)], check=False)


def dump_ui() -> ET.Element | None:
    last_error = ""
    for attempt in range(1, 4):
        adb(["shell", "rm", "-f", "/sdcard/voice_alarm_demo_ui.xml"], check=False)
        dump_result = adb(["shell", "uiautomator", "dump", "/sdcard/voice_alarm_demo_ui.xml"], check=False)
        xml_result = adb(["shell", "cat", "/sdcard/voice_alarm_demo_ui.xml"], check=False)
        xml = xml_result.stdout.strip()
        if xml:
            try:
                return ET.fromstring(xml)
            except ET.ParseError as exc:
                last_error = f"XML invalid: {exc}"
        else:
            details = " ".join(
                part.strip()
                for part in (
                    dump_result.stdout,
                    dump_result.stderr,
                    xml_result.stdout,
                    xml_result.stderr,
                )
                if part and part.strip()
            )
            last_error = details or "uiautomator dump nu a produs XML"

        if attempt < 3:
            log(f"uiautomator dump a esuat la incercarea {attempt}/3; reincerc")
            time.sleep(0.5)

    raise RuntimeError(
        "uiautomator dump a esuat pe telefon; crash-ul este in tool-ul Android, nu in aplicatia MQTT. "
        f"Detalii: {last_error}"
    )


def node_by_id(root: ET.Element | None, resource_id: str):
    if root is None:
        return None
    for node in root.iter("node"):
        if node.attrib.get("resource-id") == resource_id:
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


def parse_bounds(bounds: str) -> tuple[int, int]:
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        return (0, 0)
    x1, y1, x2, y2 = map(int, match.groups())
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def tap_node(node) -> bool:
    if node is None:
        return False
    x, y = parse_bounds(node.attrib.get("bounds", ""))
    if x <= 0 or y <= 0:
        return False
    adb(["shell", "input", "tap", str(x), str(y)], check=False)
    return True


def swipe(start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int = 250) -> None:
    adb(
        ["shell", "input", "swipe", str(start_x), str(start_y), str(end_x), str(end_y), str(duration_ms)],
        check=False,
    )


def scroll_to_top() -> None:
    swipe(540, 700, 540, 1900)
    time.sleep(0.5)


def scroll_to_commands() -> None:
    swipe(540, 1800, 540, 800)
    time.sleep(0.8)


def ensure_field_value(resource_id: str, value: str) -> None:
    root = dump_ui()
    node = node_by_id(root, resource_id)
    if node is None:
        scroll_to_top()
        root = dump_ui()
        node = node_by_id(root, resource_id)
    if node is None:
        raise RuntimeError(f"Nu am gasit campul {resource_id} in UI.")

    if node_text(node).strip() == value:
        return

    if not tap_node(node):
        raise RuntimeError(f"Nu pot selecta campul {resource_id}.")
    time.sleep(0.3)
    keyevent(123)
    for _ in range(48):
        keyevent(67)
    input_text(value)
    time.sleep(0.4)
    keyevent(4)
    time.sleep(0.3)


def configure_app(host: str, port: str, username: str, password: str, topic: str) -> None:
    log("Configurez campurile MQTT din aplicatie")
    scroll_to_top()
    ensure_field_value(RID_HOST, host)
    ensure_field_value(RID_PORT, port)
    ensure_field_value(RID_USERNAME, username)
    ensure_field_value(RID_PASSWORD, password)
    ensure_field_value(RID_TOPIC, topic)


def connect_app() -> None:
    log("Fac connect din aplicatie")
    scroll_to_top()
    root = dump_ui()
    status = node_text(node_by_id(root, RID_CONNECTION)).upper()
    if "CONNECTED" in status and "DISCONNECTED" not in status:
        log("Aplicatia este deja conectata")
        return

    button = node_by_id(root, RID_CONNECT)
    if button is None or not node_enabled(button):
        raise RuntimeError("Butonul Connect nu este disponibil.")
    tap_node(button)

    deadline = time.time() + 20
    while time.time() < deadline:
        time.sleep(1.0)
        root = dump_ui()
        status = node_text(node_by_id(root, RID_CONNECTION)).upper()
        if "CONNECTED" in status and "DISCONNECTED" not in status:
            log("Aplicatia s-a conectat la broker")
            return

    raise RuntimeError("Aplicatia nu a ajuns in starea CONNECTED.")


def start_subscriber(topic: str, artifacts_dir: Path) -> subprocess.Popen[str]:
    subscriber_log = artifacts_dir / "subscriber.log"
    log(f"Pornesc subscriber local pe topicul {topic}")
    proc = subprocess.Popen(
        [str(SUB), "--url", "mqtt://mqttuser:mqttpass@127.0.0.1:18883", "-t", topic, "-q", "1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
        env={
            **dict(os.environ),
            "PYTHONUNBUFFERED": "1",
        },
    )
    time.sleep(1.0)
    thread = threading.Thread(
        target=stream_log_output,
        args=(proc, subscriber_log, "[MQTT]"),
        daemon=True,
    )
    thread.start()
    return proc


def stream_log_output(proc: subprocess.Popen[str], log_path: Path, prefix: str) -> None:
    if proc.stdout is None:
        return
    with log_path.open("w", encoding="utf-8") as log_file:
        for line in proc.stdout:
            log_file.write(line)
            log_file.flush()
            clean = line.strip()
            if clean:
                print(f"{prefix} {clean}", flush=True)


def broker_publish(topic: str, payload: str) -> None:
    log(f"Broker -> Telefon: {payload}")
    result = run(
        [str(PUB), "--url", "mqtt://mqttuser:mqttpass@127.0.0.1:18883", "-t", topic, "-m", payload, "-q", "1"],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Publish catre broker a esuat pentru payload {payload}.")


def tap_app_publish_button(resource_id: str, label: str) -> None:
    scroll_to_commands()
    root = dump_ui()
    button = node_by_id(root, resource_id)
    if button is None or not node_enabled(button):
        raise RuntimeError(f"Butonul {label} nu este disponibil in UI.")
    log(f"Telefon -> Broker: {label}")
    tap_node(button)
    time.sleep(1.0)


def run_broker_step(topic: str, payload: str, *, context: str | None = None) -> None:
    if context:
        log(context)
    broker_publish(topic, payload)
    time.sleep(SEQUENCE_SETTLE_SECONDS)
    log_app_snapshot(f"Dupa {payload} din broker")


def run_phone_step(payload: str, *, context: str | None = None) -> None:
    if context:
        log(context)
    button_map = {
        PAYLOAD_ARM: RID_PUBLISH_ON,
        PAYLOAD_DISARM: RID_PUBLISH_OFF,
    }
    tap_app_publish_button(button_map[payload], payload)
    log_app_snapshot(f"Dupa {payload} din telefon")


def run_broker_sequence(topic: str, sequence: list[str]) -> None:
    if not sequence:
        log("Secventa broker este dezactivata.")
        return

    log(f"Secventa broker configurata: {' -> '.join(sequence)}")
    for index, payload in enumerate(sequence, start=1):
        run_broker_step(topic, payload, context=f"Pas broker {index}/{len(sequence)}")


def run_phone_sequence(sequence: list[str]) -> None:
    if not sequence:
        log("Secventa telefon este dezactivata.")
        return

    log(f"Secventa telefon configurata: {' -> '.join(sequence)}")
    for index, payload in enumerate(sequence, start=1):
        run_phone_step(payload, context=f"Pas telefon {index}/{len(sequence)}")


def build_auto_cycle(
    broker_sequence: list[str],
    phone_sequence: list[str],
) -> list[tuple[str, str]]:
    cycle: list[tuple[str, str]] = []
    max_items = max(len(broker_sequence), len(phone_sequence))
    for index in range(max_items):
        if index < len(broker_sequence):
            cycle.append(("broker", broker_sequence[index]))
        if index < len(phone_sequence):
            cycle.append(("telefon", phone_sequence[index]))
    return cycle


def install_signal_handlers() -> dict[int, object]:
    previous_handlers: dict[int, object] = {}

    def handle_signal(signum: int, _frame) -> None:
        signal_name = signal.Signals(signum).name
        raise DemoTermination(signal_name)

    for handled_signal in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        previous_handlers[handled_signal] = signal.getsignal(handled_signal)
        signal.signal(handled_signal, handle_signal)

    return previous_handlers


def restore_signal_handlers(previous_handlers: dict[int, object]) -> None:
    for handled_signal, previous_handler in previous_handlers.items():
        signal.signal(handled_signal, previous_handler)


def wait_until_ctrl_c(
    initial_message: str,
    *,
    heartbeat_message: str = "Demo in curs. Apasa Ctrl+C cand vrei sa opresti.",
) -> None:
    log(initial_message)
    log("Listen mode: ACTIV | auto-publish: OPRIT | subscriber/logcat: ACTIVE")
    next_heartbeat = time.time() + AUTO_DEMO_HEARTBEAT_SECONDS

    while True:
        time.sleep(1.0)
        now = time.time()
        if now >= next_heartbeat:
            log(heartbeat_message)
            next_heartbeat = now + AUTO_DEMO_HEARTBEAT_SECONDS


def run_continuous_demo_loop(
    topic: str,
    broker_sequence: list[str],
    phone_sequence: list[str],
) -> None:
    cycle = build_auto_cycle(broker_sequence, phone_sequence)
    if not cycle:
        wait_until_ctrl_c("Nu exista pasi automati configurati. Conexiunea si logurile raman active pana la Ctrl+C.")
        return

    cycle_labels = " -> ".join(f"{source}:{payload}" for source, payload in cycle)
    log(
        "Faza demo porneste acum. Scriptul va genera trafic MQTT in ambele sensuri "
        "pana cand opresti manual cu Ctrl+C."
    )
    log(f"Ciclu automat configurat: {cycle_labels}")

    next_heartbeat = time.time() + AUTO_DEMO_HEARTBEAT_SECONDS
    step_count = 0

    while True:
        for source, payload in cycle:
            step_count += 1
            if source == "broker":
                run_broker_step(
                    topic,
                    payload,
                    context=f"Auto-demo pas {step_count} | broker -> telefon | payload={payload}",
                )
            else:
                run_phone_step(
                    payload,
                    context=f"Auto-demo pas {step_count} | telefon -> broker | payload={payload}",
                )

            now = time.time()
            if now >= next_heartbeat:
                log("Auto-demo in curs. Apasa Ctrl+C cand vrei sa opresti.")
                next_heartbeat = now + AUTO_DEMO_HEARTBEAT_SECONDS


def run_random_broker_demo_then_listen(
    topic: str,
    payloads: list[str],
    *,
    duration_seconds: int,
    min_interval_seconds: int,
    max_interval_seconds: int,
) -> dict[str, object]:
    if not payloads:
        wait_until_ctrl_c(
            "Faza automata este dezactivata. Conexiunea ramane activa si poti trimite manual din telefon.",
            heartbeat_message="Mod listen-only activ. Trimite din telefon; opreste demo-ul cu Ctrl+C.",
        )
        return {
            "auto_demo_total_sent": 0,
            "auto_demo_counts": {},
        }

    if duration_seconds <= 0:
        wait_until_ctrl_c(
            "Durata fazei automate este 0 secunde. Conexiunea ramane activa si poti trimite manual din telefon.",
            heartbeat_message="Mod listen-only activ. Trimite din telefon; opreste demo-ul cu Ctrl+C.",
        )
        return {
            "auto_demo_total_sent": 0,
            "auto_demo_counts": {payload: 0 for payload in payloads},
        }

    counts = {payload: 0 for payload in payloads}
    end_time = time.time() + duration_seconds
    step_count = 0
    next_heartbeat = time.time() + AUTO_DEMO_HEARTBEAT_SECONDS

    log(
        "Faza automata incepe acum: brokerul va trimite payload-uri random catre telefon "
        f"timp de {duration_seconds}s, la intervale random de {min_interval_seconds}-{max_interval_seconds}s."
    )
    log(f"Payload-uri random permise: {', '.join(payloads)}")

    while time.time() < end_time:
        payload = random.choice(payloads)
        step_count += 1
        seconds_left = max(0, int(end_time - time.time()))
        log(
            f"Random demo pas {step_count} | broker -> telefon | payload={payload} | "
            f"timp ramas ~{seconds_left}s"
        )
        broker_publish(topic, payload)
        counts[payload] += 1

        remaining = end_time - time.time()
        if remaining <= 0:
            break

        pause_seconds = min(float(random.randint(min_interval_seconds, max_interval_seconds)), remaining)
        if pause_seconds <= 0:
            break
        pause_deadline = time.time() + pause_seconds
        while time.time() < pause_deadline:
            time.sleep(min(0.5, pause_deadline - time.time()))
            now = time.time()
            if now >= next_heartbeat:
                log(
                    f"Faza random este in curs. S-au trimis {step_count} comenzi pana acum; "
                    f"mai sunt aproximativ {max(0, int(end_time - now))}s."
                )
                next_heartbeat = now + AUTO_DEMO_HEARTBEAT_SECONDS

    log(
        "Faza automata s-a terminat. "
        f"Total comenzi trimise: {step_count} | "
        + " | ".join(f"{payload}={counts[payload]}" for payload in payloads)
    )
    log_app_snapshot("Dupa faza random broker -> telefon")
    result = {
        "auto_demo_total_sent": step_count,
        "auto_demo_counts": counts,
        "auto_demo_finished_at": dt.datetime.now().isoformat(timespec="seconds"),
        "listen_mode_entered": True,
    }
    wait_until_ctrl_c(
        (
            "Faza random s-a incheiat. Demo-ul a trecut in LISTEN MODE. "
            "Nu se mai trimit comenzi automate din broker."
        ),
        heartbeat_message=(
            "LISTEN MODE activ. Trimite manual din telefon sau din broker; "
            "subscriberul si logcat-ul continua sa asculte pana la Ctrl+C."
        ),
    )
    return result


def ui_snapshot() -> dict[str, str]:
    scroll_to_top()
    root = dump_ui()
    return {
        "connection_status": node_text(node_by_id(root, RID_CONNECTION)),
        "last_message": node_text(node_by_id(root, RID_LAST_MESSAGE)).replace("\n", " | "),
        "log_tail": " || ".join(
            line
            for line in node_text(node_by_id(root, RID_LOG)).splitlines()[-3:]
            if line.strip()
        ),
    }


def log_app_snapshot(context: str) -> None:
    snapshot = ui_snapshot()
    last_message = snapshot.get("last_message", "")
    log_tail = snapshot.get("log_tail", "")
    if last_message:
        log(f"{context} | App last_message: {last_message}")
    if log_tail:
        log(f"{context} | App log tail: {log_tail}")


def write_summary(path: Path, summary: dict[str, object]) -> None:
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_log_tail(path: Path, lines: int = 20) -> list[str]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:]


def capture_runtime_summary(summary: dict[str, object], artifacts_dir: Path) -> None:
    try:
        summary.update(ui_snapshot())
    except Exception as exc:
        summary["ui_snapshot_error"] = str(exc)

    try:
        summary["subscriber_tail"] = read_log_tail(artifacts_dir / "subscriber.log", lines=12)
    except Exception as exc:
        summary["subscriber_tail_error"] = str(exc)

    try:
        summary["app_logcat_tail"] = read_log_tail(artifacts_dir / "app_logcat.log", lines=12)
    except Exception as exc:
        summary["app_logcat_tail_error"] = str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo ADB pentru Voice Alarm MQTT")
    parser.add_argument("--skip-build", action="store_true", help="Nu recompila APK-ul")
    parser.add_argument("--skip-install", action="store_true", help="Nu reinstala APK-ul pe telefon")
    parser.add_argument("--host", default="127.0.0.1", help="Host MQTT care se completeaza in aplicatie")
    parser.add_argument("--port", default=str(BROKER_PORT), help="Port MQTT")
    parser.add_argument("--username", default="mqttuser", help="Username MQTT")
    parser.add_argument("--password", default="mqttpass", help="Password MQTT")
    parser.add_argument("--topic", default="control_status_relay", help="Topic MQTT folosit in demo")
    parser.add_argument(
        "--mode",
        choices=(MODE_RANDOM_BROKER_THEN_LISTEN, MODE_CONTINUOUS_BIDIRECTIONAL),
        default=MODE_RANDOM_BROKER_THEN_LISTEN,
        help=(
            "Modul demo. Implicit: brokerul trimite random ARMEAZA/DEZARMEAZA timp de 60s, "
            "apoi ramane doar in listen mode pentru comenzile tale din telefon."
        ),
    )
    parser.add_argument(
        "--random-payloads",
        default=DEFAULT_RANDOM_PAYLOADS,
        help=(
            "Payload-uri permise pentru faza random broker -> telefon. "
            "Lista separata prin virgule; accepta ARMEAZA/DEZARMEAZA sau aliasuri ARM/DISARM/ON/OFF."
        ),
    )
    parser.add_argument(
        "--random-duration",
        type=int,
        default=DEFAULT_RANDOM_DEMO_DURATION_SECONDS,
        help="Durata, in secunde, a fazei automate random broker -> telefon.",
    )
    parser.add_argument(
        "--random-min-interval",
        type=int,
        default=DEFAULT_RANDOM_MIN_INTERVAL_SECONDS,
        help="Pauza minima, in secunde, intre doua publish-uri random din broker.",
    )
    parser.add_argument(
        "--random-max-interval",
        type=int,
        default=DEFAULT_RANDOM_MAX_INTERVAL_SECONDS,
        help="Pauza maxima, in secunde, intre doua publish-uri random din broker.",
    )
    parser.add_argument(
        "--broker-sequence",
        default=DEFAULT_BROKER_SEQUENCE,
        help=(
            "Lista separata prin virgule pentru pasii broker -> telefon. "
            "Accepta ARMEAZA/DEZARMEAZA sau aliasuri ARM/DISARM/ON/OFF. "
            "Gol pentru skip."
        ),
    )
    parser.add_argument(
        "--phone-sequence",
        default=DEFAULT_PHONE_SEQUENCE,
        help=(
            "Lista separata prin virgule pentru pasii telefon -> broker. "
            "Accepta ARMEAZA/DEZARMEAZA sau aliasuri ARM/DISARM/ON/OFF. "
            "Implicit trimite aceeasi pereche ca brokerul. Gol pentru skip."
        ),
    )
    args = parser.parse_args()

    if args.random_duration < 0:
        parser.error("--random-duration trebuie sa fie >= 0")
    if args.random_min_interval < 1:
        parser.error("--random-min-interval trebuie sa fie >= 1")
    if args.random_max_interval < args.random_min_interval:
        parser.error("--random-max-interval trebuie sa fie >= --random-min-interval")

    broker_sequence = parse_sequence(args.broker_sequence, "--broker-sequence")
    phone_sequence = parse_sequence(args.phone_sequence, "--phone-sequence")
    random_payloads = parse_sequence(args.random_payloads, "--random-payloads")

    run_id = dt.datetime.now().strftime("run_%Y%m%d_%H%M%S")
    artifacts_dir = ROOT_DIR / "demo" / "artifacts" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    for required in (ADB, BUILD_SCRIPT, BROKER_SCRIPT, PUB, SUB):
        if not required.exists():
            raise FileNotFoundError(f"Lipseste fisierul necesar: {required}")

    broker_proc: subprocess.Popen[str] | None = None
    subscriber_proc: subprocess.Popen[str] | None = None
    logcat_proc: subprocess.Popen[str] | None = None
    broker_started = False
    adb_reverse_enabled = False
    summary: dict[str, object] = {
        "run_id": run_id,
        "artifacts_dir": str(artifacts_dir),
        "host": args.host,
        "port": args.port,
        "topic": args.topic,
        "mode": args.mode,
        "random_payloads": random_payloads,
        "random_duration_seconds": args.random_duration,
        "random_interval_seconds": [args.random_min_interval, args.random_max_interval],
        "broker_sequence": broker_sequence,
        "phone_sequence": phone_sequence,
    }
    exit_code = 0
    previous_signal_handlers = install_signal_handlers()

    try:
        device_id = ensure_device()
        summary["adb_device"] = device_id
        log(f"Telefon detectat prin ADB: {device_id}")
        setup_adb_reverse()
        adb_reverse_enabled = True

        broker_proc, broker_started = start_broker(artifacts_dir)
        summary["broker_started_by_script"] = broker_started

        if not args.skip_build:
            build_apk()

        if not args.skip_install:
            install_apk()

        launch_app()
        logcat_proc = start_logcat_stream(artifacts_dir)
        configure_app(args.host, args.port, args.username, args.password, args.topic)
        connect_app()

        subscriber_proc = start_subscriber(args.topic, artifacts_dir)

        if args.mode == MODE_CONTINUOUS_BIDIRECTIONAL:
            log(
                "Secventa demo porneste acum. Scriptul va genera trafic MQTT in ambele sensuri "
                "pana cand opresti manual cu Ctrl+C."
            )
            run_continuous_demo_loop(args.topic, broker_sequence, phone_sequence)
        else:
            summary.update(
                run_random_broker_demo_then_listen(
                    args.topic,
                    random_payloads,
                    duration_seconds=args.random_duration,
                    min_interval_seconds=args.random_min_interval,
                    max_interval_seconds=args.random_max_interval,
                )
            )
    except DemoTermination as exc:
        summary["stop_signal"] = exc.signal_name
        summary["stopped_at"] = dt.datetime.now().isoformat(timespec="seconds")
        if exc.signal_name == "SIGINT":
            exit_code = 0
        else:
            log(f"Demo oprit controlat de semnalul {exc.signal_name}")
            exit_code = 128 + int(signal.Signals[exc.signal_name])
    except KeyboardInterrupt:
        summary["stop_signal"] = "KEYBOARD_INTERRUPT"
        summary["stopped_at"] = dt.datetime.now().isoformat(timespec="seconds")
        exit_code = 0
    except Exception as exc:
        summary["error"] = str(exc)
        summary["error_at"] = dt.datetime.now().isoformat(timespec="seconds")
        log(f"Eroare demo: {exc}")
        exit_code = 1
    finally:
        capture_runtime_summary(summary, artifacts_dir)
        write_summary(artifacts_dir / "summary.json", summary)
        stop_process(subscriber_proc, "subscriber", announce=False)
        stop_process(logcat_proc, "logcat", announce=False)
        if should_stop_app_on_exit(summary):
            stop_app()
        else:
            stop_voice_loop(announce=False)
        if adb_reverse_enabled:
            remove_adb_reverse()
        if broker_started:
            stop_process(broker_proc, "broker", announce=False)
        restore_signal_handlers(previous_signal_handlers)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
