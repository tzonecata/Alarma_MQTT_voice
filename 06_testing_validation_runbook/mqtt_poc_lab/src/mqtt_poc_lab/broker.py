from __future__ import annotations

from pathlib import Path

from amqtt.broker import Broker
from passlib.apps import custom_app_context as pwd_context


class LocalBroker:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_auth: bool,
        runtime_dir: Path,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_auth = use_auth
        self.runtime_dir = runtime_dir

        self._broker: Broker | None = None
        self._password_file = runtime_dir / "broker_passwd.txt"

    def _write_password_file(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        hashed = pwd_context.hash(self.password)
        self._password_file.write_text(f"{self.username}:{hashed}\n", encoding="utf-8")

    def _build_config(self) -> dict:
        plugins: dict[str, dict] = {
            "amqtt.plugins.sys.broker.BrokerSysPlugin": {"sys_interval": 60},
        }

        if self.use_auth:
            self._write_password_file()
            plugins["amqtt.plugins.authentication.AnonymousAuthPlugin"] = {
                "allow_anonymous": False,
            }
            plugins["amqtt.plugins.authentication.FileAuthPlugin"] = {
                "password_file": str(self._password_file),
            }
        else:
            plugins["amqtt.plugins.authentication.AnonymousAuthPlugin"] = {
                "allow_anonymous": True,
            }

        return {
            "listeners": {
                "default": {
                    "type": "tcp",
                    "bind": f"{self.host}:{self.port}",
                }
            },
            "plugins": plugins,
        }

    async def start(self) -> None:
        if self._broker is not None:
            return
        config = self._build_config()
        broker = Broker(config)
        try:
            await broker.start()
        except OSError as exc:
            if "Address already in use" in str(exc):
                raise RuntimeError(f"Broker port {self.port} is already in use") from exc
            raise
        self._broker = broker

    async def stop(self) -> None:
        if self._broker is None:
            return
        await self._broker.shutdown()
        self._broker = None
