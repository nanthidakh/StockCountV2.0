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
    """
    คืนชื่อเครื่องสำหรับแสดงผลและบันทึก Checker

    Windows:
        Computer Name

    Android:
        1. System Device Name
        2. MODEL
        3. DEVICE
        4. PRODUCT

    Device ID สำหรับ Sync ยังคงแยกเป็น UUID
    """

    try:
        if platform == "android":
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            SettingsGlobal = autoclass(
                "android.provider.Settings$Global"
            )

            Build = autoclass(
                "android.os.Build"
            )

            # ==========================================
            # 1. Android Device Name
            # ==========================================
            try:
                activity = PythonActivity.mActivity

                resolver = activity.getContentResolver()

                device_name = SettingsGlobal.getString(
                    resolver,
                    "device_name"
                )

                text = str(
                    device_name or ""
                ).strip()

                if text:
                    return text

            except Exception:
                pass

            # ==========================================
            # 2. Fallback เป็น Model
            # ==========================================
            for value in (
                getattr(Build, "MODEL", None),
                getattr(Build, "DEVICE", None),
                getattr(Build, "PRODUCT", None),
            ):
                text = str(
                    value or ""
                ).strip()

                if text:
                    return text

            return "ANDROID_DEVICE"

        # ==============================================
        # Windows
        # ==============================================
        name = str(
            socket.gethostname() or ""
        ).strip()

        return name or "UNKNOWN_DEVICE"

    except Exception:
        return (
            "ANDROID_UNKNOWN"
            if platform == "android"
            else "UNKNOWN_DEVICE"
        )