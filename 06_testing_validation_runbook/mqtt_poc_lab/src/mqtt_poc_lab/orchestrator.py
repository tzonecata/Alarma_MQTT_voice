from __future__ import annotations

import asyncio
import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from .broker import LocalBroker
from .logging_utils import setup_logger
from .load_generator import LoadGenerator
from .models import LabConfig, RunSummary, normalize_state
from .monitor import TopicMonitor
from .relay import RelaySimulator, RelayState
from .status_publisher import StatusPublisher


def _run_label() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _write_commands_csv(commands: list, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["epoch_ts", "monotonic_ts", "payload"])
        for cmd in commands:
            writer.writerow([f"{cmd.epoch_ts:.6f}", f"{cmd.monotonic_ts:.6f}", cmd.payload])


def _evaluate_verdict(config: LabConfig, summary: RunSummary) -> tuple[bool, str]:
    reasons: list[str] = []

    if summary.observation_ratio < config.min_observation_ratio:
        reasons.append(
            f"observation_ratio {summary.observation_ratio:.3f} < {config.min_observation_ratio:.3f}"
        )
    if summary.command_delivery_ratio < config.min_command_delivery_ratio:
        reasons.append(
            f"command_delivery_ratio {summary.command_delivery_ratio:.3f} < {config.min_command_delivery_ratio:.3f}"
        )

    allowed_gap = config.status_interval_seconds * config.max_gap_factor
    if summary.max_gap_seconds > allowed_gap:
        reasons.append(f"max_gap_seconds {summary.max_gap_seconds:.3f} > {allowed_gap:.3f}")

    if summary.invalid_payloads > config.max_invalid_payloads:
        reasons.append(
            f"invalid_payloads {summary.invalid_payloads} > {config.max_invalid_payloads}"
        )

    if not summary.final_state_match:
        reasons.append("final_state_match is false")

    if reasons:
        return False, "; ".join(reasons)
    return True, "all acceptance checks passed"


