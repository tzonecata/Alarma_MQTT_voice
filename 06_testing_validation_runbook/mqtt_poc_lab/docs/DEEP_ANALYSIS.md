# Deep Analysis - MQTT POC Lab

## Objective

Construirea unui setup end-to-end, testabil local, care să simuleze cât mai aproape fluxul real:
- Android/Client trimite comenzi `ON/OFF`.
- Sistemul relay consumă acele comenzi.
- Sistemul publică status recurent la interval fix (default 10s).
- Monitorizarea produce dovezi cantitative pentru stabilitate pe termen lung.

## Architectural decisions

1. Broker embedded local (`amqtt`)
- Avantaj: nu depinde de Docker sau sudo.
- Avantaj: setup reproductibil pe mașina curentă.
- Risc: performanță mai mică decât Mosquitto la scale mari.
- Mitigare: POC/soak controlat; pentru producție se migrează pe Mosquitto.

2. Clienți MQTT cu `paho-mqtt`
- Avantaj: client mainstream, bun benchmark pentru integrare.
- Avantaj: model callback robust pentru publish/subscribe.
- Risc: concurență thread-based.
- Mitigare: locking explicit și separare clară a stării partajate.

3. Topic unic `control_status_relay`
- Aliniat cu cerința explicită din raport.
- Tradeoff: nu separă semantic comanda de status.
- Mitigare: monitorul verifică regularitatea statusului și convergența stării.

4. Orchestrare într-un singur proces
- Avantaj: rulare simplă, scriptabilă, deterministă.
- Risc: nu reprezintă fully distributed deployment.
- Mitigare: componentele sunt separate logic și pot fi mutate ulterior în procese distincte.

## Data flow

1. Load Generator publică `ON/OFF` la interval random controlat.
2. Relay Simulator este subscribed pe același topic și actualizează starea internă.
3. Status Publisher publică periodic starea internă pe același topic.
4. Monitor observă toate mesajele și calculează metrici de calitate.
5. Orchestrator decide PASS/FAIL și persistă artefacte.

## Reliability model

- QoS default: `1`.
- Retry de transport este delegat la paho/broker.
- Criterii de sănătate:
  - fără payload invalid,
  - gap maxim dintre mesaje sub prag,
  - observabilitate consistentă între mesaje expected/observed,
  - stare finală convergentă.

## Metrics emitted

- `commands_sent`
- `status_messages_sent`
- `messages_observed_total`
- `messages_observed_on`
- `messages_observed_off`
- `invalid_payloads`
- `max_gap_seconds`
- `avg_gap_seconds`
- `command_delivery_ratio`
- `command_latency_ms_{avg,p95,max}`
- `final_state_match` (bool)

## Long-run strategy (hours)

Pentru rulări de 4-12 ore:
- status la 10 sec,
- comandă la 20-60 sec,
- artefacte JSON per run,
- seed fix pentru reproductibilitate dacă e nevoie.

Se recomandă:
- 1x smoke (2-5 min),
- 1x soak 4h,
- 1x soak 8h (după eventuale tunări).

## Migration path to production

1. Broker: AMQTT -> Mosquitto.
2. Control plane: topic unic -> topic separat command/status (opțional).
3. Security:
- TLS (1883 -> 8883),
- certificate pinning pe client.
4. Networking:
- VPN overlay (Tailscale/WireGuard) pentru mediu CGNAT.
5. Android:
- aceeași semantică de topic + QoS,
- reconnection policy + foreground constraints.

## Failure modes considered

- Broker startup failure (port ocupat): detectat explicit.
- Auth mismatch: detectat la connect timeout.
- Publisher alive dar relay blocat: final_state mismatch.
- Message starvation: max_gap_seconds depășit.
- Payload corupt: invalid_payloads > 0.

## What this project does not cover

- Integrare UI Android reală în acest repo (necesită Android SDK/Studio).
- TLS PKI completă (cert CA/client), doar extensie recomandată.
- Distribuție pe host-uri separate; proiectul actual e local-lab.
