from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from contextlib import suppress
from typing import Any

import paho.mqtt.client as mqtt

MessageCallback = Callable[[mqtt.Client, Any, mqtt.MQTTMessage], None]
DisconnectCallback = Callable[[int], None]


def _reason_code_to_int(reason_code: Any) -> int:
    if hasattr(reason_code, "value"):
        try:
            return int(reason_code.value)
        except (TypeError, ValueError):
            return -1
    try:
        return int(reason_code)
    except (TypeError, ValueError):
        return -1


class ManagedPahoClient:
    def __init__(
        self,
        *,
        client_id: str,
        host: str,
        port: int,
        username: str,
        password: str,
        keepalive: int = 30,
        subscribe_topics: Sequence[tuple[str, int]] | None = None,
        on_message: MessageCallback | None = None,
        on_disconnect: DisconnectCallback | None = None,
    ) -> None:
        self.client_id = client_id
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.keepalive = keepalive
        self.subscribe_topics = list(subscribe_topics or [])
        self.on_message_callback = on_message
        self.on_disconnect_callback = on_disconnect

        self._client: mqtt.Client | None = None
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._last_connect_rc: int | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def last_connect_rc(self) -> int | None:
        return self._last_connect_rc

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        rc = _reason_code_to_int(reason_code)
        self._last_connect_rc = rc
        if rc != 0:
            return
        if self.subscribe_topics:
            for topic, qos in self.subscribe_topics:
                client.subscribe(topic, qos=qos)
        self._connected.set()

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, disconnect_flags: Any, reason_code: Any, properties: Any = None) -> None:
        self._connected.clear()
        rc = _reason_code_to_int(reason_code)
        if self.on_disconnect_callback is not None:
            self.on_disconnect_callback(rc)

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        if self.on_message_callback is not None:
            self.on_message_callback(client, userdata, msg)

    def start(self, timeout_seconds: float = 8.0) -> None:
        with self._lock:
            if self._client is not None:
                return

            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=self.client_id,
                protocol=mqtt.MQTTv311,
            )

            if self.username:
                client.username_pw_set(self.username, self.password)

            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message

            rc = client.connect(self.host, self.port, self.keepalive)
            if rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"connect() failed for {self.client_id} with rc={rc}")

            client.loop_start()
            self._client = client

        if not self._connected.wait(timeout=timeout_seconds):
            self.stop()
            raise TimeoutError(
                f"MQTT client '{self.client_id}' did not connect in {timeout_seconds:.1f}s "
                f"(last_rc={self._last_connect_rc})"
            )

    def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = False, wait_timeout_seconds: float = 5.0) -> None:
        client = self._client
        if client is None or not self._connected.is_set():
            raise RuntimeError(f"MQTT client '{self.client_id}' is not connected")

        info = client.publish(topic, payload=payload, qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Publish failed for '{self.client_id}' rc={info.rc}")

        # Ensure publication lifecycle reached completion (QoS-aware)
        with suppress(Exception):
            info.wait_for_publish(timeout=wait_timeout_seconds)

    def stop(self) -> None:
        with self._lock:
            client = self._client
            self._client = None

        if client is None:
            return

        with suppress(Exception):
            client.disconnect()
        with suppress(Exception):
            client.loop_stop()
        self._connected.clear()
