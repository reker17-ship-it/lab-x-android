#!/usr/bin/env bash
set -euo pipefail

apk=$1
package=org.reker17.labx
runtime_log="$RUNNER_TEMP/labx-runtime.log"

adb shell getprop ro.product.cpu.abilist
adb install "$apk"
adb logcat -c
adb shell am start -W -n "$package/org.kivy.android.PythonActivity"

for _ in {1..24}; do
    adb logcat -d -s python AndroidRuntime > "$runtime_log"
    if grep -qE 'FATAL EXCEPTION|Traceback \(most recent call last\)' "$runtime_log"; then
        break
    fi
    if grep -q 'Start application main loop' "$runtime_log" && adb shell pidof "$package"; then
        echo 'LAB X started successfully.'
        exit 0
    fi
    sleep 5
done

cat "$runtime_log"
exit 1
