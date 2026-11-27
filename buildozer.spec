[app]
title = LAB X
package.name = labx
package.domain = org.reker17
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,wav
version = 5.0
requirements = python3==3.11.14,hostpython3==3.11.14,kivy,pyjnius,plyer,numpy,openssl
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,ACCESS_COARSE_LOCATION,ACCESS_FINE_LOCATION,RECORD_AUDIO,ACTIVITY_RECOGNITION
android.api = 35
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
