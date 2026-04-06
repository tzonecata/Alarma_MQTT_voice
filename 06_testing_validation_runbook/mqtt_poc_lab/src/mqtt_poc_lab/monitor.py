from __future__ import annotations

import csv
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

import paho.mqtt.client as mqtt

from .models import CommandEvent, ObservedMessage, normalize_state
from .mqtt_client import ManagedPahoClient


@dataclass(slots=True)
class MonitorMetrics:
    observed_total: int
    observed_on: int
    observed_off: int
    invalid_payloads: int
    max_gap_seconds: float
    avg_gap_seconds: float
    command_delivery_ratio: float
    command_latency_avg_ms: float
    command_latency_p95_ms: float
    command_latency_max_ms: float
    last_observed_payload: str | None


class TopicMonitor:
    def __init__(
        self,
        *,
        broker_host: str,
        broker_port: int,
        username: str,
        password: str,
        topic: str,
        qos: int,
    ) -> None:
        self.topic = topic
        self.qos = qos
        self._messages: list[ObservedMessage] = []
        self._lock = threading.Lock()

        self._client = ManagedPahoClient(
            client_id="topic-monitor",
            host=broker_host,
            port=broker_port,
            username=username,
            password=password,
            subscribe_topics=[(topic, qos)],
            on_message=self._on_message,
        )

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        payload = msg.payload.decode("utf-8", errors="replace")
        state = normalize_state(payload)

        record = ObservedMessage(
            monotonic_ts=time.monotonic(),
            epoch_ts=time.time(),
            topic=msg.topic,
            payload=payload.strip().upper(),
            qos=int(msg.qos),
            retained=bool(msg.retain),
            valid_state=state is not None,
        )

        with self._lock:
            self._messages.append(record)

    def start(self) -> None:
        self._client.start()

    def stop(self) -> None:
        self._client.stop()

    def snapshot_messages(self) -> list[ObservedMessage]:
        with self._lock:
            return list(self._messages)

    def export_messages_csv(self, path: Path) -> None:
        rows = self.snapshot_messages()
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["epoch_ts", "monotonic_ts", "topic", "payload", "qos", "retained", "valid_state"])
            for row in rows:
                writer.writerow([
                    f"{row.epoch_ts:.6f}",
                    f"{row.monotonic_ts:.6f}",
                    row.topic,
                    row.payload,
                    row.qos,
                    int(row.retained),
                    int(row.valid_state),
                ])

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return values[0]
        data = sorted(values)
        rank = (len(data) - 1) * pct
        lower = int(rank)
        upper = min(lower + 1, len(data) - 1)
        weight = rank - lower
        return data[lower] * (1 - weight) + data[upper] * weight

    def compute_metrics(self, commands: list[CommandEvent]) -> MonitorMetrics:
        messages = self.snapshot_messages()

        observed_total = len(messages)
        observed_on = 0
        observed_off = 0
        invalid = 0

        for m in messages:
            state = normalize_state(m.payload)
            if state == "ON":
                observed_on += 1
            elif state == "OFF":
                observed_off += 1
            else:
                invalid += 1

        gaps: list[float] = []
        if len(messages) >= 2:
            prev = messages[0].monotonic_ts
            for m in messages[1:]:
                gaps.append(max(0.0, m.monotonic_ts - prev))
                prev = m.monotonic_ts

        max_gap = max(gaps) if gaps else 0.0
        avg_gap = fmean(gaps) if gaps else 0.0

        latencies_ms: list[float] = []
        if commands and messages:
            for cmd in commands:
                for msg in messages:
                    if msg.monotonic_ts >= cmd.monotonic_ts and msg.payload == cmd.payload:
                        latencies_ms.append((msg.monotonic_ts - cmd.monotonic_ts) * 1000.0)
                        break

        delivery_ratio = (len(latencies_ms) / len(commands)) if commands else 1.0
        latency_avg = fmean(latencies_ms) if latencies_ms else 0.0
        latency_p95 = self._percentile(latencies_ms, 0.95) if latencies_ms else 0.0
        latency_max = max(latencies_ms) if latencies_ms else 0.0

        last_payload = messages[-1].payload if messages else None

        return MonitorMetrics(
            observed_total=observed_total,
            observed_on=observed_on,
            observed_off=observed_off,
            invalid_payloads=invalid,
            max_gap_seconds=max_gap,
            avg_gap_seconds=avg_gap,
            command_delivery_ratio=delivery_ratio,
            command_latency_avg_ms=latency_avg,
            command_latency_p95_ms=latency_p95,
            command_latency_max_ms=latency_max,
            last_observed_payload=last_payload,
        )
