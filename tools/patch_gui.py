"""Point-and-click installer for the ToHeart2 DX PLUS English patch.

The window asks for one thing — the installed game folder — then checks, installs
or restores through the same guarded core as ``patch_game.py``. It never starts
RPCS3, never touches save data and never deletes a backup.

``tkinter`` is imported only when the window is created, so the helper functions
below stay usable (and testable) on a machine without a display.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import sys
import threading

import patch_data
import patch_engine
import patch_game

TITLE = "ToHeart2 DX PLUS - English patch"
VERSION = "0.1"
SETTINGS_NAME = "th2dxp_patch_ui.json"
INTRO = (
    "This installs the English patch into the game you own. It decrypts EBOOT.BIN\n"
    "and data.sdat, applies the patch and verifies every result before replacing\n"
    "anything. Your originals stay in .th2dxp-backup so you can undo it.\n\n"
    "The first install takes several minutes because data.sdat is 2.2 GB.\n"
    "It never starts RPCS3 and never touches save data."
)


def settings_path():
    """Per-user settings file; never next to a read-only install directory."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    return root / "th2dxp_en" / SETTINGS_NAME


def load_settings(path=None):
    path = Path(path or settings_path())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(values, path=None):
    path = Path(path or settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(values, ensure_ascii=False, indent=2) + "\n")


def find_build(start=None):
    """Return the patch-data folder shipped next to the program, or None."""
    try:
        return patch_engine.default_patch_dir(start)
    except ValueError:
        return None


def human_bytes(size):
    return patch_engine.format_size(size)


KIND_LABELS = {
    "SELF": "original encrypted executable",
    "ELF": "pristine decrypted executable",
    "pristine": "original retail archive",
    "patched": "already patched file",
    "unknown": "unrecognised file",
    "missing": "missing file",
}


def kind_label(kind):
    return KIND_LABELS.get(kind, kind)


def describe_plan(plan):
    """Confirmation text for one install plan."""
    if plan.get("blocked"):
        return ("This folder cannot be patched yet:\n\n"
                + "\n".join(f"- {text}" for text in plan["blocked"]))
    if plan.get("nothing_to_do"):
        return "Nothing to do: this folder already has the English patch."
    lines = [f"Install into: {plan['usrdir']}", ""]
    elf = plan.get("elf") or {}
    archive = plan.get("archive") or {}
    if elf.get("install"):
        lines.append(f"EBOOT.BIN: back up the {kind_label(elf.get('current_kind'))}, decrypt it, "
                     "apply the executable patch, then verify the result.")
    if archive.get("install"):
        lines.append(f"data.sdat: back up the {kind_label(archive.get('current_kind'))}, decrypt "
                     "it, replace the UI atlases, re-encrypt it, then authenticate the new "
                     "archive. This step takes several minutes.")
    lines.append("")
    lines.append(f"Free space needed in the game folder: about "
                 f"{human_bytes(plan.get('free_space_needed', 0))} "
                 f"(available: {human_bytes(plan.get('free_space_available', 0))}).")
    lines.append("Your originals stay in .th2dxp-backup inside the game folder.")
    installed = plan.get("last_install")
    if installed:
        lines.append("")
        lines.append(f"Last install: {installed.get('installed_at', 'unknown time')}")
        lines.append(f"  EBOOT.BIN {str(installed.get('elf_sha256'))[:16]}...")
        lines.append(f"  data.sdat {(installed.get('sdat_sha256') or '')[:16]}...")
    backups = plan.get("backups") or {}
    present = [name for name, row in backups.items() if row]
    lines.append(f"Backups: {', '.join(present) if present else 'none yet'}")
    return "\n".join(lines)


