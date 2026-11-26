[app]
title = LAB X
package.name = labx
package.domain = org.reker17
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,wav
icon.filename = %(source.dir)s/icon.png
version = 4.1
# Use a pure-Python release so p4a cannot bundle the build host's native wheel.
requirements = python3==3.11.14,hostpython3==3.11.14,kivy,pyjnius,plyer,numpy,openssl,chardet==6.0.0.post1
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,ACCESS_COARSE_LOCATION,ACCESS_FINE_LOCATION,RECORD_AUDIO,ACTIVITY_RECOGNITION,BODY_SENSORS
android.api = 35
android.minapi = 24
android.ndk_api = 24
android.ndk = 28c
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.release_artifact = apk
p4a.branch = v2026.05.09
p4a.source_dir =

[buildozer]
log_level = 2
warn_on_root = 1
