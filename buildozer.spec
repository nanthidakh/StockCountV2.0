[app]

# ---------------------------------------------------------
# Application identity
# ---------------------------------------------------------
title = HWK Stock Count
package.name = hwkstock
package.domain = com.hwking
version = 2.0.0

# ---------------------------------------------------------
# Source files
# ---------------------------------------------------------
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,json,txt,ini,xml
source.exclude_dirs = .git,.github,.idea,.vscode,__pycache__,bin,.buildozer,logs,IIS,New folder
source.exclude_patterns = */__pycache__/*,*.pyc,*.pyo,*.log,*~,*.bak

# Existing icon from the CountStock project.
# The file must exist at the project root before building.
icon.filename = %(source.dir)s/barcode.png

# ---------------------------------------------------------
# Python / Kivy dependencies
# Keep the known working p4a toolchain.
# requests installs urllib3, certifi, idna and charset-normalizer.
# ---------------------------------------------------------
requirements = python3,kivy,kivymd,requests,pyjnius,materialyoucolor
p4a.branch = release-2024.01.21

# ---------------------------------------------------------
# Android toolchain
# These values are retained from the CountStock build that
# previously completed successfully.
# ---------------------------------------------------------
android.api = 28
android.minapi = 23
android.ndk = 25b
android.accept_sdk_license = True
android.archs = armeabi-v7a

# ---------------------------------------------------------
# Android application behavior
# ---------------------------------------------------------
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# Keep application data when installing a newer APK with the
# same package name and signing key.
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