class Window:
    """The whole UI; all long work runs in a worker thread."""

    def __init__(self, root, settings=None):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.root = root
        self.settings = settings if settings is not None else load_settings()
        self.queue = queue.Queue()
        self.busy = False

        root.title(f"{TITLE} {VERSION}")
        root.minsize(720, 560)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Head.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Hint.TLabel", foreground="#444444")
        style.configure("Go.TButton", font=("Segoe UI", 10, "bold"))

        header = ttk.Frame(root, padding=(16, 14, 16, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="ToHeart2 DX PLUS - English patch", style="Head.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(header, text=INTRO, style="Hint.TLabel", justify="left").grid(
            row=1, column=0, sticky="w", pady=(6, 0))

        folders = ttk.LabelFrame(root, text="Folders", padding=(12, 8))
        folders.grid(row=1, column=0, sticky="ew", padx=16)
        folders.columnconfigure(1, weight=1)
        self.game_var = tk.StringVar(value=self.settings.get("game_dir", ""))
        self.build_var = tk.StringVar(value=self.settings.get("build_dir", ""))
        ttk.Label(folders, text="Game folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(folders, textvariable=self.game_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(folders, text="Browse...", command=self.browse_game).grid(row=0, column=2)
        ttk.Label(folders, text="Patch data").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(folders, textvariable=self.build_var).grid(row=1, column=1, sticky="ew", padx=8,
                                                             pady=(8, 0))
        ttk.Button(folders, text="Browse...", command=self.browse_build).grid(row=1, column=2,
                                                                             pady=(8, 0))
        ttk.Label(folders, text="The game folder you installed in RPCS3 (it contains PS3_GAME).",
                  style="Hint.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        progress = ttk.Frame(root, padding=(16, 10, 16, 0))
        progress.grid(row=2, column=0, sticky="ew")
        progress.columnconfigure(0, weight=1)
        self.progress_label = ttk.Label(progress, text="Ready.")
        self.progress_label.grid(row=0, column=0, sticky="w")
        self.bar = ttk.Progressbar(progress, mode="determinate", maximum=1000)
        self.bar.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        body = ttk.Frame(root, padding=(16, 10, 16, 0))
        body.grid(row=3, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.log = tk.Text(body, height=14, wrap="word", relief="flat", background="#f7f7f7",
                           font=("Consolas", 9), state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

        buttons = ttk.Frame(root, padding=(16, 10, 16, 14))
        buttons.grid(row=4, column=0, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        self.check_button = ttk.Button(buttons, text="Check", command=self.check)
        self.check_button.grid(row=0, column=0, sticky="w")
        self.install_button = ttk.Button(buttons, text="Install patch", style="Go.TButton",
                                         command=self.install)
        self.install_button.grid(row=0, column=1, padx=6)
        self.restore_button = ttk.Button(buttons, text="Restore original",
                                        command=self.restore)
        self.restore_button.grid(row=0, column=2, padx=6)
        ttk.Button(buttons, text="Open backups", command=self.open_backups).grid(row=0, column=3,
                                                                                padx=6)
        ttk.Button(buttons, text="Quit", command=root.destroy).grid(row=0, column=4, padx=(6, 0))

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.write(INTRO)
        if not self.build_var.get():
            found = find_build()
            if found is not None:
                self.build_var.set(str(found))
                self.write(f"\nPatch files found: {found}")
        if self.game_var.get():
            self.root.after(150, self.check)
        else:
            guess = patch_game.tool_root() / "PS3_GAME/USRDIR"
            if (guess / patch_game.GAME_ELF_NAME).is_file():
                self.game_var.set(str(patch_game.tool_root()))
                self.root.after(150, self.check)
        self.root.after(80, self.poll)

    # ---- small UI helpers ------------------------------------------------
    def write(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def say(self, text):
        self.progress_label.configure(text=text)

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for button in (self.check_button, self.install_button, self.restore_button):
            button.configure(state=state)
        self.root.configure(cursor="watch" if busy else "")

    def ask(self, title, message):
        from tkinter import messagebox
        return messagebox.askyesno(title, message, icon="question", parent=self.root)

    def error(self, message):
        from tkinter import messagebox
        self.write("\nERROR: " + message)
        self.say("Stopped: " + message.splitlines()[0])
        messagebox.showerror(TITLE, message, parent=self.root)

    def info(self, message):
        from tkinter import messagebox
        messagebox.showinfo(TITLE, message, parent=self.root)

    # ---- folder picking --------------------------------------------------
    def browse_game(self):
        from tkinter import filedialog
        chosen = filedialog.askdirectory(title="Select the game folder", parent=self.root)
        if chosen:
            self.game_var.set(chosen)
            self.check()

    def browse_build(self):
        from tkinter import filedialog
        chosen = filedialog.askdirectory(title="Select the folder with the patch data",
                                         parent=self.root)
        if chosen:
            self.build_var.set(chosen)

    def remembered(self):
        self.settings.update(game_dir=self.game_var.get().strip(),
                             build_dir=self.build_var.get().strip())
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def open_backups(self):
        folder = Path(self.game_var.get().strip() or ".") / patch_game.BACKUP_DIRNAME
        try:
            usrdir = patch_game.require_usrdir(self.game_var.get().strip())
        except ValueError:
            self.error("Choose the game folder first.")
            return
        folder = usrdir / patch_game.BACKUP_DIRNAME
        if not folder.is_dir():
            self.info("No backups have been made yet.")
            return
        os.startfile(str(folder))

    # ---- worker plumbing -------------------------------------------------
    def run(self, work, done):
        """Run ``work(progress)`` off the UI thread, then ``done(result)``."""
        if self.busy:
            return
        self.set_busy(True)
        self.remembered()

        def report(label, done_bytes, total):
            self.queue.put(("progress", label, done_bytes, total))

        def target():
            try:
                result = work(report)
            except (OSError, ValueError, KeyError, RuntimeError) as error:
                self.queue.put(("error", str(error)))
            except Exception as error:  # keep the window usable on any surprise
                self.queue.put(("error", f"{type(error).__name__}: {error}"))
            else:
                self.queue.put(("done", done, result))

        threading.Thread(target=target, daemon=True).start()

    def poll(self):
        try:
            while True:
                message = self.queue.get_nowait()
                if message[0] == "progress":
                    _, label, done_bytes, total = message
                    self.say(label)
                    if total:
                        self.set_bar_mode("determinate")
                        self.bar.configure(value=int(done_bytes * 1000 / total))
                    else:
                        self.set_bar_mode("indeterminate")
                elif message[0] == "error":
                    self.set_busy(False)
                    self.stop_bar()
                    self.error(message[1])
                else:
                    _, callback, result = message
                    self.set_busy(False)
                    self.stop_bar()
                    self.say("Done.")
                    callback(result)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(80, self.poll)

    def set_bar_mode(self, mode):
        if self.bar.cget("mode") == mode:
            return
        if mode == "indeterminate":
            self.bar.configure(mode="indeterminate", value=0)
            self.bar.start(12)
        else:
            self.bar.stop()
            self.bar.configure(mode="determinate", value=0)

    def stop_bar(self):
        self.bar.stop()
        self.bar.configure(mode="determinate", value=0)

    def usrdir(self):
        return patch_game.require_usrdir(self.game_var.get().strip())

    def build(self):
        text = self.build_var.get().strip()
        if text:
            return Path(text)
        found = find_build()
        if found is None:
            raise ValueError(
                "The patch data is missing.\n\nExpected a 'patch-data' folder containing "
                "manifest.json next to this program, or choose it with Browse.")
        self.build_var.set(str(found))
        return found

    # ---- actions ---------------------------------------------------------
    def check(self):
        try:
            build, usrdir = self.build(), self.usrdir()
        except ValueError as error:
            self.error(str(error))
            return

        def work(report):
            return patch_engine.plan(build, usrdir, report)

        def done(plan):
            self.write("\n" + describe_plan(plan))
            self.say("Folder checked.")
        self.run(work, done)

    def install(self):
        try:
            build, usrdir = self.build(), self.usrdir()
        except ValueError as error:
            self.error(str(error))
            return

        def plan_work(report):
            return patch_engine.plan(build, usrdir, report)

        def plan_done(plan):
            text = describe_plan(plan)
            self.write("\n" + text)
            if plan["blocked"]:
                self.say("Cannot install yet.")
                self.error(text)
                return
            if plan["nothing_to_do"]:
                self.say("Already up to date.")
                self.info("Nothing to do: this folder already has the English patch.")
                return
            if not self.ask("Install the English patch?", text):
                self.say("Cancelled; nothing was changed.")
                return

            def write_work(report):
                return patch_engine.apply(plan, report)

            self.run(write_work, installed)

        def installed(result):
            self.write("\nInstalled.")
            self.write(f"  EBOOT.BIN {result['elf_sha256']}")
            self.write(f"  data.sdat {result['sdat_sha256']}")
            self.say("Installed. Start the game normally in RPCS3.")
            self.info("The English patch is installed.\n\nStart the game normally in RPCS3.\n"
                      "Use 'Restore original' to undo it.")

        self.run(plan_work, plan_done)

    def restore(self):
        try:
            usrdir = self.usrdir()
        except ValueError as error:
            self.error(str(error))
            return

        def plan_work(report):
            return patch_game.plan_restore(usrdir, report)

        def plan_done(plan):
            lines = [f"Restore the original files in {plan['usrdir']}?", ""]
            for name, row in plan["restore"].items():
                lines.append(f"{name}: back to the saved copy ({human_bytes(row['size'])}).")
            if plan["removed"]:
                lines.append("")
                lines.append("Also removes: " + ", ".join(Path(p).name for p in plan["removed"]))
            if not self.ask("Restore the original files?", "\n".join(lines)):
                self.say("Cancelled; nothing was changed.")
                return

            def write_work(report):
                return patch_game.write_restore(plan, report)

            self.run(write_work, restored)

        def restored(result):
            self.write("\nOriginals restored.")
            self.say("Restored.")
            self.info("Your original files are back in place.")

        self.run(plan_work, plan_done)

    def close(self):
        self.remembered()
        self.root.destroy()


def _emit(text):
    """Write a line even when the windowed build has no console attached."""
    stream = sys.stdout or sys.stderr
    if stream is not None:
        try:
            stream.write(text + "\n")
        except (OSError, ValueError):
            pass


def _fatal(message):
    """Report a startup failure in a windowed program without a console."""
    _emit(message)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10)
    except Exception:
        pass


def self_test():
    """Headless sanity check for the frozen build (``--self-test``)."""
    problems = []
    if not TITLE:
        problems.append("no title")
    blocked = describe_plan({"usrdir": "C:/game", "blocked": ["data.sdat is missing"],
                             "nothing_to_do": False})
    if "cannot be patched yet" not in blocked:
        problems.append("blocked plan text missing")
    plan = describe_plan({"usrdir": "C:/game", "blocked": [], "nothing_to_do": False,
                          "patch": {"version": "0.1"},
                          "elf": {"install": True, "current_kind": "SELF"},
                          "archive": {"install": True, "current_kind": "pristine"},
                          "free_space_needed": 7 * 1024 ** 3,
                          "free_space_available": 100 * 1024 ** 3,
                          "backups": {}, "last_install": None})
    for expected in ("decrypt it", "7.0 GiB", "Backups: none yet", ".th2dxp-backup"):
        if expected not in plan:
            problems.append(f"plan text missing {expected!r}")
    idle = describe_plan({"usrdir": "C:/game", "blocked": [], "nothing_to_do": True})
    if "Nothing to do" not in idle:
        problems.append("idle plan text missing")
    if human_bytes(2185195888) != "2.0 GiB":
        problems.append("size formatting changed")
    # The frozen program must find its own payload: the patch data and the two
    # pinned helpers travel inside it, so a missing or altered one is fatal.
    try:
        folder = patch_engine.default_patch_dir()
        manifest = patch_data.load_manifest(folder)
        if manifest["elf"]["output_size"] <= manifest["elf"]["source_size"]:
            problems.append("patch data does not grow the executable")
        if not manifest["archive"]["replacements"]:
            problems.append("patch data carries no archive replacements")
    except ValueError as error:
        problems.append(f"patch data: {error}")
    try:
        decryptor, packer = patch_engine.find_tools()
        if not (decryptor.is_file() and packer.is_file()):
            problems.append("helpers resolved to missing files")
    except ValueError as error:
        problems.append(f"helpers: {error}")
    if problems:
        raise SystemExit("self-test FAILED: " + "; ".join(problems))
    _emit("self-test OK")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv:
        _emit(f"{TITLE} {VERSION}")
        return 0
    if "--self-test" in argv:
        self_test()
        return 0
    if any(flag in argv for flag in ("-h", "--help")):
        _emit((__doc__ or TITLE).strip())
        _emit("")
        _emit(f"Version {VERSION}. Run without arguments to open the window.")
        return 0
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception as error:  # a display-less or broken Tk install
        _fatal(f"{TITLE} could not start its window:\n\n{error}")
        return 1
    Window(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