async def run_lab(config: LabConfig) -> RunSummary:
    config.validate()

    run_started = time.time()
    run_dir = config.artifacts_dir / f"run_{_run_label()}"
    run_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(run_dir / "run.log")
    logger.info("Starting run in %s", run_dir)
    logger.info(
        "Broker=%s:%s topic=%s duration=%.1fs status_interval=%.1fs command_interval=[%.1f, %.1f]",
        config.broker_host,
        config.broker_port,
        config.topic,
        config.duration_seconds,
        config.status_interval_seconds,
        config.command_min_interval_seconds,
        config.command_max_interval_seconds,
    )

    broker = LocalBroker(
        host=config.broker_host,
        port=config.broker_port,
        username=config.broker_username,
        password=config.broker_password,
        use_auth=config.use_auth,
        runtime_dir=run_dir,
    )

    relay_state = RelayState(initial_state=config.initial_state)
    relay = RelaySimulator(
        broker_host=config.broker_host,
        broker_port=config.broker_port,
        username=config.broker_username,
        password=config.broker_password,
        topic=config.topic,
        qos=config.qos,
        state=relay_state,
    )

    status_publisher = StatusPublisher(
        broker_host=config.broker_host,
        broker_port=config.broker_port,
        username=config.broker_username,
        password=config.broker_password,
        topic=config.topic,
        qos=config.qos,
        interval_seconds=config.status_interval_seconds,
        relay_state=relay_state,
    )

    load_generator = LoadGenerator(
        broker_host=config.broker_host,
        broker_port=config.broker_port,
        username=config.broker_username,
        password=config.broker_password,
        topic=config.topic,
        qos=config.qos,
        min_interval_seconds=config.command_min_interval_seconds,
        max_interval_seconds=config.command_max_interval_seconds,
        initial_state=config.initial_state,
        seed=config.seed,
    )

    monitor = TopicMonitor(
        broker_host=config.broker_host,
        broker_port=config.broker_port,
        username=config.broker_username,
        password=config.broker_password,
        topic=config.topic,
        qos=config.qos,
    )

    stop_event = asyncio.Event()
    status_task: asyncio.Task | None = None
    load_task: asyncio.Task | None = None

    error: Exception | None = None

    try:
        await broker.start()
        await asyncio.sleep(config.startup_settle_seconds)

        await asyncio.gather(
            asyncio.to_thread(monitor.start),
            asyncio.to_thread(relay.start),
            asyncio.to_thread(status_publisher.start),
            asyncio.to_thread(load_generator.start),
        )

        status_task = asyncio.create_task(status_publisher.run(stop_event), name="status-publisher")
        load_task = asyncio.create_task(load_generator.run(stop_event), name="load-generator")

        await asyncio.sleep(config.duration_seconds)
    except Exception as exc:  # noqa: BLE001
        error = exc
        logger.exception("Run failed due to exception")
    finally:
        stop_event.set()

        if status_task is not None:
            await asyncio.gather(status_task, return_exceptions=True)
        if load_task is not None:
            await asyncio.gather(load_task, return_exceptions=True)

        await asyncio.sleep(config.stop_drain_seconds)

        # Stop clients before broker shutdown.
        await asyncio.gather(
            asyncio.to_thread(load_generator.stop),
            asyncio.to_thread(status_publisher.stop),
            asyncio.to_thread(relay.stop),
            asyncio.to_thread(monitor.stop),
            return_exceptions=True,
        )

        await broker.stop()

    run_finished = time.time()

    commands = load_generator.commands
    monitor_metrics = monitor.compute_metrics(commands)

    expected_total = len(commands) + status_publisher.messages_sent
    observed_total = monitor_metrics.observed_total
    observation_ratio = (observed_total / expected_total) if expected_total else 1.0

    relay_metrics = relay.snapshot_metrics()

    relay_final = relay_state.get_state()
    last_command = commands[-1].payload if commands else None
    last_observed = normalize_state(monitor_metrics.last_observed_payload)

    final_state_match = True
    if last_command is not None:
        final_state_match = relay_final == last_command
        if last_observed is not None:
            final_state_match = final_state_match and (last_observed == relay_final)

    provisional = RunSummary(
        pass_verdict=False,
        reason="pending evaluation",
        run_started_epoch=run_started,
        run_finished_epoch=run_finished,
        duration_seconds=max(0.0, run_finished - run_started),
        expected_messages_total=expected_total,
        observed_messages_total=observed_total,
        observation_ratio=observation_ratio,
        commands_sent=len(commands),
        status_messages_sent=status_publisher.messages_sent,
        command_delivery_ratio=monitor_metrics.command_delivery_ratio,
        messages_observed_on=monitor_metrics.observed_on,
        messages_observed_off=monitor_metrics.observed_off,
        invalid_payloads=monitor_metrics.invalid_payloads + relay_metrics.invalid_payloads,
        max_gap_seconds=monitor_metrics.max_gap_seconds,
        avg_gap_seconds=monitor_metrics.avg_gap_seconds,
        command_latency_avg_ms=monitor_metrics.command_latency_avg_ms,
        command_latency_p95_ms=monitor_metrics.command_latency_p95_ms,
        command_latency_max_ms=monitor_metrics.command_latency_max_ms,
        relay_final_state=relay_final,
        last_command_payload=last_command,
        last_observed_payload=monitor_metrics.last_observed_payload,
        final_state_match=final_state_match,
        artifacts_dir=str(run_dir),
    )

    pass_verdict, reason = _evaluate_verdict(config, provisional)
    if error is not None:
        pass_verdict = False
        reason = f"runtime exception: {error}"

    summary = RunSummary(
        pass_verdict=pass_verdict,
        reason=reason,
        run_started_epoch=provisional.run_started_epoch,
        run_finished_epoch=provisional.run_finished_epoch,
        duration_seconds=provisional.duration_seconds,
        expected_messages_total=provisional.expected_messages_total,
        observed_messages_total=provisional.observed_messages_total,
        observation_ratio=provisional.observation_ratio,
        commands_sent=provisional.commands_sent,
        status_messages_sent=provisional.status_messages_sent,
        command_delivery_ratio=provisional.command_delivery_ratio,
        messages_observed_on=provisional.messages_observed_on,
        messages_observed_off=provisional.messages_observed_off,
        invalid_payloads=provisional.invalid_payloads,
        max_gap_seconds=provisional.max_gap_seconds,
        avg_gap_seconds=provisional.avg_gap_seconds,
        command_latency_avg_ms=provisional.command_latency_avg_ms,
        command_latency_p95_ms=provisional.command_latency_p95_ms,
        command_latency_max_ms=provisional.command_latency_max_ms,
        relay_final_state=provisional.relay_final_state,
        last_command_payload=provisional.last_command_payload,
        last_observed_payload=provisional.last_observed_payload,
        final_state_match=provisional.final_state_match,
        artifacts_dir=provisional.artifacts_dir,
    )

    monitor.export_messages_csv(run_dir / "messages.csv")
    _write_commands_csv(commands, run_dir / "commands.csv")
    (run_dir / "summary.json").write_text(
        json.dumps(summary.to_dict(), indent=2),
        encoding="utf-8",
    )

    logger.info(
        "Run finished verdict=%s reason=%s observed=%d expected=%d",
        summary.pass_verdict,
        summary.reason,
        summary.observed_messages_total,
        summary.expected_messages_total,
    )

    return summary
