# Test Plan

## Smoke

Durată: 90-180 sec

Scop:
- să valideze start/stop corect al stack-ului,
- să valideze publish/subscribe ON/OFF,
- să genereze summary cu PASS.

Comandă:

```bash
bash scripts/run_smoke.sh
```

## Soak

Durată: 4h (sau mai mult)

Scop:
- stabilitate pe termen lung,
- detectare leak-uri sau degradări,
- verificare consistență metrici.

Comandă:

```bash
bash scripts/run_soak_4h.sh
```

## Acceptance criteria

- `pass: true` în `summary.json`.
- `invalid_payloads == 0`.
- `command_delivery_ratio >= 0.98`.
- `max_gap_seconds <= status_interval * 2.2`.
- `final_state_match == true`.

## Artifacts

Per run se generează:
- `summary.json` (metrici + verdict),
- `messages.csv` (stream observat),
- `commands.csv` (comenzi emise).
