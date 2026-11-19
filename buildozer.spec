[app]
title = Ali STT
package.name = alistt
package.domain = org.rahimi
source.dir = .
source.include_exts = py
version = 1.0
source.exclude_dirs = .github,bin,.buildozer
requirements = python3,kivy==2.3.0,requests,urllib3,idna,charset-normalizer,certifi,plyer,pyjnius,android,arabic-reshaper,python-bidi==0.4.2,future
orientation = portrait
fullscreen = 0
android.permissions = RECORD_AUDIO,INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_AUDIO,READ_MEDIA_VIDEO
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.enable_androidx = True

[buildozer]
log_level = 2
warn_on_root = 1
