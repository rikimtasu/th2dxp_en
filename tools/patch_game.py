"""Install the English patch into a game USRDIR, or restore the original files.

This is the end-user tool. It runs only when asked; it never launches RPCS3,
never touches save data and never deletes a backup. The user supplies one
verified build directory (``EBOOT.elf``/``EBOOT_EN.elf`` plus the paired
``data.sdat`` and ``EBOOT.report.json``), and the tool:

1. re-checks that the ELF and the archive match the report they came with,
2. backs up ``EBOOT.BIN`` and ``data.sdat`` once, hash-recorded,
3. replaces ``EBOOT.BIN`` with the patched ELF and ``data.sdat`` with the paired
   archive, verifying every byte it writes,
4. records what it did in ``.th2dxp-en-patch.json``.

The PS3 SELF container cannot be rebuilt here, so the patched executable is
written as a plain ELF named ``EBOOT.BIN``; that is the form RPCS3 boots
directly. The original SELF is kept byte-exactly in
``.th2dxp-backup/EBOOT.BIN`` and ``restore`` puts it back.

``data.sdat`` is 2.2 GB, so the first install needs roughly twice its size in
free space: the backup copy and the replacement being written.

Commands:

    status                      show installed files, backups and the journal
    apply --build build/<name>  dry-run by default; add --apply to write
    restore                     put the recorded originals back (dry-run first)

A dry run writes nothing and reports exactly what would move.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from patch_data import require, sha256_file

BACKUP_DIRNAME = ".th2dxp-backup"
JOURNAL_NAME = ".th2dxp-en-patch.json"
GAME_ELF_NAME = "EBOOT.BIN"
LEGACY_ELF_NAME = "EBOOT_EN.elf"
SDAT_NAME = "data.sdat"
ELF_NAME = "EBOOT.elf"
REPORT_NAME = "EBOOT.report.json"
SELF_MAGIC = b"SCE\0"
ELF_MAGIC = b"\x7fELF"
CHUNK = 4 * 1024 * 1024

#: BLJM60381 retail data.sdat (the only file this tool will replace blindly).
PRISTINE_SDAT_SHA256 = "4509a4e93e7e630e09971326d3e5f78e4c48a05e588e8c1ab9f0a88b174a9e3a"
PRISTINE_SDAT_SIZE = 2185195888


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def magic(path):
    with Path(path).open("rb") as stream:
        return stream.read(4)


def tool_root():
    """Directory holding the release files (works frozen or from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def default_build(start=None):
    """Find the one obvious build directory, never guess between several."""
    start = Path(start or tool_root())
    for candidate in (start, start / "patch-data", start / "build/english-v0.1",
                      start.parent / "patch-data", start.parent / "build/english-v0.1"):
        if (candidate / ELF_NAME).is_file() and (candidate / REPORT_NAME).is_file():
            return candidate
    raise ValueError("No build directory found; pass --build <dir> containing EBOOT.elf and EBOOT.report.json")


def staged_pair(build, progress=None):
    """Return verified ELF/SDAT files and hashes for one build, never a mixture."""
    build = Path(build).resolve()
    require(build.is_dir(), f"Build directory not found: {build}")
    elf = build / ELF_NAME
    if not elf.is_file():
        alternate = build / LEGACY_ELF_NAME
        require(alternate.is_file(), f"Build has no {ELF_NAME}: {build}")
        elf = alternate
    require(magic(elf) == ELF_MAGIC, f"{elf.name} is not a decrypted ELF; refusing to install it")
    report_path = build / REPORT_NAME
    require(report_path.is_file(), f"Build has no {REPORT_NAME}; refusing an unverified executable")
    report = load_json(report_path)
    elf_sha256 = sha256_file(elf, _report(progress, "Checking the patched EBOOT"))
    require(elf_sha256 == report.get("output_sha256"),
            "EBOOT.elf does not match its report; rebuild instead of installing")
    result = {"build": build, "elf": elf, "elf_sha256": elf_sha256, "sdat": None,
              "sdat_sha256": None, "report": report}
    declared = report.get("ui_archive")
    if not isinstance(declared, dict):
        assets = report.get("ui_assets")
        if isinstance(assets, dict) and assets.get("sha256"):
            declared = {"path": SDAT_NAME, "sha256": assets["sha256"]}
    archive = build / SDAT_NAME
    if isinstance(declared, dict) and declared.get("path"):
        archive = build / declared["path"]
        require(archive.is_file(), f"Build report requires {declared['path']}, which is missing")
    elif not archive.is_file():
        archive = build / "assets" / SDAT_NAME
        if not archive.is_file():
            return result
    sdat_sha256 = sha256_file(archive, _report(progress, "Checking the patch data.sdat"))
    require(sdat_sha256 == declared.get("sha256"),
            "data.sdat does not match the report; never mix an older archive with this ELF")
    result.update(sdat=archive, sdat_sha256=sdat_sha256)
    return result


def rpcs3_running():
    """Windows-only advisory check; an unknown state never blocks the caller."""
    if os.name != "nt":
        return False
    try:
        completed = subprocess.run(["tasklist", "/FI", "IMAGENAME eq rpcs3.exe", "/NH"],
                                   capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return "rpcs3.exe" in completed.stdout.casefold()


def journal_path(usrdir):
    return Path(usrdir) / JOURNAL_NAME


def read_journal(usrdir):
    path = journal_path(usrdir)
    return load_json(path) if path.is_file() else None


def write_journal(usrdir, data):
    save_json(journal_path(usrdir), data)


def resolve_usrdir(path):
    """Accept the game folder, its PS3_GAME directory or USRDIR itself."""
    path = Path(path).expanduser()
    if path.is_file():
        path = path.parent
    for candidate in (path, path / "PS3_GAME" / "USRDIR", path / "USRDIR"):
        if (candidate / GAME_ELF_NAME).is_file():
            return candidate.resolve()
    raise ValueError(f"Not a game USRDIR (no {GAME_ELF_NAME}): {path}")


def require_usrdir(usrdir):
    usrdir = Path(usrdir).expanduser()
    require(usrdir.exists(), f"USRDIR not found: {usrdir}")
    return resolve_usrdir(usrdir)


def copy_verified(source, target, expected, progress=None):
    """Copy through a temporary sibling so a partial write never replaces a file."""
    source, target = Path(source), Path(target)
    total = source.stat().st_size
    temporary = target.with_name(target.name + ".th2dxp-part")
    try:
        done = 0
        with source.open("rb") as reader, temporary.open("wb") as writer:
            while chunk := reader.read(CHUNK):
                writer.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
        require(sha256_file(temporary) == expected, f"Copy verification failed for {target.name}")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    require(sha256_file(target) == expected, f"Installed {target.name} hash changed after replace")


def free_bytes(path):
    return shutil.disk_usage(str(path)).free


def classify_sdat(path, digest=None):
    """Say what the current data.sdat is, so nothing unknown is replaced."""
    if not path.is_file():
        return "absent"
    if path.stat().st_size == PRISTINE_SDAT_SIZE:
        digest = digest or sha256_file(path)
        if digest == PRISTINE_SDAT_SHA256:
            return "pristine"
    return "unknown"


def backup_once(usrdir, name, journal, *, accepted=("pristine",), expected_sha256=None,
                progress=None):
    """Back up an original before the first replacement; never silently re-backup."""
    original = usrdir / name
    backup = usrdir / BACKUP_DIRNAME / name
    backups = journal.setdefault("backups", {})
    current = sha256_file(original, _report(progress, f"Checking {name}"))
    if name in backups:
        recorded = backups[name]["sha256"]
        require(backup.is_file(), f"Recorded backup for {name} is missing; refusing to continue")
        require(sha256_file(backup, _report(progress, f"Checking the {name} backup")) == recorded,
                f"Backup for {name} was modified; refusing to continue")
        if current == recorded:
            return backup
        # Already patched earlier and the file changed again: the backup stays the
        # only original, so reset to it before a new verified install.
        require(backup.stat().st_size <= free_bytes(usrdir), f"Not enough free space to restore {name}")
        copy_verified(backup, original, recorded, _report(progress, f"Restoring {name}"))
        return backup
    if expected_sha256 is not None:
        require(current == expected_sha256,
                f"{name} is not the file this patch was built for; restore your own dump first")
        kind = "pristine"
    else:
        kind = classify_sdat(original, current) if name == SDAT_NAME else "self"
    require(kind in accepted,
            f"{name} is not a file this tool will replace ({kind}). Restore your own dump first.")
    require(free_bytes(usrdir) >= original.stat().st_size * 2,
            f"Not enough free space to back up {name} ({original.stat().st_size} bytes) and install the new one")
    backup.parent.mkdir(parents=True, exist_ok=True)
    copy_verified(original, backup, current, _report(progress, f"Backing up {name}"))
    backups[name] = {"sha256": current, "size": original.stat().st_size, "kind": kind}
    return backup


def _report(progress, label):
    """Adapt a plain (done, total) callback to a labelled one."""
    if progress is None:
        return None
    return lambda done, total: progress(label, done, total)


def plan_install(build, usrdir, progress=None):
    usrdir = require_usrdir(usrdir)
    pair = staged_pair(build, _report(progress, "Checking the patch files"))
    journal = read_journal(usrdir) or {"schema_version": 2, "backups": {}, "installs": []}
    elf_current = sha256_file(usrdir / GAME_ELF_NAME, _report(progress, "Checking EBOOT.BIN"))
    elf_magic = magic(usrdir / GAME_ELF_NAME)
    require(elf_magic in (ELF_MAGIC, SELF_MAGIC),
            f"{GAME_ELF_NAME} is neither a PS3 SELF nor a decrypted ELF; refusing to replace it")
    actions = []
    if elf_current != pair["elf_sha256"]:
        actions.append({"file": GAME_ELF_NAME, "source": str(pair["elf"]),
                        "source_sha256": pair["elf_sha256"],
                        "current_sha256": elf_current,
                        "current_kind": "patched" if elf_magic == ELF_MAGIC else "retail SELF",
                        "backup": str(usrdir / BACKUP_DIRNAME / GAME_ELF_NAME)})
    sdat = None
    if pair["sdat"] is not None:
        target = usrdir / SDAT_NAME
        current = sha256_file(target, _report(progress, "Checking data.sdat")) if target.is_file() else None
        if current != pair["sdat_sha256"]:
            recorded = journal.get("backups", {}).get(SDAT_NAME)
            kind = classify_sdat(target, current)
            if kind == "unknown" and recorded is None:
                raise ValueError(
                    f"{SDAT_NAME} in {usrdir} is neither the pristine BLJM60381 archive nor a file "
                    "with a recorded backup; restore your own dump before patching")
            sdat = {"file": SDAT_NAME, "source": str(pair["sdat"]),
                    "source_sha256": pair["sdat_sha256"],
                    "current_sha256": current, "current_kind": kind,
                    "backup": str(usrdir / BACKUP_DIRNAME / SDAT_NAME),
                    "free_space_needed": (target.stat().st_size if target.is_file() else 0) +
                                         pair["sdat"].stat().st_size}
            actions.append(sdat)
    legacy = usrdir / LEGACY_ELF_NAME
    return {"usrdir": str(usrdir), "build": str(pair["build"]),
            "elf_source": str(pair["elf"]), "elf_sha256": pair["elf_sha256"],
            "sdat_source": str(pair["sdat"]) if pair["sdat"] else None,
            "sdat_sha256": pair["sdat_sha256"],
            "actions": actions, "nothing_to_do": not actions,
            "legacy_file_to_remove": str(legacy) if legacy.is_file() else None,
            "_journal": journal, "_pair": pair}


def public_plan(plan):
    """Strip the internal (non-JSON) planning state from a plan."""
    return {key: value for key, value in plan.items() if not key.startswith("_")}


def write_plan(plan, progress=None):
    """Perform an already checked install plan; the caller owns confirmation."""
    require("_journal" in plan and "_pair" in plan,
            "Install plan was not produced by plan_install()")
    require(not rpcs3_running(), "RPCS3 appears to be running; close it before patching")
    journal, pair = plan["_journal"], plan["_pair"]
    usrdir = Path(plan["usrdir"])
    journal["usrdir"] = str(usrdir)
    for action in plan["actions"]:
        if action["file"] == GAME_ELF_NAME:
            backup_once(usrdir, GAME_ELF_NAME, journal, accepted=("self",), progress=progress)
            copy_verified(pair["elf"], usrdir / GAME_ELF_NAME, pair["elf_sha256"],
                          _report(progress, "Installing EBOOT.BIN"))
        else:
            backup_once(usrdir, SDAT_NAME, journal, progress=progress)
            copy_verified(pair["sdat"], usrdir / SDAT_NAME, pair["sdat_sha256"],
                          _report(progress, "Installing data.sdat"))
    legacy = usrdir / LEGACY_ELF_NAME
    if legacy.is_file():
        legacy.unlink()
    journal["installs"].append({
        "build": str(pair["build"]),
        "installed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "elf_sha256": pair["elf_sha256"], "sdat_sha256": pair["sdat_sha256"],
        "elf_written_as": GAME_ELF_NAME,
        "boot": "Boot the game normally in RPCS3 (no separate ELF selection needed).",
        "save_data_modified": False,
    })
    journal.pop("restored_at", None)
    write_journal(usrdir, journal)
    result = public_plan(plan)
    result.update(applied=True, journal=str(journal_path(usrdir)))
    return result


def apply(build, usrdir=None, *, confirm=False, progress=None):
    plan = plan_install(build, usrdir or default_usrdir(), progress)
    if not confirm:
        result = public_plan(plan)
        result.update(dry_run=True,
                      next="Re-run with --apply to write; nothing was changed.")
        return result
    result = write_plan(plan, progress)
    result["dry_run"] = False
    return result


def plan_restore(usrdir=None, progress=None):
    """Check every recorded backup without writing anything."""
    usrdir = require_usrdir(usrdir or default_usrdir())
    journal = read_journal(usrdir)
    require(isinstance(journal, dict), "No patch journal; nothing recorded to restore")
    backups = journal.get("backups") or {}
    require(backups, "No backups recorded; nothing to restore")
    plan = {"usrdir": str(usrdir), "restore": {}, "removed": [],
            "_journal": journal, "_backups": backups}
    for name, info in backups.items():
        backup = usrdir / BACKUP_DIRNAME / name
        require(backup.is_file(), f"Backup missing for {name}; cannot restore")
        require(sha256_file(backup, _report(progress, f"Checking the {name} backup")) == info["sha256"],
                f"Backup for {name} was modified; refusing to restore")
        current = usrdir / name
        plan["restore"][name] = {"backup": str(backup), "sha256": info["sha256"],
                                 "size": info["size"],
                                 "current_sha256": sha256_file(current) if current.is_file() else None}
    legacy = usrdir / LEGACY_ELF_NAME
    if legacy.is_file():
        plan["removed"].append(str(legacy))
    return plan


def write_restore(plan, progress=None):
    """Copy the recorded backups back; the caller owns confirmation."""
    require("_journal" in plan and "_backups" in plan,
            "Restore plan was not produced by plan_restore()")
    require(not rpcs3_running(), "RPCS3 appears to be running; close it before restoring")
    usrdir, journal = Path(plan["usrdir"]), plan["_journal"]
    for name, info in plan["_backups"].items():
        copy_verified(usrdir / BACKUP_DIRNAME / name, usrdir / name, info["sha256"],
                      _report(progress, f"Restoring {name}"))
    legacy = usrdir / LEGACY_ELF_NAME
    if legacy.is_file():
        legacy.unlink()
    journal["restored_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    journal["installs"] = []
    write_journal(usrdir, journal)
    result = public_plan(plan)
    result.update(restored=True)
    return result


def restore(usrdir=None, *, confirm=False, progress=None):
    plan = plan_restore(usrdir, progress)
    if not confirm:
        result = public_plan(plan)
        result.update(dry_run=True,
                      next="Re-run with --apply to restore; nothing was changed.")
        return result
    result = write_restore(plan, progress)
    result["dry_run"] = False
    return result


def status(usrdir=None, progress=None):
    usrdir = require_usrdir(usrdir or default_usrdir())
    journal = read_journal(usrdir)
    files = {}
    for name in (GAME_ELF_NAME, LEGACY_ELF_NAME, SDAT_NAME):
        path = usrdir / name
        files[name] = None
        if path.is_file():
            if name == SDAT_NAME:
                kind = "archive"
            else:
                kind = {ELF_MAGIC: "ELF", SELF_MAGIC: "SELF"}.get(magic(path), "unknown")
            files[name] = {"size": path.stat().st_size,
                           "sha256": sha256_file(path, _report(progress, f"Checking {name}")),
                           "kind": kind}
    backups = {}
    for name in (GAME_ELF_NAME, SDAT_NAME):
        path = usrdir / BACKUP_DIRNAME / name
        backups[name] = ({"size": path.stat().st_size,
                          "sha256": sha256_file(path, _report(progress, f"Checking the {name} backup"))}
                         if path.is_file() else None)
    installed = None
    if isinstance(journal, dict) and journal.get("installs"):
        installed = journal["installs"][-1]
    sdat_path = usrdir / SDAT_NAME
    sdat_kind = classify_sdat(sdat_path, files[SDAT_NAME]["sha256"] if files[SDAT_NAME] else None)
    return {"usrdir": str(usrdir),
            "installed_elf_matches_journal": bool(
                installed and files[GAME_ELF_NAME] and
                files[GAME_ELF_NAME]["sha256"] == installed.get("elf_sha256")),
            "sdat_is_pristine": sdat_kind == "pristine",
            "sdat_kind": sdat_kind,
            "files": files, "backups": backups, "last_install": installed,
            "rpcs3_running": rpcs3_running(), "emulator_launched_by_tool": False}


def default_usrdir():
    """Accept the game folder, PS3_GAME or USRDIR itself."""
    candidates = []
    configured = tool_root() / "project.json"
    if configured.is_file():
        try:
            candidates.append(Path(load_json(configured)["game_usrdir"]))
        except (OSError, ValueError, KeyError):
            pass
    candidates.extend((tool_root() / "PS3_GAME/USRDIR", tool_root() / "USRDIR",
                       tool_root() / ".." / "PS3_GAME/USRDIR"))
    for candidate in candidates:
        try:
            return resolve_usrdir(candidate)
        except ValueError:
            continue
    raise ValueError("Cannot find the game USRDIR; pass --game-dir <.../PS3_GAME/USRDIR>")


def utf8_console():
    """Keep help/JSON printable on a Japanese-locale console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    utf8_console()
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "apply", "restore"):
        command = sub.add_parser(name)
        command.add_argument("--game-dir", type=Path, default=None,
                             help="Target PS3_GAME/USRDIR; detected next to the tool when omitted")
        if name != "status":
            command.add_argument("--apply", action="store_true", dest="confirm",
                                 help="Write changes; without it the command only reports")
        if name == "apply":
            command.add_argument("--build", type=Path, default=None,
                                 help="Directory with EBOOT.elf, data.sdat and EBOOT.report.json")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(status(args.game_dir), ensure_ascii=False, indent=2))
        return 0
    if args.command == "apply":
        build = args.build or default_build()
        result = apply(build, args.game_dir, confirm=args.confirm)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    result = restore(args.game_dir, confirm=args.confirm)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    utf8_console()
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"ERROR: {error}")
