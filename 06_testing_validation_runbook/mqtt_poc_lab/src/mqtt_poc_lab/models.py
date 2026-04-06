from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

VALID_STATES = {"ON", "OFF"}


def normalize_state(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    elif isinstance(value, str):
        text = value
    elif isinstance(value, bool):
        return "ON" if value else "OFF"
    else:
        text = str(value)

    normalized = text.strip().upper()
    if normalized in {"TRUE", "1"}:
        return "ON"
    if normalized in {"FALSE", "0"}:
        return "OFF"
    if normalized in VALID_STATES:
        return normalized
    return None


@dataclass(slots=True)
class LabConfig:
    broker_host: str = "127.0.0.1"
    broker_port: int = 18883
    broker_username: str = "mqttuser"
    broker_password: str = "mqttpass"
    use_auth: bool = True

    topic: str = "control_status_relay"
    qos: int = 1
    initial_state: str = "OFF"

    duration_seconds: float = 300.0
    status_interval_seconds: float = 10.0
    command_min_interval_seconds: float = 20.0
    command_max_interval_seconds: float = 45.0

    seed: int | None = None
    artifacts_dir: Path = Path("artifacts")

    # verdict thresholds
    min_observation_ratio: float = 0.95
    min_command_delivery_ratio: float = 0.98
    max_gap_factor: float = 2.2
    max_invalid_payloads: int = 0

    # orchestration tuning
    startup_settle_seconds: float = 0.6
    stop_drain_seconds: float = 0.8

    def validate(self) -> None:
        if self.qos not in (0, 1, 2):
            raise ValueError("qos must be 0, 1, or 2")
        if self.broker_port <= 0 or self.broker_port > 65535:
            raise ValueError("broker_port must be in 1..65535")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be > 0")
        if self.status_interval_seconds <= 0:
            raise ValueError("status_interval_seconds must be > 0")
        if self.command_min_interval_seconds <= 0 or self.command_max_interval_seconds <= 0:
            raise ValueError("command intervals must be > 0")
        if self.command_min_interval_seconds > self.command_max_interval_seconds:
            raise ValueError("command_min_interval_seconds cannot be greater than command_max_interval_seconds")
        if normalize_state(self.initial_state) is None:
            raise ValueError("initial_state must be ON or OFF")
        if not self.topic:
            raise ValueError("topic must be non-empty")


@dataclass(slots=True)
class CommandEvent:
    monotonic_ts: float
    epoch_ts: float
    payload: str


@dataclass(slots=True)
class ObservedMessage:
    monotonic_ts: float
    epoch_ts: float
    topic: str
    payload: str
    qos: int
    retained: bool
    valid_state: bool


@dataclass(slots=True)
class RunSummary:
    pass_verdict: bool
    reason: str

    run_started_epoch: float
    run_finished_epoch: float
    duration_seconds: float

    expected_messages_total: int
    observed_messages_total: int
    observation_ratio: float

    commands_sent: int
    status_messages_sent: int
    command_delivery_ratio: float

    messages_observed_on: int
    messages_observed_off: int
    invalid_payloads: int

    max_gap_seconds: float
    avg_gap_seconds: float

    command_latency_avg_ms: float
    command_latency_p95_ms: float
    command_latency_max_ms: float

    relay_final_state: str
    last_command_payload: str | None
    last_observed_payload: str | None
    final_state_match: bool

    artifacts_dir: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
