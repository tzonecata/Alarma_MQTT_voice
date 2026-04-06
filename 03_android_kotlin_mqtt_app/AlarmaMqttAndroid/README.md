# AlarmaMqttAndroid

Aplicatie Android Kotlin pentru test MQTT cu brokerul de pe Ubuntu in aceeasi retea Wi-Fi.

## 0) Build app in Android Studio

1. Deschide Android Studio.
2. `Open` -> selecteaza folderul:
   `/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid`
3. Asteapta `Gradle Sync`.
4. Ruleaza pe telefon (USB debugging activ).

Sau din terminal (toolchain-ul a fost instalat local deja):

```bash
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/build_apk_on_ubuntu.sh
```

APK rezultat:

`/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/app/build/outputs/apk/debug/app-debug.apk`

## 1) Ce trebuie sa ruleze pe Ubuntu

In terminal pe Ubuntu:

```bash
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/start_wifi_broker.sh
```

Scriptul porneste acum brokerul in background, fara sa stea blocat in terminal.
Oprire / status / loguri:

```bash
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/start_wifi_broker.sh stop
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/start_wifi_broker.sh status
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/start_wifi_broker.sh logs
```

Important:
- afla IP-ul Ubuntu in Wi-Fi: `ip -4 a`
- foloseste acel IP in telefon (de ex. `192.168.1.50`)
- nu folosi `127.0.0.1` pe telefon
- daca ai firewall activ: `sudo ufw allow 18883/tcp`

## 2) Config in aplicatie

- Host: IP-ul Ubuntu (ex. `192.168.1.50`)
- Port: `18883`
- Username: `mqttuser`
- Password: `mqttpass`
- Topic: `control_status_relay`

## 3) Test rapid

1. Apasa `Connect`.
2. Daca status devine `CONNECTED`, apasa `Publish ON` si `Publish OFF`.
3. In log vei vedea TX/RX, iar `Last message` se actualizeaza.

## 4) Notite

- Aplicatia foloseste `Eclipse Paho MQTT Java Client` (`MqttAsyncClient`), fara Android Service.
- Subscribe pe topicul configurat se face automat la conectare.
- Setarile de conexiune se salveaza local in SharedPreferences.

## COMENZI

Comenzile de mai jos sunt scrise pentru setup-ul tau actual (Ubuntu + telefon prin ADB) si pot fi rulate din orice director.

```bash
# Build APK debug (foloseste toolchain local instalat in .toolchain)
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/build_apk_on_ubuntu.sh

# Porneste tot pentru demo rapid:
# - porneste brokerul MQTT local
# - instaleaza APK pe telefon
# - lanseaza aplicatia
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma run

# Porneste doar brokerul MQTT local (port 18883)
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma start

# Alternativ, direct prin scriptul brokerului (tot in background)
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/start_wifi_broker.sh

# Opreste brokerul MQTT local
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma stop

# Opreste brokerul direct prin script
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/start_wifi_broker.sh stop

# Verifica starea curenta:
# - IP Ubuntu
# - status broker
# - device ADB conectat
# - path APK
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma status

# Instaleaza APK-ul curent pe telefon (fara launch)
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma install

# Lanseaza aplicatia pe telefon
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma launch

# Urmareste live logul brokerului MQTT
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma logs

# Status / loguri direct prin scriptul brokerului
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/start_wifi_broker.sh status
bash /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/start_wifi_broker.sh logs

# Meniu interactiv cu optiuni (run/start/stop/status/etc.)
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma menu

# Porneste testul de anduranta (soak) pentru mobil, implicit in ore
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma soak-start 12

# Vezi statusul testului de anduranta + ultimele linii din log
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma soak-status

# Opreste testul de anduranta
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/alarma soak-stop

# DEMO LIVE 5 minute (build + update app + broker + ON/OFF random + loguri live in tab-uri)
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/demo_live_5m.sh

# Opreste demo-ul curent (inchide stream-urile + opreste brokerul)
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/demo_live_5m.sh --stop

# Daca nu se deschid ferestrele terminal (ex: eroare gnome-terminal.real / GLIBC),
# ruleaza demo in mod headless (toate stream-urile merg in fisiere .log)
DEMO_HEADLESS=1 /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/AlarmaMqttAndroid/demo_live_5m.sh

# Vezi toate logurile headless live
tail -n +1 -f /tmp/alarma_demo_*/01_BOOTSTRAP_BUILD_INSTALL.log \
  /tmp/alarma_demo_*/02_BROKER_LOG_LIVE.log \
  /tmp/alarma_demo_*/03_MQTT_SUBSCRIBER_LIVE.log \
  /tmp/alarma_demo_*/04_RANDOM_ON_OFF_PUBLISHER_5M.log \
  /tmp/alarma_demo_*/05_ANDROID_LOGCAT_MQTT.log \
  /tmp/alarma_demo_*/06_SYSTEM_STATUS_WATCH.log
```

### Comenzi alias (fara path lung)

```bash
# Incarca alias-urile in sesiunea curenta (sau deschide terminal nou)
source ~/.bash_aliases

# Echivalent pentru "run all" (start broker + install apk + launch)
alarma

# Aliasuri scurte existente
a
am
f_apk

# Alias DEMO live 5 minute
DEMO
```

### Mesaje MQTT live (subscriber in terminal)

```bash
# Vezi live doar topicul principal al aplicatiei
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/amqtt_sub \
  --url "mqtt://mqttuser:mqttpass@127.0.0.1:18883" \
  -t control_status_relay -q 1

# Vezi live toate topicurile din broker
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/06_testing_validation_runbook/mqtt_poc_lab/.venv/bin/amqtt_sub \
  --url "mqtt://mqttuser:mqttpass@127.0.0.1:18883" \
  -t "#"
```

### Loguri live de pe mobil (ADB)

```bash
# Loguri aplicatie filtrate pe tag-ul MQTT din app
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/.toolchain/android-sdk/platform-tools/adb \
  logcat -v time -s AlarmaMqtt

# Cauta erori critice in logul de soak curent
rg -n "FATAL EXCEPTION|AndroidRuntime|connect failed|MQTT connect exception" \
  /home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/soak_mobile_logs/run_*/adb_logcat.txt
```

### Unde gasesc logurile

```bash
# Logul runtime pentru soak (scris de serviciul systemd user)
/tmp/alarma_mobile_soak.log

# Rulari istorice de soak (fiecare run are propriul folder)
/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/soak_mobile_logs/
```
=============
Integrare rapida cu Home Assistant (HA Assist + MQTT)  de comenzi vocale:
🎤 Vorbești în telefon
→ HA Assist (în aplicație)
→ Automation în Home Assistant
→ MQTT publish către brokerul tău Ubuntu
→ aplicația ta Android primește mesajul
Și invers:
📱 Apasă buton în aplicația Android
→ MQTT publish către brokerul tău Ubuntu
→ Automation în Home Assistant
→ HA Assist răspunde vocal în tele_fon
Astfel, poți controla și monitoriza dispozitivele tale smart prin comenzi vocale sau prin interfața aplicației Android, toate integrate prin MQTT și Home Assistant!

creaza folder 07_HA_Voice_commands in Personale_tz/Alarma_Mqtt/ si adauga acolo un README.md cu pasii de integrare rapida MQTT + Home Assistant Assist pentru comenzi vocale.
