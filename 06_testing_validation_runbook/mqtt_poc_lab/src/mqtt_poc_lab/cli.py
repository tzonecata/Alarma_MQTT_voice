from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .config import deep_get, load_yaml_file
from .models import LabConfig
from .orchestrator import run_lab


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=Path("config/default.yaml"), help="Path to YAML defaults")

    parser.add_argument("--broker-host", type=str, default=None)
    parser.add_argument("--broker-port", type=int, default=None)
    parser.add_argument("--username", type=str, default=None)
    parser.add_argument("--password", type=str, default=None)
    parser.add_argument("--no-auth", action="store_true", help="Disable broker authentication")

    parser.add_argument("--topic", type=str, default=None)
    parser.add_argument("--qos", type=int, default=None)
    parser.add_argument("--initial-state", type=str, default=None)

    parser.add_argument("--status-interval", type=float, default=None)
    parser.add_argument("--cmd-min-interval", type=float, default=None)
    parser.add_argument("--cmd-max-interval", type=float, default=None)

    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))

    parser.add_argument("--min-observation-ratio", type=float, default=0.95)
    parser.add_argument("--min-command-delivery-ratio", type=float, default=0.98)
    parser.add_argument("--max-gap-factor", type=float, default=2.2)
    parser.add_argument("--max-invalid-payloads", type=int, default=0)


def _pick(cli_value, cfg: dict, key: str, fallback):
    if cli_value is not None:
        return cli_value
    return deep_get(cfg, key, fallback)


def _build_lab_config(args: argparse.Namespace, mode: str) -> LabConfig:
    cfg = load_yaml_file(args.config)

    if mode == "run":
        duration = _pick(args.duration_seconds, cfg, "test.duration_seconds", 300.0)
    elif mode == "smoke":
        duration = args.duration_seconds
    elif mode == "soak":
        duration = float(args.hours) * 3600.0
    else:
        raise ValueError(f"Unsupported mode {mode}")

    return LabConfig(
        broker_host=_pick(args.broker_host, cfg, "broker.host", "127.0.0.1"),
        broker_port=int(_pick(args.broker_port, cfg, "broker.port", 18883)),
        broker_username=_pick(args.username, cfg, "broker.username", "mqttuser"),
        broker_password=_pick(args.password, cfg, "broker.password", "mqttpass"),
        use_auth=not args.no_auth,
        topic=_pick(args.topic, cfg, "topic", "control_status_relay"),
        qos=int(_pick(args.qos, cfg, "test.qos", 1)),
        initial_state=_pick(args.initial_state, cfg, "relay.initial_state", "OFF"),
        duration_seconds=float(duration),
        status_interval_seconds=float(
            _pick(args.status_interval, cfg, "status_publisher.interval_seconds", 10.0)
        ),
        command_min_interval_seconds=float(
            _pick(args.cmd_min_interval, cfg, "load_generator.min_interval_seconds", 20.0)
        ),
        command_max_interval_seconds=float(
            _pick(args.cmd_max_interval, cfg, "load_generator.max_interval_seconds", 45.0)
        ),
        seed=args.seed,
        artifacts_dir=args.artifacts_dir,
        min_observation_ratio=float(args.min_observation_ratio),
        min_command_delivery_ratio=float(args.min_command_delivery_ratio),
        max_gap_factor=float(args.max_gap_factor),
        max_invalid_payloads=int(args.max_invalid_payloads),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mqtt-lab",
        description="Functional MQTT relay/status lab with smoke + soak tests",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run with explicit duration")
    _add_common_args(run_parser)
    run_parser.add_argument("--duration-seconds", type=float, default=None)

    smoke_parser = subparsers.add_parser("smoke", help="Short validation run")
    _add_common_args(smoke_parser)
    smoke_parser.add_argument("--duration-seconds", type=float, default=120.0)
    smoke_parser.set_defaults(
        status_interval=5.0,
        cmd_min_interval=7.0,
        cmd_max_interval=14.0,
    )

    soak_parser = subparsers.add_parser("soak", help="Long run in hours")
    _add_common_args(soak_parser)
    soak_parser.add_argument("--hours", type=float, default=4.0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = _build_lab_config(args, args.command)

    try:
        summary = asyncio.run(run_lab(config))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: run failed: {exc}")
        return 2

    print(json.dumps(summary.to_dict(), indent=2))
    print(f"summary_file: {Path(summary.artifacts_dir) / 'summary.json'}")

    return 0 if summary.pass_verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
