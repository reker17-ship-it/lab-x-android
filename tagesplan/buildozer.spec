[app]
title = Tagesplan
package.name = tagesplan
package.domain = de.tagesplan.local
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0.0
requirements = python3,kivy,pyjnius
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png
android.permissions = android.permission.SET_ALARM,android.permission.READ_CALENDAR,android.permission.WRITE_CALENDAR
android.api = 35
android.minapi = 26
android.ndk_api = 26
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.debug_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1
