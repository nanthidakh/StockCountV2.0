"""
=========================================================
Project : HWK_StockV1
File    : utils/device.py

Device Information
=========================================================
"""

import socket
from kivy.utils import platform


def get_device_name():
    """คืนชื่อเครื่องสำหรับแสดงผลและบันทึก Checker

    Windows ใช้ Computer Name
    Android ใช้ Model/Device Name
    Device ID สำหรับ Sync ยังคงเก็บแยกเป็น UUID ใน SQLite
    """
    try:
        if platform == "android":
            from jnius import autoclass

            Build = autoclass("android.os.Build")

            for value in (
                getattr(Build, "MODEL", None),
                getattr(Build, "DEVICE", None),
                getattr(Build, "PRODUCT", None),
            ):
                text = str(value or "").strip()
                if text:
                    return text

            return "ANDROID_DEVICE"

        name = str(socket.gethostname() or "").strip()
        return name or "UNKNOWN_DEVICE"

    except Exception:
        return "ANDROID_UNKNOWN" if platform == "android" else "UNKNOWN_DEVICE"
