# Optional Docker Deployment

Aceste fișiere sunt pentru medii unde ai Docker/Compose.
Pe mașina curentă POC-ul a fost validat fără Docker folosind:
`/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/mqtt-lab`.

## 1) Pregătește parola pentru Mosquitto

```bash
cd /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/deploy/mosquitto/config
# necesită utilitarul mosquitto_passwd instalat local
mosquitto_passwd -c passwd mqttuser
```

## 2) Pornește stack-ul

```bash
cd /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/deploy/docker
docker compose up -d
```

## 3) Integrare cu lab-ul Python

Rulează lab-ul către brokerul Docker:

```bash
source /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/activate
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/mqtt-lab run --broker-port 1883 --duration-seconds 300
```
