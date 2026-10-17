#!/usr/bin/env python3
"""Mood organ: dial a code, get a mood.

The resting screen is splash-screen-heart.png, next to this script
(black if that file is missing).

Put one folder per code in ./moods (next to this script), e.g. moods/481/:
  a video alone        plays with its own sound
  images (+ a sound)   shown in filename order, IMAGE_SECONDS each;
                       an animated gif runs for as long as its animation
  a video + sound/images  the video is muted and shown like an animated gif
  a sound only         plays over the splash screen
With LOOP_SESSION on, the mood repeats until another code is dialed.

Keys: digits (top row or number pad), Enter to dial right away,
Backspace to fix a digit, Escape to stop and return to the splash, q to quit.

Run: python3 organ.py
"""
import math
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
IMAGE_SECONDS = 2.0       # how long each still image stays up
LOOP_SESSION = True       # repeat the dialed mood until another code is dialed
# "fill": cover the whole screen, cropping the overflow; "fit": show it all, with black bars
SCALE_MODE = ["fill", "fit"][1]
VIDEO = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SOUND = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
# -----------------------------------------------------------------------------

screen = mpv.MPV(
    fullscreen=True, idle=True, force_window=True,
    background="none", background_color="#00000000",  # transparent pixels show the desktop (needs a compositor)
    input_default_bindings=False, input_vo_keyboard=True,
    image_display_duration="inf",  # images stay up until the script changes them
    panscan=1.0 if SCALE_MODE == "fill" else 0.0,
    osd_font_size=90, osd_align_x="center", osd_align_y="center",
    cursor_autohide="always",
)
speaker = mpv.MPV(vid="no", idle=True)  # sound for image moods; never opens a window

lock = threading.Lock()
digits = ""
last_digit_at = 0.0
running = True

# The mood currently playing; None when resting on the splash screen.
session = None


def find_all(folder, kinds):
    return [str(p) for p in sorted(folder.iterdir()) if p.suffix.lower() in kinds]


def show_image(path):
    """Show one image of the slideshow and note when to move on."""
    now = time.monotonic()
    suffix = Path(path).suffix.lower()
    session["gif"] = suffix == ".gif" or suffix in VIDEO  # animated: loops, timed by its length
    session["started"] = now
    session["next_at"] = float("inf") if session["gif"] else now + IMAGE_SECONDS
    session["timed"] = not session["gif"]
    screen.mute = "yes" if suffix in VIDEO else "no"  # the separate sound file takes over
    screen.loop_file = "inf" if session["gif"] else "no"  # looping avoids a black gap
    screen.play(path)


def say(text, seconds):
    screen.show_text(text, max(1, int(seconds * 1000)))


def show_menu(visible):
    """List the dialable codes along the bottom of the splash screen."""
    codes = [p.name for p in sorted(MOODS_DIR.iterdir()) if p.is_dir()] if visible else []
    if codes:
        text = "{\\an2\\fs40}Dial:  " + "   ".join(codes)
        screen.command("osd-overlay", 1, "ass-events", text)
    else:
        screen.command("osd-overlay", 1, "none", "")


def show_splash():
    """The resting screen: the splash image, or black if the file is missing."""
    show_menu(True)
    screen.loop_file = "no"
    screen.mute = "no"
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
    global digits, session
    code, digits = digits, ""
    speaker.stop()
    session = None

    folder = MOODS_DIR / code
    videos = images = sounds = []
    if folder.is_dir():
        videos = find_all(folder, VIDEO)
        images = find_all(folder, IMAGE)
        sounds = find_all(folder, SOUND)
    if not (videos or images or sounds):
        show_splash()
        say(f"No setting for {code}", NO_SETTING_SECONDS)
        return

    say("", 0)
    show_menu(False)
    if videos and not (images or sounds):
        screen.mute = "no"
        screen.loop_file = "inf" if LOOP_SESSION else "no"
        screen.play(videos[0])
        if SPLASH.exists() and not LOOP_SESSION:
            screen.playlist_append(str(SPLASH))  # back to the splash when the video ends
        return

    # A video next to sound or images is just another (muted) visual in the slideshow.
    images = sorted(videos + images)
    session = {"images": images, "idx": 0, "sound": bool(sounds),
               "sound_started": False, "images_done": not images}
    if images:
        show_image(images[0])
    else:
        show_splash()
    if sounds:
        speaker.loop_file = "inf" if LOOP_SESSION else "no"
        speaker.play(sounds[0])


def tick(now):
    """Advance the slideshow and end the mood when it is over. Lock held."""
    global session
    s = session
    if s is None:
        return
    images = s["images"]
    if images and not s["images_done"]:
        if s["gif"] and not s["timed"]:
            # Once mpv reports the animation length, run whole loops covering IMAGE_SECONDS.
            length = screen.duration
            if length:
                s["next_at"] = now + max(1, math.ceil(IMAGE_SECONDS / length)) * length
                s["timed"] = True
            elif now - s["started"] > 2:
                s["next_at"] = s["started"] + IMAGE_SECONDS
                s["timed"] = True
        finished = now >= s["next_at"]
        single_still = len(images) == 1
        if finished and single_still and LOOP_SESSION:
            s["next_at"] = float("inf")  # nothing to cycle to
        elif finished:
            s["idx"] += 1
            if s["idx"] >= len(images):
                if LOOP_SESSION:
                    s["idx"] = 0
                else:
                    s["images_done"] = True
            if not s["images_done"]:
                show_image(images[s["idx"]])

    sound_done = True
    if s["sound"]:
        if not speaker.idle_active:
            s["sound_started"] = True
        sound_done = s["sound_started"] and speaker.idle_active
    if not LOOP_SESSION and s["images_done"] and sound_done:
        session = None
        show_splash()


def escape():
    """Stop whatever is playing and go back to the splash screen."""
    global digits, session
    with lock:
        digits = ""
        session = None
        speaker.stop()
        say("", 0)
        show_splash()


def quit_organ():
    global running
    running = False


def main():
    for d in "0123456789":
        screen.on_key_press(d)(lambda d=d: dial_digit(d))
        screen.on_key_press("KP" + d)(lambda d=d: dial_digit(d))
    screen.on_key_press("ENTER")(dial_now)
    screen.on_key_press("KP_ENTER")(dial_now)
    screen.on_key_press("BS")(delete_digit)
    screen.on_key_press("ESC")(escape)
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
                tick(now)
    except (KeyboardInterrupt, mpv.ShutdownError):
        pass
    finally:
        speaker.terminate()
        screen.terminate()


if __name__ == "__main__":
    main()
