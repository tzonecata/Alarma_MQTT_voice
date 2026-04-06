# HA Assist + MQTT - Integrare Comenzi Vocale

Integrare rapida intre **Home Assistant Assist (comenzi vocale)** si **aplicatia Android Kotlin** prin **MQTT**.

## Fluxul de integrare

### 1️⃣ Vorbești în telefon → HA Assist → Android App

```
🎤 Vorbești în telefon (ex: "Aprinde lumina")
  ↓
HA Assist (în app Home Assistant)
  ↓
Automation în Home Assistant
  ↓
MQTT publish către brokerul tău Ubuntu
  ↓
Aplicația ta Android primește mesajul (`control_status_relay` topic)
  ↓
Execută acțiune (ON/OFF for relay)
```

### 2️⃣ Apasă buton în Android → Control HomeAssistant

```
📱 Apasă buton în aplicația Android
  ↓
MQTT publish către brokerul tău Ubuntu
  ↓
Home Assistant primește mesajul
  ↓
Automation în Home Assistant
  ↓
HA Assist răspunde vocal în telefon (Home Assistant app)
```

---

## Pași de setup rapid

### Pasul 1: Configurare Home Assistant

#### 1.1 Conectare la MQTT broker-ul tău Ubuntu

**Home Assistant → Settings → Devices & Services → MQTT**

```yaml
# configuration.yaml (sau UI integrations)
mqtt:
  broker: 192.168.1.50  # IP-ul Ubuntu din Wi-Fi
  port: 18883
  username: mqttuser
  password: mqttpass
```

Sau prin interfața Web:
1. `Settings` → `Devices & Services`
2. `Create Automation` → `MQTT` broker
3. Host: `192.168.1.50`
4. Port: `18883`
5. Username/Password: `mqttuser` / `mqttpass`

#### 1.2 Instalare HA Assist (dacă nu e instalat)

**Home Assistant → Settings → Voice Assistants**

- Selectează `Create voice assistant`
- Alege `Home Assistant Cloud` sau `Whisper` (local)
- Configurează limba: Română (RO)

---

### Pasul 2: Automation de la HA Assist la Android App (via MQTT)

Cria o automatizare care sa publica pe topic-ul aplicatiei Android cand Assist primeste o comanda.

**Home Assistant → Automations → Create Automation**

Opțiunea 1: Prin YAML (mai simplu):

```yaml
alias: HA Assist → Android MQTT Publish
description: "Publish HA Assist commands to Android via MQTT"

trigger:
  platform: template
  value_template: "{{ state_attr('conversation.home_assistant', 'last_entity_generated') }}"

condition:
  condition: template
  value_template: "{{ 'light' in states | selectattr('entity_id', 'match', 'light.*') | list or 'switch' in states }}"

action:
  - service: mqtt.publish
    data:
      topic: control_status_relay
      payload: "{{ 'ON' if 'aprinde' in trigger.value.lower() or 'on' in trigger.value.lower() else 'OFF' }}"
      qos: 1
      retain: false
```

Opțiunea 2: Prin interfața vizuală:

1. `Settings → Automations`
2. `Create Automation`
3. **Trigger:** "Template" → custom rule cu `conversation.home_assistant`
4. **Action:** `MQTT: Publish a message`
   - Topic: `control_status_relay`
   - Payload: `{{ 'ON' if 'aprinde' in trigger.value.lower() else 'OFF' }}`

---

### Pasul 3: Automation de la Android App la HA Assist (MQTT → Voice Response)

Cria o automatizare care asculta mesajele MQTT de la Android si raspunde vocal.

```yaml
alias: Android MQTT → HA Assist Voice Response
description: "Listen for Android MQTT messages and respond with HA Assist"

trigger:
  platform: mqtt
  topic: control_status_relay

condition: []

action:
  - service: notify.mobile_app_[PHONE_NAME]  # Înlocuiește cu numele telefonului
    data:
      title: "Control"
      message: "{{ trigger.payload }} button pressed from app"
      data:
        tag: "mqtt_response"

  - service: conversation.process
    data:
      text: "{{ 'Lumina a fost aprinsă' if trigger.payload == 'ON' else 'Lumina a fost stinsă' }}"
      agent_id: conversation.home_assistant
      language: ro
```

---

### Pasul 4: Configurare Aplicație Android

Aplicația trebuie sa fie configurata sa se conecteze la brokerul MQTT de pe Ubuntu.

**În aplicația AlarmaMqttAndroid:**

1. Deschide app
2. **Settings / Config:**
   - **Host:** `192.168.1.50` (IP-ul Ubuntu din Wi-Fi)
   - **Port:** `18883`
   - **Username:** `mqttuser`
   - **Password:** `mqttpass`
   - **Topic:** `control_status_relay`

