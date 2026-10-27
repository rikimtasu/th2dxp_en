"""Install the English patch from the game folder alone.

The release ships patch *data*, not a pre-patched game: an executable diff, one
pre-compressed archive chunk per rewritten table row, and a manifest of the
hashes on both ends. This module turns that into an installed patch:

1. check the folder holds the pristine BLJM60381 executable and archive,
2. back both up once under ``.th2dxp-backup`` (hash recorded),
3. decrypt ``EBOOT.BIN``, apply the diff and verify the pinned patched hash,
4. decrypt ``data.sdat``, append the chunks, rewrite the rows, re-encrypt and
   authenticate the new archive against its pinned hash,
5. swap both files into place and record the install in the journal.

Nothing is installed until both rebuilt files exist and match their pinned
hashes, so a failure leaves the installed game untouched. RPCS3 is never
started, saves are never touched, and the decrypted intermediate files live in
``.th2dxp-work`` inside the game folder, on the same volume as the files they
replace.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import patch_data
import patch_game
import ps3_self

ROOT = Path(__file__).resolve().parents[1]
WORK_DIRNAME = ".th2dxp-work"
DECRYPTOR = "make_npdata.exe"
PACKER = "make_npdata-pack.exe"
#: The two helpers are pinned: they are the exact binaries that produced v0.1.
DECRYPTOR_SHA256 = "662fd552ed91e6742f0dead3f66cf7e559782a983b9f453a781e22a138f57fac"
PACKER_SHA256 = "81c2cd3a2c4d4a04801b28666c7e2d7cfa00ebe83fa67d47d58b2f2366b510b7"
SLACK = 256 * 1024 * 1024
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

require = patch_game.require


def _labelled(progress, label):
    if progress is None:
        return None
    return lambda done, total: progress(label, done, total)


def _stage(progress, label):
    if progress is not None:
        progress(label, 0, 0)


def search_roots():
    """Where the two archive helpers may live, most specific first."""
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "tools")
        roots.append(Path(sys.executable).resolve().parent / "tools")
    roots += [patch_game.tool_root() / "tools", ROOT / "work",
              ROOT / "work/make_npdata-pack", patch_game.tool_root()]
    unique = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def find_tools():
    """Return the pinned decryptor and packer, refusing any other build."""
    found = {}
    for name in (DECRYPTOR, PACKER):
        for root in search_roots():
            candidate = Path(root) / name
            if candidate.is_file():
                found[name] = candidate
                break
        require(name in found,
                f"The bundled {name} helper is missing; download the release again")
    require(patch_game.sha256_file(found[DECRYPTOR]) == DECRYPTOR_SHA256,
            f"{found[DECRYPTOR]} is not the pinned make_npdata build")
    require(patch_game.sha256_file(found[PACKER]) == PACKER_SHA256,
            f"{found[PACKER]} is not the pinned archive packer")
    return found[DECRYPTOR], found[PACKER]


def _invoke(command, *, expect, label):
    """Run one helper, keep its output, and turn any failure into a ValueError."""
    completed = subprocess.run(command, capture_output=True, text=True, check=False,
                               creationflags=NO_WINDOW)
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode or any(message not in output for message in expect):
        tail = " | ".join(line.strip() for line in output.strip().splitlines()[-3:] if line.strip())
        raise ValueError(f"{label} failed (exit {completed.returncode}): {tail or 'no output'}")
    return output


def _free(path):
    return shutil.disk_usage(str(path)).free


def format_size(size):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def default_patch_dir(start=None):
    """Find the one obvious patch folder, never guess between several."""
    if start is not None:
        for candidate in (Path(start) / "patch-data", Path(start)):
            if (candidate / patch_data.MANIFEST_NAME).is_file():
                return candidate
        raise ValueError(f"No patch data found under {start}")
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
    roots += [patch_game.tool_root(), ROOT / "build" / "patch-data-v0.1"]
    for root in roots:
        for candidate in (root / "patch-data", root):
            if (candidate / patch_data.MANIFEST_NAME).is_file():
                return candidate
    raise ValueError("No patch data found; expected a 'patch-data' folder with manifest.json "
                     "next to this program")


def space_needed(plan):
    """Peak additional bytes: the backup, then the DAT, then the new archive.

    The decrypted DAT is deleted before the archive is re-encrypted, and the
    re-extracted copy used for the round-trip check replaces it, so the two large
    plaintext files never coexist.
    """
    elf_spec, archive_spec = plan["_manifest"]["elf"], plan["_manifest"]["archive"]
    needed = 0
    if plan["elf"]["install"]:
        needed = max(needed, elf_spec["output_size"] + 32 * 1024 * 1024)
    if plan["archive"]["install"]:
        backup = 0 if plan["archive"]["backup_recorded"] else archive_spec["source_sdat_size"]
        during_patch = backup + archive_spec["source_dat_size"] + archive_spec["output_dat_size"]
        during_encrypt = backup + archive_spec["output_dat_size"] + archive_spec["output_sdat_size"]
        during_roundtrip = backup + archive_spec["output_sdat_size"] + archive_spec["output_dat_size"]
        needed = max(needed, during_patch, during_encrypt, during_roundtrip)
    return needed + SLACK if needed else 0


def classify_archive(current, spec, journal):
    """Name what ``data.sdat`` is now, without trusting only the patch data.

    Re-encrypting an archive rewrites NPD header hashes computed over the input
    file's path (``forge_npd_title_hash``), so a locally rebuilt archive never
    matches the reference hash of the build that produced the patch data. The
    journal is therefore what proves "this is my installed archive".
    """
    if current == spec["source_sdat_sha256"]:
        return "pristine"
    recorded = {row.get("sdat_sha256") for row in journal.get("installs", [])
                if isinstance(row, dict)}
    backup = journal.get("backups", {}).get(patch_game.SDAT_NAME)
    if backup and current == backup.get("sha256"):
        return "pristine"
    if current in recorded or current == spec.get("output_sdat_sha256"):
        return "patched"
    return "unknown"


def plan(build, usrdir, progress=None):
    """Check one folder against the patch data without writing anything."""
    usrdir = patch_game.require_usrdir(usrdir)
    build = Path(build).resolve()
    manifest = patch_data.load_manifest(build)
    elf_spec, archive_spec = manifest["elf"], manifest["archive"]
    require("header" in archive_spec and "output_sdat_sha256" in archive_spec
            and "source_sdat_sha256" in archive_spec,
            "This patch data is incomplete; download the release again")
    journal = patch_game.read_journal(usrdir)
    if not isinstance(journal, dict):
        journal = {"schema_version": 3, "backups": {}, "installs": []}
    journal.setdefault("backups", {})
    journal.setdefault("installs", [])

    elf_path = usrdir / patch_game.GAME_ELF_NAME
    sdat_path = usrdir / patch_game.SDAT_NAME
    blocked = []
    elf = {"current_kind": "missing", "current_sha256": None,
           "output_sha256": elf_spec["output_sha256"], "install": False}
    archive = {"current_kind": "missing", "current_sha256": None,
               "output_sha256": archive_spec["output_sdat_sha256"], "install": False,
               "backup_recorded": bool(journal["backups"].get(patch_game.SDAT_NAME))}
    if not elf_path.is_file():
        blocked.append(f"{patch_game.GAME_ELF_NAME} is missing from {usrdir}")
    else:
        magic = patch_game.magic(elf_path)
        elf["current_kind"] = {patch_game.ELF_MAGIC: "ELF",
                               patch_game.SELF_MAGIC: "SELF"}.get(magic, "unknown")
        elf["current_sha256"] = patch_game.sha256_file(
            elf_path, _labelled(progress, f"Checking {patch_game.GAME_ELF_NAME}"))
        elf["install"] = elf["current_sha256"] != elf["output_sha256"]
        if elf["install"] and elf["current_kind"] == "unknown":
            blocked.append(f"{patch_game.GAME_ELF_NAME} is not a PS3 executable this tool recognises")
        elif elf["install"] and elf["current_kind"] == "ELF" \
                and elf["current_sha256"] != elf_spec["source_sha256"]:
            blocked.append(f"{patch_game.GAME_ELF_NAME} is a patched executable from another "
                           "build; restore the original first")
    if not sdat_path.is_file():
        blocked.append(f"{patch_game.SDAT_NAME} is missing from {usrdir}")
    else:
        archive["current_sha256"] = patch_game.sha256_file(
            sdat_path, _labelled(progress, f"Checking {patch_game.SDAT_NAME}"))
        archive["current_kind"] = classify_archive(archive["current_sha256"], archive_spec,
                                                   journal)
        archive["install"] = archive["current_kind"] != "patched"
        if archive["install"] and archive["current_kind"] == "unknown":
            blocked.append(
                f"{patch_game.SDAT_NAME} is neither the pristine BLJM60381 archive nor a file "
                "this tool installed. Restore your own dump (or use 'Restore original') first.")

    backups = {}
    for name in (patch_game.GAME_ELF_NAME, patch_game.SDAT_NAME):
        info = journal["backups"].get(name)
        path = usrdir / patch_game.BACKUP_DIRNAME / name
        backups[name] = ({"size": path.stat().st_size, "sha256": info["sha256"]}
                         if info and path.is_file() else None)
    result = {"usrdir": str(usrdir), "build": str(build), "patch": manifest.get("patch", {}),
              "elf": elf, "archive": archive, "blocked": blocked,
              "backups": backups,
              "last_install": journal["installs"][-1] if journal["installs"] else None,
              "nothing_to_do": not elf["install"] and not archive["install"],
              "free_space_available": _free(usrdir),
              "_journal": journal, "_manifest": manifest, "_build": build}
    result["free_space_needed"] = space_needed(result)
    if result["free_space_needed"] > result["free_space_available"]:
        blocked.append(
            f"Not enough free space in {usrdir}: about "
            f"{format_size(result['free_space_needed'])} is needed, "
            f"{format_size(result['free_space_available'])} is free")
    return result


def public_plan(plan):
    return {key: value for key, value in plan.items() if not key.startswith("_")}


def apply(plan, progress=None):
    """Perform a checked plan; the caller owns confirmation."""
    require(isinstance(plan.get("_manifest"), dict) and isinstance(plan.get("_journal"), dict),
            "Install plan was not produced by plan()")
    require(not plan["blocked"], "Cannot install: " + "; ".join(plan["blocked"]))
    require(not plan["nothing_to_do"],
            "Nothing to do: this folder already matches the patch data")
    require(not patch_game.rpcs3_running(), "RPCS3 appears to be running; close it before patching")

    usrdir = Path(plan["usrdir"])
    build = Path(plan["_build"])
    journal = plan["_journal"]
    manifest = plan["_manifest"]
    elf_spec, archive_spec = manifest["elf"], manifest["archive"]
    decryptor, packer = find_tools()
    work = usrdir / WORK_DIRNAME
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    journal["usrdir"] = str(usrdir)
    installed = {"elf": False, "sdat": False}
    try:
        if plan["elf"]["install"]:
            _stage(progress, f"Backing up {patch_game.GAME_ELF_NAME}")
            patch_game.backup_once(usrdir, patch_game.GAME_ELF_NAME, journal,
                                   accepted=("self",), progress=progress)
        if plan["archive"]["install"]:
            _stage(progress, f"Backing up {patch_game.SDAT_NAME}")
            patch_game.backup_once(usrdir, patch_game.SDAT_NAME, journal,
                                   expected_sha256=archive_spec["source_sdat_sha256"],
                                   progress=progress)
        # The backups are recorded before any rebuilt file exists.
        patch_game.write_journal(usrdir, journal)

        if plan["elf"]["install"]:
            source = usrdir / patch_game.GAME_ELF_NAME
            if plan["elf"]["current_kind"] == "SELF":
                _stage(progress, "Decrypting EBOOT.BIN")
                pristine = work / "pristine.elf"
                ps3_self.decrypt_file(source, pristine,
                                      expected_sha256=elf_spec["source_sha256"])
                source = pristine
            _stage(progress, "Applying the executable patch")
            patch_data.apply_elf_patch(source, work / patch_game.GAME_ELF_NAME, build, elf_spec)
            if source != usrdir / patch_game.GAME_ELF_NAME:
                source.unlink()

        if plan["archive"]["install"]:
            decrypted, patched = work / "data.dat", work / "data-patched.dat"
            _stage(progress, "Decrypting data.sdat")
            _invoke([str(decryptor), "-v", "-d", str(usrdir / patch_game.SDAT_NAME),
                     str(decrypted), "0"],
                    expect=("File successfully parsed!", "File successfully decrypted!"),
                    label="Decrypting data.sdat")
            require(patch_game.sha256_file(decrypted) == archive_spec["source_dat_sha256"],
                    "The decrypted archive does not match the pristine BLJM60381 DAT")
            _stage(progress, "Patching the archive")
            patch_data.apply_archive_patch(decrypted, patched, build, archive_spec,
                                           progress=_labelled(progress, "Patching the archive"))
            decrypted.unlink()
            _stage(progress, "Encrypting data.sdat")
            header = archive_spec["header"]
            built = work / patch_game.SDAT_NAME
            _invoke([str(packer), "-v", "-e", str(patched), str(built),
                     str(header["version"]), "0", str(header["type"]), "1",
                     header["content_id"], "0"],
                    expect=("File successfully encrypted!", "File successfully forged!"),
                    label="Encrypting data.sdat")
            patched.unlink()
            _stage(progress, "Authenticating the new archive")
            _invoke([str(packer), "--verify", str(built)],
                    expect=("authenticated!",), label="Authenticating the new archive")
            built_hash = _check_rebuilt_archive(built, archive_spec, decryptor, work,
                                                progress)

        legacy = usrdir / patch_game.LEGACY_ELF_NAME
        if legacy.is_file():
            legacy.unlink()
        if plan["elf"]["install"]:
            _stage(progress, "Installing EBOOT.BIN")
            os.replace(work / patch_game.GAME_ELF_NAME, usrdir / patch_game.GAME_ELF_NAME)
            installed["elf"] = True
        if plan["archive"]["install"]:
            _stage(progress, "Installing data.sdat")
            os.replace(work / patch_game.SDAT_NAME, usrdir / patch_game.SDAT_NAME)
            installed["sdat"] = True
        _stage(progress, "Checking the installed files")
        require(patch_game.sha256_file(usrdir / patch_game.GAME_ELF_NAME)
                == elf_spec["output_sha256"],
                f"Installed {patch_game.GAME_ELF_NAME} does not match the pinned executable")
        if installed["sdat"]:
            require(patch_game.sha256_file(usrdir / patch_game.SDAT_NAME) == built_hash,
                    f"Installed {patch_game.SDAT_NAME} does not match the verified rebuild")
        journal["installs"].append({
            "mode": "self-contained",
            "patch_version": (manifest.get("patch") or {}).get("version", "unknown"),
            "installed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "elf_sha256": elf_spec["output_sha256"],
            "sdat_sha256": built_hash if installed["sdat"] else plan["archive"]["current_sha256"],
            "sdat_dat_sha256": archive_spec["output_dat_sha256"],
            "elf_written_as": patch_game.GAME_ELF_NAME,
            "boot": "Boot the game normally in RPCS3 (no separate ELF selection needed).",
            "save_data_modified": False,
        })
        journal.pop("restored_at", None)
        patch_game.write_journal(usrdir, journal)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    result = public_plan(plan)
    result.update(applied=True, installed=installed,
                  journal=str(patch_game.journal_path(usrdir)))
    return result


def _check_rebuilt_archive(built, spec, decryptor, work, progress):
    """Prove the new archive holds exactly the pinned DAT, then return its hash.

    The pinned SHA-256 of the reference ``data.sdat`` cannot be matched: the NPD
    header carries hashes computed over the *path string* of the input DAT, so a
    rebuild is content-identical but byte-different from the build machine's
    archive. Re-extracting the rebuilt archive and comparing the DAT is the
    check that actually matters.
    """
    header = patch_data.read_sdat_header(built)
    require(built.stat().st_size == spec["output_sdat_size"],
            f"The rebuilt archive is {built.stat().st_size} bytes, "
            f"not the expected {spec['output_sdat_size']}")
    for field in ("version", "license", "type", "content_id", "block_size"):
        require(header[field] == spec["header"][field],
                f"The rebuilt archive changed its {field}")
    require(header["dat_size"] == spec["output_dat_size"],
            "The rebuilt archive declares the wrong archive length")
    _stage(progress, "Reading the new archive back")
    roundtrip = work / "roundtrip.dat"
    _invoke([str(decryptor), "-v", "-d", str(built), str(roundtrip), "0"],
            expect=("File successfully parsed!", "File successfully decrypted!"),
            label="Reading the new archive back")
    try:
        actual = patch_game.sha256_file(roundtrip)
    finally:
        roundtrip.unlink(missing_ok=True)
    require(actual == spec["output_dat_sha256"],
            "The rebuilt archive does not contain the patched data "
            f"(reads back as {actual}, expected {spec['output_dat_sha256']})")
    return patch_game.sha256_file(built)


def install(build, usrdir=None, *, confirm=False, progress=None):
    """Plan, then apply when ``confirm`` is true; a dry run writes nothing."""
    plan_result = plan(build, usrdir or patch_game.default_usrdir(), progress)
    if not confirm:
        result = public_plan(plan_result)
        result.update(dry_run=True,
                      next="Re-run with --apply to write; nothing was changed.")
        return result
    result = apply(plan_result, progress)
    result["dry_run"] = False
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Install the English patch into a game folder.")
    parser.add_argument("--game", help="the game folder, PS3_GAME or USRDIR")
    parser.add_argument("--patch", help="the folder with the patch data (manifest.json)")
    parser.add_argument("--apply", action="store_true", help="write the patch")
    args = parser.parse_args(argv)
    try:
        build = args.patch or default_patch_dir()
        result = install(build, args.game or patch_game.default_usrdir(), confirm=args.apply,
                         progress=lambda label, done, total: print(label, flush=True))
    except ValueError as error:
        print(f"ERROR: {error}", flush=True)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
