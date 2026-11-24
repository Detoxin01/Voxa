"""
Whisper Type - Wispr Flow-style push-to-talk voice typing for Windows.

Runs silently in the system tray with a non-focus-stealing floating status pill.
Hold the hotkey (default: Left Ctrl), speak, release -> text is typed into any active window.
"""
import ctypes
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import winreg
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
LOG_PATH = HERE / "whisper_type.log"
ICON_PATH = HERE / "app.ico"
EXE_PATH = HERE / "WhisperType.exe"
SINGLE_INSTANCE_PORT = 47831
STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_NAME = "WhisperType"

# Always log stdout/stderr to whisper_type.log when running via pythonw.exe
if sys.stdout is None or sys.stderr is None or "pythonw" in Path(sys.executable).name.lower():
    log_file = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file

DEFAULTS = {
    "hotkey": "ctrl_l",          # ctrl_l, ctrl_r, alt_r, caps_lock, f8, f9, scroll_lock, ...
    "model": "large-v3-turbo",   # tiny, base, small, medium, large-v3, large-v3-turbo
    "device": "auto",            # auto, cuda, cpu
    "compute_type": "auto",      # auto, float16, int8_float16, int8, float32
    "language": "en",            # "en", "ne", "hi", or null for auto-detect
    "beam_size": 5,
    "initial_prompt": "",        # optional: names / jargon to help spelling
    "min_hold_seconds": 0.3,     # shorter taps are ignored (so normal Ctrl use still works)
    "trailing_space": True,
    "beep": True,
    "show_overlay": True,
}

SAMPLE_RATE = 16000
PREROLL_SECONDS = 0.3


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"Warning: could not parse config.json ({e}), using defaults.")
    else:
        save_config(cfg)
    return cfg


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Warning: could not save config.json: {e}")


def add_cuda_dll_paths():
    """Make pip-installed NVIDIA libs (cuBLAS / cuDNN) visible to CTranslate2."""
    try:
        import nvidia  # namespace package from nvidia-*-cu12 wheels
    except ImportError:
        return
    for base in list(nvidia.__path__):
        for sub in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"):
            p = os.path.join(base, sub, "bin")
            if os.path.isdir(p):
                os.add_dll_directory(p)
                os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")


add_cuda_dll_paths()

import numpy as np  # noqa: E402
import pystray  # noqa: E402
import sounddevice as sd  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from pynput import keyboard  # noqa: E402


