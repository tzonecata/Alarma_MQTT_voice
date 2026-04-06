from __future__ import annotations

import asyncio
import time

from .mqtt_client import ManagedPahoClient
from .relay import RelayState


async def wait_or_stop(stop_event: asyncio.Event, timeout: float) -> bool:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
        return True
    except TimeoutError:
        return False


class StatusPublisher:
    def __init__(
        self,
        *,
        broker_host: str,
        broker_port: int,
        username: str,
        password: str,
        topic: str,
        qos: int,
        interval_seconds: float,
        relay_state: RelayState,
    ) -> None:
        self.topic = topic
        self.qos = qos
        self.interval_seconds = interval_seconds
        self.relay_state = relay_state

        self.messages_sent = 0
        self.last_publish_epoch: float | None = None

        self._client = ManagedPahoClient(
            client_id="status-publisher",
            host=broker_host,
            port=broker_port,
            username=username,
            password=password,
        )

    def start(self) -> None:
        self._client.start()

    def stop(self) -> None:
        self._client.stop()

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            payload = self.relay_state.get_state()
            await asyncio.to_thread(
                self._client.publish,
                self.topic,
                payload,
                self.qos,
                False,
            )
            self.messages_sent += 1
            self.last_publish_epoch = time.time()
            if await wait_or_stop(stop_event, self.interval_seconds):
                break
