from __future__ import annotations

import asyncio
import random
import time

from .models import CommandEvent, normalize_state
from .mqtt_client import ManagedPahoClient


async def wait_or_stop(stop_event: asyncio.Event, timeout: float) -> bool:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
        return True
    except TimeoutError:
        return False


class LoadGenerator:
    def __init__(
        self,
        *,
        broker_host: str,
        broker_port: int,
        username: str,
        password: str,
        topic: str,
        qos: int,
        min_interval_seconds: float,
        max_interval_seconds: float,
        initial_state: str,
        seed: int | None,
    ) -> None:
        self.topic = topic
        self.qos = qos
        self.min_interval_seconds = min_interval_seconds
        self.max_interval_seconds = max_interval_seconds

        normalized_initial = normalize_state(initial_state) or "OFF"
        self._last_command = normalized_initial

        self._rnd = random.Random(seed)
        self.commands: list[CommandEvent] = []

        self._client = ManagedPahoClient(
            client_id="load-generator",
            host=broker_host,
            port=broker_port,
            username=username,
            password=password,
        )

    def _next_state(self) -> str:
        return "ON" if self._last_command == "OFF" else "OFF"

    def start(self) -> None:
        self._client.start()

    def stop(self) -> None:
        self._client.stop()

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            payload = self._next_state()
            mono = time.monotonic()
            epoch = time.time()
            await asyncio.to_thread(
                self._client.publish,
                self.topic,
                payload,
                self.qos,
                False,
            )
            self.commands.append(CommandEvent(monotonic_ts=mono, epoch_ts=epoch, payload=payload))
            self._last_command = payload

            delay = self._rnd.uniform(self.min_interval_seconds, self.max_interval_seconds)
            if await wait_or_stop(stop_event, delay):
                break