def make_mic_image(color="#22c55e", bg="#18181b", size=64):
    """Draw a clean microphone icon with the given accent color."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(size * 0.06)
    d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=int(size * 0.24), fill=bg)
    # Mic capsule
    mx0, my0, mx1, my1 = int(size * 0.38), int(size * 0.20), int(size * 0.62), int(size * 0.54)
    d.rounded_rectangle([mx0, my0, mx1, my1], radius=int(size * 0.12), fill=color)
    # Mic cradle arc + stem
    ax0, ay0, ax1, ay1 = int(size * 0.28), int(size * 0.30), int(size * 0.72), int(size * 0.66)
    lw = max(2, int(size * 0.07))
    d.arc([ax0, ay0, ax1, ay1], start=0, end=180, fill=color, width=lw)
    cx = size // 2
    d.line([cx, int(size * 0.66), cx, int(size * 0.78)], fill=color, width=lw)
    d.line([int(size * 0.36), int(size * 0.78), int(size * 0.64), int(size * 0.78)], fill=color, width=lw)
    return img


def ensure_ico_file():
    if not ICON_PATH.exists():
        imgs = [make_mic_image("#22c55e", size=s) for s in (256, 64, 48, 32, 16)]
        imgs[0].save(ICON_PATH, format="ICO", sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])


def beep(freq, ms=60):
    try:
        import winsound
        threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()
    except Exception:
        pass


def parse_hotkey(name):
    n = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "left_ctrl": "ctrl_l", "right_ctrl": "ctrl_r", "lctrl": "ctrl_l", "rctrl": "ctrl_r",
        "left_alt": "alt_l", "right_alt": "alt_r", "lalt": "alt_l", "ralt": "alt_r",
        "left_shift": "shift_l", "right_shift": "shift_r",
        "capslock": "caps_lock", "caps": "caps_lock", "scrolllock": "scroll_lock",
        "left_win": "cmd_l", "right_win": "cmd_r", "win": "cmd",
    }
    n = aliases.get(n, n)
    if hasattr(keyboard.Key, n):
        return getattr(keyboard.Key, n)
    if len(n) == 1:
        return keyboard.KeyCode.from_char(n)
    raise ValueError(f"Unknown hotkey '{name}'. Examples: ctrl_l, ctrl_r, alt_r, caps_lock, f9")


def is_startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, STARTUP_REG_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_startup_enabled(enable):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                target = f'"{EXE_PATH}"' if EXE_PATH.exists() else f'"{HERE / ".venv/Scripts/pythonw.exe"}" "{HERE / "whisper_type.py"}"'
                winreg.SetValueEx(k, STARTUP_REG_NAME, 0, winreg.REG_SZ, target)
            else:
                try:
                    winreg.DeleteValue(k, STARTUP_REG_NAME)
                except FileNotFoundError:
                    pass
    except Exception as e:
        print(f"Failed to update startup registry: {e}")


def claim_single_instance(on_quit_request):
    """Stop any older running instance so only one hotkey listener is active."""
    try:
        with socket.create_connection(("127.0.0.1", SINGLE_INSTANCE_PORT), timeout=0.4) as s:
            s.sendall(b"QUIT")
        time.sleep(0.4)
    except Exception:
        pass

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        srv.listen(1)
    except Exception:
        return

    def accept_loop():
        while True:
            try:
                conn, _ = srv.accept()
                data = conn.recv(16)
                conn.close()
                if data == b"QUIT":
                    on_quit_request()
                    break
            except Exception:
                break

    threading.Thread(target=accept_loop, daemon=True).start()


class StatusPill:
    """Wispr Flow-style floating bottom pill that never steals focus."""

    def __init__(self):
        self.q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def show(self, dot_color, text, auto_hide_ms=None):
        self.q.put(("show", dot_color, text, auto_hide_ms))

    def hide(self):
        self.q.put(("hide", None, None, None))

    def _run(self):
        try:
            import tkinter as tk
        except Exception:
            return

        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.93)
        bg = "#18181b"
        root.configure(bg=bg)

        frame = tk.Frame(root, bg=bg, highlightthickness=1, highlightbackground="#3f3f46", padx=14, pady=6)
        frame.pack()

        dot_lbl = tk.Label(frame, text="●", font=("Segoe UI", 11, "bold"), bg=bg, fg="#22c55e")
        dot_lbl.pack(side="left", padx=(0, 6))

        txt_lbl = tk.Label(frame, text="Whisper Type", font=("Segoe UI", 10, "bold"), bg=bg, fg="#f4f4f5")
        txt_lbl.pack(side="left")

        root.update_idletasks()
        # Make window non-activating & toolwindow so it never steals focus or appears in Alt-Tab
        try:
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_TOPMOST = 0x00000008
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            )
        except Exception:
            pass

        hide_job = [None]

        def reposition():
            root.update_idletasks()
            w = root.winfo_reqwidth()
            h = root.winfo_reqheight()
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            x = (sw - w) // 2
            y = sh - h - 64
            root.geometry(f"{w}x{h}+{x}+{y}")

        def poll():
            try:
                while True:
                    cmd, color, text, auto_hide_ms = self.q.get_nowait()
                    if hide_job[0] is not None:
                        root.after_cancel(hide_job[0])
                        hide_job[0] = None
                    if cmd == "hide":
                        root.withdraw()
                    elif cmd == "show":
                        dot_lbl.configure(fg=color)
                        txt_lbl.configure(text=text)
                        reposition()
                        root.deiconify()
                        root.lift()
                        if auto_hide_ms:
                            hide_job[0] = root.after(auto_hide_ms, root.withdraw)
            except queue.Empty:
                pass
            root.after(40, poll)

        root.after(40, poll)
        root.mainloop()


def load_model(cfg):
    from faster_whisper import WhisperModel

    device, ct = cfg["device"], cfg["compute_type"]
    attempts = []
    if device in ("auto", "cuda"):
        attempts.append(("cuda", "float16" if ct == "auto" else ct))
    if device in ("auto", "cpu"):
        attempts.append(("cpu", "int8" if ct == "auto" else ct))

    for dev, ctype in attempts:
        try:
            print(f"Loading '{cfg['model']}' on {dev} ({ctype})...")
            try:
                model = WhisperModel(cfg["model"], device=dev, compute_type=ctype, local_files_only=True)
            except Exception:
                print("  (Model not cached locally yet, downloading from Hugging Face...)")
                model = WhisperModel(cfg["model"], device=dev, compute_type=ctype, local_files_only=False)
            segs, _ = model.transcribe(np.zeros(SAMPLE_RATE, np.float32), language="en")
            list(segs)  # warm-up: forces CUDA libs to actually load
            return model, dev, ctype
        except Exception as e:
            print(f"  -> {dev} failed: {e}")
    sys.exit("Could not load the model on any device.")


class Recorder:
    """Keeps the mic stream open with a small pre-roll so the first word isn't clipped."""

    def __init__(self):
        self.lock = threading.Lock()
        self.preroll = []
        self.preroll_len = int(PREROLL_SECONDS * SAMPLE_RATE)
        self.frames = None
        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                     dtype="float32", callback=self._cb)
        self.stream.start()

    def _cb(self, indata, frames, t, status):
        chunk = indata[:, 0].copy()
        with self.lock:
            if self.frames is not None:
                self.frames.append(chunk)
            else:
                self.preroll.append(chunk)
                total = sum(len(c) for c in self.preroll)
                while self.preroll and total - len(self.preroll[0]) >= self.preroll_len:
                    total -= len(self.preroll.pop(0))

    def start(self):
        with self.lock:
            self.frames = list(self.preroll)
            self.preroll = []

    def stop(self):
        with self.lock:
            frames, self.frames = self.frames or [], None
        return np.concatenate(frames) if frames else np.zeros(0, np.float32)


