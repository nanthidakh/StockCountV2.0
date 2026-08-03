"""Cross-platform notification tones for the CountStock module."""
from __future__ import annotations

from kivy.utils import platform

try:
    if platform == "win":
        import winsound  # type: ignore
    else:
        winsound = None
except Exception:
    winsound = None


def play_notification(success: bool = True) -> None:
    """Play the same short success/error tones used by CountStock V1.2."""
    if platform == "android":
        try:
            from jnius import autoclass

            ToneGenerator = autoclass("android.media.ToneGenerator")
            AudioManager = autoclass("android.media.AudioManager")
            tone = ToneGenerator(AudioManager.STREAM_MUSIC, 100)
            tone_type = (
                ToneGenerator.TONE_PROP_BEEP
                if success
                else ToneGenerator.TONE_SUP_ERROR
            )
            duration_ms = 150 if success else 400
            tone.startTone(tone_type, duration_ms)
        except Exception as exc:
            print(f"CountStock Sound Error: {exc}")
        return

    if winsound is not None:
        try:
            if success:
                winsound.Beep(2000, 150)
            else:
                winsound.Beep(600, 400)
        except Exception as exc:
            print(f"CountStock Sound Error: {exc}")
