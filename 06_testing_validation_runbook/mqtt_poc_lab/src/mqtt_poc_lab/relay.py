from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt

from .models import normalize_state
from .mqtt_client import ManagedPahoClient


@dataclass(slots=True)
class RelayMetrics:
    received_messages: int = 0
    state_changes: int = 0
    duplicate_messages: int = 0
    invalid_payloads: int = 0


class RelayState:
    def __init__(self, initial_state: str = "OFF") -> None:
        normalized = normalize_state(initial_state) or "OFF"
        self._state = normalized
        self._last_update_epoch = time.time()
        self._lock = threading.Lock()

    def get_state(self) -> str:
        with self._lock:
            return self._state

    def set_state(self, new_state: str) -> bool:
        normalized = normalize_state(new_state)
        if normalized is None:
            return False

        with self._lock:
            changed = normalized != self._state
            self._state = normalized
            self._last_update_epoch = time.time()
            return changed

    def last_update_epoch(self) -> float:
        with self._lock:
            return self._last_update_epoch


class RelaySimulator:
    def __init__(
        self,
        *,
        broker_host: str,
        broker_port: int,
        username: str,
        password: str,
        topic: str,
        qos: int,
        state: RelayState,
    ) -> None:
        self.topic = topic
        self.qos = qos
        self.state = state
        self.metrics = RelayMetrics()
        self._lock = threading.Lock()

        self._client = ManagedPahoClient(
            client_id="relay-simulator",
            host=broker_host,
            port=broker_port,
            username=username,
            password=password,
            subscribe_topics=[(topic, qos)],
            on_message=self._on_message,
        )

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        payload = normalize_state(msg.payload)
        with self._lock:
            self.metrics.received_messages += 1

        if payload is None:
            with self._lock:
                self.metrics.invalid_payloads += 1
            return

        changed = self.state.set_state(payload)
        with self._lock:
            if changed:
                self.metrics.state_changes += 1
            else:
                self.metrics.duplicate_messages += 1

    def start(self) -> None:
        self._client.start()

    def stop(self) -> None:
        self._client.stop()

    def snapshot_metrics(self) -> RelayMetrics:
        with self._lock:
            return RelayMetrics(
                received_messages=self.metrics.received_messages,
                state_changes=self.metrics.state_changes,
                duplicate_messages=self.metrics.duplicate_messages,
                invalid_payloads=self.metrics.invalid_payloads,
            )