def main():
    ensure_ico_file()
    cfg = load_config()
    pill = StatusPill()

    icons = {
        "loading": make_mic_image("#a1a1aa"),
        "ready": make_mic_image("#22c55e"),
        "recording": make_mic_image("#ef4444"),
        "transcribing": make_mic_image("#f59e0b"),
    }

    state = {
        "held": False,
        "t0": 0.0,
        "cancel": False,
        "ready": False,
        "hotkey": parse_hotkey(cfg["hotkey"]),
        "device_label": "Loading model...",
    }

    tray = pystray.Icon("WhisperType", icons["loading"], "Whisper Type (Loading...)")

    def quit_app(*_):
        pill.hide()
        try:
            tray.stop()
        except Exception:
            pass
        os._exit(0)

    claim_single_instance(quit_app)

    def set_hotkey_choice(hk_name):
        def _handler(icon, item):
            cfg["hotkey"] = hk_name
            state["hotkey"] = parse_hotkey(hk_name)
            save_config(cfg)
            if cfg.get("show_overlay", True):
                pill.show("#22c55e", f"Hotkey set to [{hk_name}]", auto_hide_ms=1800)
        return _handler

    def is_hotkey_choice(hk_name):
        return lambda item: cfg.get("hotkey") == hk_name

    def set_lang_choice(lang_val):
        def _handler(icon, item):
            cfg["language"] = lang_val
            save_config(cfg)
            label = lang_val or "Auto"
            if cfg.get("show_overlay", True):
                pill.show("#22c55e", f"Language: {label}", auto_hide_ms=1800)
        return _handler

    def is_lang_choice(lang_val):
        return lambda item: cfg.get("language") == lang_val

    def toggle_overlay(icon, item):
        cfg["show_overlay"] = not cfg.get("show_overlay", True)
        save_config(cfg)
        if not cfg["show_overlay"]:
            pill.hide()
        else:
            pill.show("#22c55e", "Floating pill enabled", auto_hide_ms=1500)

    def toggle_beep(icon, item):
        cfg["beep"] = not cfg.get("beep", True)
        save_config(cfg)

    def toggle_startup(icon, item):
        set_startup_enabled(not is_startup_enabled())

    def open_settings(icon, item):
        try:
            os.startfile(str(CONFIG_PATH))
        except Exception:
            subprocess.Popen(["notepad.exe", str(CONFIG_PATH)])

    hotkey_menu = pystray.Menu(
        pystray.MenuItem("Left Ctrl (ctrl_l)", set_hotkey_choice("ctrl_l"), checked=is_hotkey_choice("ctrl_l"), radio=True),
        pystray.MenuItem("Right Ctrl (ctrl_r)", set_hotkey_choice("ctrl_r"), checked=is_hotkey_choice("ctrl_r"), radio=True),
        pystray.MenuItem("Right Alt (alt_r)", set_hotkey_choice("alt_r"), checked=is_hotkey_choice("alt_r"), radio=True),
        pystray.MenuItem("Caps Lock (caps_lock)", set_hotkey_choice("caps_lock"), checked=is_hotkey_choice("caps_lock"), radio=True),
        pystray.MenuItem("F8 (f8)", set_hotkey_choice("f8"), checked=is_hotkey_choice("f8"), radio=True),
        pystray.MenuItem("F9 (f9)", set_hotkey_choice("f9"), checked=is_hotkey_choice("f9"), radio=True),
    )

    lang_menu = pystray.Menu(
        pystray.MenuItem("English (en)", set_lang_choice("en"), checked=is_lang_choice("en"), radio=True),
        pystray.MenuItem("Auto-detect", set_lang_choice(None), checked=is_lang_choice(None), radio=True),
        pystray.MenuItem("Nepali (ne)", set_lang_choice("ne"), checked=is_lang_choice("ne"), radio=True),
        pystray.MenuItem("Hindi (hi)", set_lang_choice("hi"), checked=is_lang_choice("hi"), radio=True),
    )

    tray.menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"Status: {state['device_label']}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Hotkey", hotkey_menu),
        pystray.MenuItem("Language", lang_menu),
        pystray.MenuItem("Show Floating Pill", toggle_overlay, checked=lambda item: cfg.get("show_overlay", True)),
        pystray.MenuItem("Sound Beeps", toggle_beep, checked=lambda item: cfg.get("beep", True)),
        pystray.MenuItem("Start with Windows", toggle_startup, checked=lambda item: is_startup_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Settings (config.json)", open_settings),
        pystray.MenuItem("Quit Whisper Type", quit_app),
    )

    def engine_thread():
        if cfg.get("show_overlay", True):
            pill.show("#a1a1aa", f"Whisper Type: Loading {cfg['model']}...")
        model, dev, ctype = load_model(cfg)
        recorder = Recorder()
        typer = keyboard.Controller()
        jobs = queue.Queue()

        state["ready"] = True
        state["device_label"] = f"Ready on {dev} ({ctype})"
        tray.icon = icons["ready"]
        tray.title = f"Whisper Type — Hold [{cfg['hotkey']}] to talk"
        if cfg.get("show_overlay", True):
            pill.show("#22c55e", f"Whisper Type Ready — Hold [{cfg['hotkey']}] to talk", auto_hide_ms=2800)

        def worker():
            while True:
                audio = jobs.get()
                tray.icon = icons["transcribing"]
                if cfg.get("show_overlay", True):
                    pill.show("#f59e0b", "Transcribing...")
                t = time.time()
                try:
                    segs, _ = model.transcribe(
                        audio,
                        language=cfg["language"] or None,
                        beam_size=cfg["beam_size"],
                        initial_prompt=cfg["initial_prompt"] or None,
                        vad_filter=True,
                        condition_on_previous_text=False,
                    )
                    text = "".join(s.text for s in segs).strip()
                except Exception as e:
                    print(f"Transcription error: {e}")
                    tray.icon = icons["ready"]
                    pill.hide()
                    continue

                tray.icon = icons["ready"]
                if not text:
                    print("(no speech detected)")
                    if cfg.get("show_overlay", True):
                        pill.show("#a1a1aa", "No speech detected", auto_hide_ms=900)
                    continue

                dt = time.time() - t
                print(f"[{dt:.2f}s] {text}")
                # Brief pause to ensure the released modifier key is cleared in the target window
                time.sleep(0.03)
                typer.type(text + (" " if cfg["trailing_space"] else ""))
                if cfg.get("show_overlay", True):
                    preview = text if len(text) <= 42 else text[:39] + "..."
                    pill.show("#22c55e", f"✓ {preview}", auto_hide_ms=1100)

        threading.Thread(target=worker, daemon=True).start()

        def recording_started():
            if state["held"] and not state["cancel"]:
                tray.icon = icons["recording"]
                if cfg.get("beep", True):
                    beep(880)
                if cfg.get("show_overlay", True):
                    pill.show("#ef4444", "Listening... (release to type)")

        def on_press(key):
            if not state["ready"]:
                return
            if key == state["hotkey"]:
                if not state["held"]:
                    state.update(held=True, t0=time.time(), cancel=False)
                    recorder.start()
                    threading.Timer(cfg["min_hold_seconds"], recording_started).start()
            elif state["held"]:
                state["cancel"] = True
                tray.icon = icons["ready"]
                pill.hide()

        def on_release(key):
            if key == state["hotkey"] and state["held"]:
                state["held"] = False
                audio = recorder.stop()
                held = time.time() - state["t0"]
                if state["cancel"] or held < cfg["min_hold_seconds"]:
                    tray.icon = icons["ready"]
                    pill.hide()
                    return
                if cfg.get("beep", True):
                    beep(440)
                jobs.put(audio)

        print(f"\nReady on {dev} ({ctype}). Hold [{cfg['hotkey']}] to talk, release to type.\n")
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    threading.Thread(target=engine_thread, daemon=True).start()
    tray.run()


if __name__ == "__main__":
    main()
