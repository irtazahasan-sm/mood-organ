#!/usr/bin/env python3
"""Mood organ: dial a code, get a mood.

The resting screen is splash-screen-heart.png, next to this script
(black if that file is missing).

Put mood files in ./moods (next to this script), named by their code:
  481.mp4            video with its own sound
  482.jpg + 482.mp3  image that stays up until the sound ends
  483.png            image on its own, stays up IMAGE_SECONDS
  484.mp3            sound on its own, over the splash screen
If a code has a video, the video wins.

Keys: digits (top row or number pad), Enter to dial right away,
Backspace to fix a digit, q to quit.

Run: python3 organ.py
"""
import threading
import time
from pathlib import Path

import mpv

# ---- Settings ---------------------------------------------------------------
HERE = Path(__file__).resolve().parent
MOODS_DIR = HERE / "moods"
SPLASH = HERE / "splash-screen-heart.png"
DIAL_AFTER = 2.0          # seconds after the last digit before the code goes through
NO_SETTING_SECONDS = 5    # how long "No setting for ..." stays on screen
IMAGE_SECONDS = 10        # how long an image without a sound stays up
VIDEO = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp"}
SOUND = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
# -----------------------------------------------------------------------------

screen = mpv.MPV(
    fullscreen=True, idle=True, force_window=True,
    input_default_bindings=False, input_vo_keyboard=True,
    image_display_duration="inf",  # images stay up until the script changes them
    panscan=1.0,  # fill the screen, cropping anything that isn't the screen's shape
    osd_font_size=90, osd_align_x="center", osd_align_y="center",
    cursor_autohide="always",
)
speaker = mpv.MPV(vid="no", idle=True)  # sound for image moods; never opens a window

lock = threading.Lock()
digits = ""
last_digit_at = 0.0
image_waits_for_sound = False
sound_started = False
image_until = None
running = True


def find(code, kinds):
    for path in sorted(MOODS_DIR.glob(f"{code}.*")):
        if path.suffix.lower() in kinds:
            return str(path)
    return None


def say(text, seconds):
    screen.show_text(text, max(1, int(seconds * 1000)))


def show_splash():
    """The resting screen: the splash image, or black if the file is missing."""
    if SPLASH.exists():
        screen.play(str(SPLASH))
    else:
        screen.stop()


def dial_digit(d):
    """Every input calls this: the keyboard now, the dial or knob later."""
    global digits, last_digit_at
    with lock:
        digits += d
        last_digit_at = time.monotonic()
        say(digits, 3600)


def delete_digit():
    global digits
    with lock:
        digits = digits[:-1]
        say(digits, 3600 if digits else 0)


def dial_now():
    with lock:
        if digits:
            go()


def go():
    """Play whatever the dialed code points to. Call with the lock held."""
    global digits, image_waits_for_sound, sound_started, image_until
    code, digits = digits, ""
    speaker.stop()
    image_waits_for_sound = sound_started = False
    image_until = None

    video, image, sound = find(code, VIDEO), find(code, IMAGE), find(code, SOUND)
    if not (video or image or sound):
        show_splash()
        say(f"No setting for {code}", NO_SETTING_SECONDS)
        return

    say("", 0)
    if video:
        screen.play(video)
        if SPLASH.exists():
            screen.playlist_append(str(SPLASH))  # back to the splash when the video ends
        return
    if image:
        screen.play(image)
        if sound:
            image_waits_for_sound = True
        else:
            image_until = time.monotonic() + IMAGE_SECONDS
    else:
        show_splash()
    if sound:
        speaker.play(sound)


def quit_organ():
    global running
    running = False


def main():
    global image_waits_for_sound, sound_started, image_until
    for d in "0123456789":
        screen.on_key_press(d)(lambda d=d: dial_digit(d))
        screen.on_key_press("KP" + d)(lambda d=d: dial_digit(d))
    screen.on_key_press("ENTER")(dial_now)
    screen.on_key_press("KP_ENTER")(dial_now)
    screen.on_key_press("BS")(delete_digit)
    screen.on_key_press("q")(quit_organ)

    # Later: the rotary dial or knob gets wired up here and calls dial_digit(...).

    show_splash()
    try:
        while running:
            time.sleep(0.05)
            with lock:
                now = time.monotonic()
                if digits and now - last_digit_at >= DIAL_AFTER:
                    go()
                if image_until and now >= image_until:  # image-only mood is done
                    image_until = None
                    show_splash()
                if image_waits_for_sound:
                    if not speaker.idle_active:
                        sound_started = True
                    elif sound_started:  # the sound just ended, so take the image down
                        image_waits_for_sound = False
                        show_splash()
    except (KeyboardInterrupt, mpv.ShutdownError):
        pass
    finally:
        speaker.terminate()
        screen.terminate()


if __name__ == "__main__":
    main()
