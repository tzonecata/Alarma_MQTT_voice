# MQTT POC Lab (functional, local, long-run)

Acest proiect oferă un POC MQTT complet rulabil local, fără Docker și fără sudo:
- broker MQTT local (AMQTT) cu autentificare user/parolă,
- simulator relay care consumă comenzi `ON/OFF` de pe topicul `control_status_relay`,
- publisher de status periodic (default: la 10 secunde),
- load generator pentru comenzi ON/OFF,
- monitor + metrici + summary JSON pentru smoke/soak test.

## 1) Quick start

```bash
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/scripts/bootstrap.sh
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/scripts/run_smoke.sh
```

După rulare, rezultatele apar în:
`/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/artifacts/run_<timestamp>/summary.json`.

## 2) Rulare manuală

```bash
source /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/activate
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/mqtt-lab run \
  --duration-seconds 300 \
  --status-interval 10 \
  --cmd-min-interval 20 \
  --cmd-max-interval 45
```

## 3) Soak test pe ore

4 ore:

```bash
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/scripts/run_soak_4h.sh
```

Sau custom:

```bash
source /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/activate
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/mqtt-lab soak --hours 8
```

## 4) Optional: deployment cu Docker (Mosquitto + Home Assistant)

```bash
cat /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/deploy/README.md
```

## 5) Ce validează proiectul

- Flux ON/OFF pe topic unic `control_status_relay`.
- Publicare de status periodică, independentă de comenzi.
- Livrare QoS 1 pentru comenzi/status.
- Stabilitate pe durate lungi (soak), cu metrici:
  - mesaje așteptate vs mesaje observate,
  - gap maxim între mesaje,
  - latență comanda->observare,
  - payload invalid,
  - convergență stare finală.

## 6) Comenzi CLI

```bash
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/mqtt-lab smoke
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/mqtt-lab run --help
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/mqtt-lab soak --help
```

## 7) Structura proiectului (path complet)

- `/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/src/mqtt_poc_lab/` codul principal
- `/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/scripts/` bootstrap + run scripts
- `/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/deploy/` stack opțional Docker pentru Mosquitto + Home Assistant
- `/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/docs/DEEP_ANALYSIS.md` analiză arhitecturală extinsă
- `/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/docs/TEST_PLAN.md` plan de test și criterii de acceptare
- `/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/artifacts/` output automat al rularilor

## 8) Observații

- Port default broker: `18883` (ca să evităm conflict cu `1883` dacă ai broker sistem).
- Dacă vrei port `1883`, rulează cu `--broker-port 1883`.
- Topicul implicit este exact cel cerut: `control_status_relay`.