3. Apasa `Connect`

Status trebuie sa devina **CONNECTED**.

---

### Pasul 5: Test rapid

#### Test 1: HA Assist → Android

1. Deschide **Home Assistant app** pe telefon
2. Apasa **Home Assistant button** (microfon pentru Assist)
3. Spune: **"Aprinde lumina"** (sau "ON")
4. In aplicația **AlarmaMqttAndroid** ar trebui sa vede mesajul **ON** in log
5. Apasa **Publish ON** sa confirmezi ca merge si invers

#### Test 2: Android → HA Assist

1. In aplicația **AlarmaMqttAndroid**, apasa **Publish ON**
2. Home Assistant ar trebui sa primeasca mesajul pe topic `control_status_relay`
3. Automation-ul trigger si HA Assist ar trebui sa raspunda vocal (in lang RO)
4. Verifica **Home Assistant app** → notification ca s-a primit comanda

---

## Verificare conexiunile

### Verifica MQTT broker-ul

```bash
# Pe Ubuntu, verifica ca broker-ul asculta pe port 18883
ss -tlnp | grep 18883

# Output asteptat:
# LISTEN 0 5 0.0.0.0:18883 0.0.0.0:* ... mosquitto
```

### Verifica Android conectat

```bash
# In Android app, status trebuie CONNECTED si topic trebuie SUBSCRIBED
# In log ar trebui sa vada: "Subscribed to: control_status_relay"
```

### Verifica Home Assistant - MQTT connection

**Home Assistant → Settings → Devices & Services → MQTT**

Status trebuie sa arate: **Connected to broker at 192.168.1.50:18883**

### Monitor mesajele MQTT live

```bash
# Pe Ubuntu, vede live toate mesajele pe topicul Android
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/amqtt_sub \
  --url "mqtt://mqttuser:mqttpass@127.0.0.1:18883" \
  -t control_status_relay -q 1

# Ar trebui sa veda:
# control_status_relay: ON
# control_status_relay: OFF
```

---

## Troubleshooting

### Android nu se conecteaza

1. **Firewall:** `sudo ufw allow 18883/tcp`
2. **Host IP:** Asigura-te ca folosesti IP-ul real Ubuntu (`ip -4 a`), nu `127.0.0.1`
3. **Broker running:** `ps aux | grep mosquitto` sa confirmi ca e pornit
4. **Credentials:** Username `mqttuser` / Password `mqttpass` trebuie sa fie corecte

### HA Assist nu raspunde

1. Verifica ca Voice Assistant e configurat in Home Assistant
2. Verifica ca MQTT integration e connected
3. Restarta Home Assistant: `Settings → System → Restart`
4. Verifica logs in Home Assistant: `Settings → Logs`

### Mesajele MQTT nu ajung in Android

1. Verifica topic-ul: trebuie **exact** `control_status_relay`
2. Verifica ca Android e **SUBSCRIBED** (log-ul ar trebui sa arate subscription)
3. Publishes test din terminal: `amqtt_pub`

```bash
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/amqtt_pub \
  --url "mqtt://mqttuser:mqttpass@127.0.0.1:18883" \
  -t control_status_relay -m "ON" -q 1
```

---

## Referințe

- **MQTT Broker Setup:** [02_ha_container_mosquitto_native/README.md](../02_ha_container_mosquitto_native/README.md)
- **Android App Setup:** [03_android_kotlin_mqtt_app/AlarmaMqttAndroid/README.md](../03_android_kotlin_mqtt_app/AlarmaMqttAndroid/README.md)
- **Testing & Validation:** [06_testing_validation_runbook/README.md](../06_testing_validation_runbook/README.md)
- **Home Assistant Assist Docs:** [https://www.home-assistant.io/voice_control/](https://www.home-assistant.io/voice_control/)
- **Home Assistant MQTT Docs:** [https://www.home-assistant.io/integrations/mqtt/](https://www.home-assistant.io/integrations/mqtt/)

---

## Comenzi rapide

```bash
# Start MQTT broker pe Ubuntu (port 18883)
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma start

# Demo live 5 minute (build + install + broker + test)
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/demo_live_5m.sh

# Monitor MQTT messages live
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/amqtt_sub \
  --url "mqtt://mqttuser:mqttpass@127.0.0.1:18883" \
  -t control_status_relay -q 1
```

---

## Notes

- **Limba:** Asigura-te ca HA Assist e configurat pentru limba **Română (RO)**
- **Local vs Cloud:** Poti folosi Whisper (local) sau HA Cloud Speech pentru recognition
- **Security:** In productie, schimba username/password si nu deschide broker-ul pe internet
- **Topic consistency:** Topic-ul trebuie sa fie **identic** in Android app si in automation-uri
