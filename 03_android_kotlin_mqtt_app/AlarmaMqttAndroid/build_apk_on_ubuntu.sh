#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLCHAIN_BASE="/home/ctone/Downloads/Personale_tz/Alarma_Mqtt/03_android_kotlin_mqtt_app/.toolchain"
JDK_HOME="$TOOLCHAIN_BASE/jdk/current"
SDK_ROOT="$TOOLCHAIN_BASE/android-sdk"

if [[ ! -x "$JDK_HOME/bin/java" ]]; then
  echo "Missing local JDK at $JDK_HOME"
  exit 1
fi

if [[ ! -x "$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" ]]; then
  echo "Missing Android SDK cmdline tools at $SDK_ROOT"
  exit 1
fi

export JAVA_HOME="$JDK_HOME"
export ANDROID_SDK_ROOT="$SDK_ROOT"
export PATH="$JAVA_HOME/bin:$PATH"

cat > "$PROJECT_DIR/local.properties" <<EOL
sdk.dir=$SDK_ROOT
EOL

cd "$PROJECT_DIR"
./gradlew assembleDebug

APK_PATH="$PROJECT_DIR/app/build/outputs/apk/debug/app-debug.apk"
if [[ -f "$APK_PATH" ]]; then
  echo "APK_READY=$APK_PATH"
else
  echo "APK_NOT_FOUND"
  exit 2
fi
