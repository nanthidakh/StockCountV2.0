"""
=========================================================
Project : HWK_StockV1
File    : services/config_service.py

Download Application Configuration
=========================================================
"""

import requests


class ConfigServiceError(Exception):
    """
    Error สำหรับ Config Service
    """
    pass


class ConfigService:

    REQUIRED_KEYS = [
        "download_url",
        "sync_url",
        "login_url",
        "sync_batch",
        "timeout",
    ]

    # =====================================================
    # Download Config
    # =====================================================

    def download_config(
        self,
        server_ip: str,
    ) -> dict:

        server_ip = str(
            server_ip or ""
        ).strip()

        if not server_ip:
            raise ConfigServiceError(
                "กรุณาระบุ Server IP"
            )

        # รองรับ:
        # 192.168.10.21
        # http://192.168.10.21
        # https://192.168.10.21
        if not server_ip.lower().startswith(
            ("http://", "https://")
        ):
            server_ip = (
                "http://" +
                server_ip
            )

        url = (
            server_ip.rstrip("/")
            +
            "/CountStock/GetAppConfig.ashx"
        )

        try:
            response = requests.get(
                url,
                timeout=(
                    10,
                    30,
                ),
            )

            response.raise_for_status()

        except requests.exceptions.ConnectionError as exc:
            raise ConfigServiceError(
                "ไม่สามารถเชื่อมต่อ Server ได้"
            ) from exc

        except requests.exceptions.Timeout as exc:
            raise ConfigServiceError(
                "เชื่อมต่อ Server เกินเวลาที่กำหนด"
            ) from exc

        except requests.exceptions.HTTPError as exc:
            status_code = getattr(
                response,
                "status_code",
                0,
            )

            raise ConfigServiceError(
                f"Server ตอบกลับ HTTP {status_code}"
            ) from exc

        except requests.exceptions.RequestException as exc:
            raise ConfigServiceError(
                f"เกิดข้อผิดพลาดในการเชื่อมต่อ: {exc}"
            ) from exc

        # =================================================
        # Parse JSON
        # =================================================

        try:
            data = response.json()

        except ValueError as exc:
            response_text = str(
                response.text or ""
            ).strip()

            if len(response_text) > 500:
                response_text = (
                    response_text[:500] +
                    "..."
                )

            raise ConfigServiceError(
                "Server ไม่ได้ส่ง Config JSON ที่ถูกต้อง\n"
                f"URL: {url}\n"
                f"Response: {response_text}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise ConfigServiceError(
                "รูปแบบ Config จาก Server ไม่ถูกต้อง"
            )

        if not data.get(
            "success",
            False,
        ):
            message = str(
                data.get(
                    "message",
                    "Server ส่ง Config ไม่สำเร็จ",
                )
            ).strip()

            raise ConfigServiceError(
                message
            )

        # =================================================
        # Validate Required Keys
        # =================================================

        for key in self.REQUIRED_KEYS:
            if key not in data:
                raise ConfigServiceError(
                    f"ไม่พบ Config '{key}'"
                )

        download_url = str(
            data.get(
                "download_url",
                "",
            ) or ""
        ).strip()

        sync_url = str(
            data.get(
                "sync_url",
                "",
            ) or ""
        ).strip()

        login_url = str(
            data.get(
                "login_url",
                "",
            ) or ""
        ).strip()

        if not download_url:
            raise ConfigServiceError(
                "download_url ว่าง"
            )

        if not sync_url:
            raise ConfigServiceError(
                "sync_url ว่าง"
            )

        if not login_url:
            raise ConfigServiceError(
                "login_url ว่าง"
            )

        try:
            sync_batch = int(
                data.get(
                    "sync_batch",
                    500,
                )
            )

            timeout = int(
                data.get(
                    "timeout",
                    120,
                )
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ConfigServiceError(
                "sync_batch หรือ timeout ไม่ใช่ตัวเลข"
            ) from exc

        if sync_batch <= 0:
            raise ConfigServiceError(
                "sync_batch ต้องมากกว่า 0"
            )

        if timeout <= 0:
            raise ConfigServiceError(
                "timeout ต้องมากกว่า 0"
            )

        # =================================================
        # Normalize Config
        # =================================================

        return {
            "success": True,
            "download_url": download_url.rstrip("/"),
            "sync_url": sync_url.rstrip("/"),
            "login_url": login_url.rstrip("/"),
            "sync_batch": sync_batch,
            "timeout": timeout,
            "config_url": url,
        }