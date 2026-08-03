"""
=========================================================
Project : HWK_StockV1
File    : main.py

Application Entry Point
=========================================================
"""

from pathlib import Path

from kivy.core.text import LabelBase
from kivy.core.window import Window

from app import HWKStockApp

# กำหนดขนาดหน้าต่างเฉพาะตอนทดสอบบน Desktop เท่านั้น
# Android ต้องใช้ขนาดหน้าจอจริงของอุปกรณ์ เพื่อให้พิกัดภาพและ Touch ตรงกัน
if platform not in ("android", "ios"):
    Window.size = (
        380,
        680
    )

Window.softinput_mode = "below_target"

# Resolve the font from the project directory instead of the current
# working directory. This is required when the app is started from an IDE,
# a shortcut, or an Android package.
BASE_DIR = Path(__file__).resolve().parent
THAI_FONT_PATH = str(BASE_DIR / "fonts" / "Kanit-Regular.ttf")

if not Path(THAI_FONT_PATH).is_file():
    raise FileNotFoundError(
        f"Thai font file was not found: {THAI_FONT_PATH}"
    )

# Kivy/KivyMD widgets in the existing screens use both aliases.
LabelBase.register(
    name="ThaiFont",
    fn_regular=THAI_FONT_PATH
)
LabelBase.register(
    name="Roboto",
    fn_regular=THAI_FONT_PATH
)


if __name__ == "__main__":
    HWKStockApp().run()