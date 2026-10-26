"""Local PS3 scenario workflow; no emulator launch or installed-game writes."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import re
import struct
import subprocess
import sys
import tempfile
import scenario_source
import text_layout

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))
SOURCE = ROOT / CONFIG["source_eboot"]
BASELINE = ROOT / CONFIG["baseline_dir"]
SCRIPTS = ROOT / CONFIG["script_dir"]
KIT = ROOT / "vendor/TH2DXP_KIT/scenario_eboot_tool.py"
# The source-bound choice scanner imports project; initialize paths first.
import choice_text

# Native 6E34C..6E8C4: backslash controls, angle tags, and dynamic
# first/last/nickname or *h2 substitutions (optional kana/length selector).
_ENGINE_CONTROLS = re.compile(
    r"\\p[0-9A-Fa-f]{4}|\\[\s\S]|\\$|<[^>]*(?:>|$)|\*n[fln]k?[1-6]?|\*h2[1-6]?"
)


def engine_controls(text):
    return _ENGINE_CONTROLS.findall(text)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def source_bytes():
    data = SOURCE.read_bytes()
    if len(data) != CONFIG["source_size"] or digest(data) != CONFIG["source_sha256"]:
        raise ValueError("Source EBOOT does not match project.json; refusing another revision or patched input")
    return data


def codec():
    spec = importlib.util.spec_from_file_location("th2dxp_scenario", KIT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def baseline():
    meta = load(BASELINE / "scenario_meta.json")
    if meta["source_eboot_sha256"] != CONFIG["source_sha256"] or meta["encoding"] != CONFIG["encoding"]:
        raise ValueError("Baseline provenance/encoding mismatch")
    if meta.get("container_codec") != "complete-chunks-v1":
        raise ValueError("Baseline omits continuation scenarios; run tools/project.py recover before building")
    for entry in meta["entries"]:
        if entry["text_count"]:
            path = BASELINE / entry["json_filename"]
            if digest(path.read_bytes()) != entry["json_sha256"]:
                raise ValueError(f"Baseline changed: {path}; restore from the original EBOOT")
    choice_text.baseline()
    return meta


def extract_complete(destination, *, data=None, source_path=None):
    if data is None:
        data = source_bytes()
    if source_path is None:
        source_path = SOURCE
    kit = codec()
    entries = []
    destination.mkdir(parents=True, exist_ok=True)
    for entry, payload, source_name, chunks in scenario_source.scan(data, kit):
        records = kit.read_text_records_structured(payload, CONFIG["encoding"], None)
        units = kit.make_structured_units(payload, records, include_offsets=False,
                                         encoding=CONFIG["encoding"], font_table=None, decode_gaps=False)
        entry.text_count = len(units)
        row = dict(vars(entry), source_name=source_name, chunks=chunks)
        if units:
            path = destination / entry.json_filename
            save(path, units)
            row["json_sha256"] = digest(path.read_bytes())
        entries.append(row)
    meta = {"tool": "th2dxplus-project", "container_codec": "complete-chunks-v1",
            "source_eboot": str(source_path), "source_eboot_size": len(data),
            "source_eboot_sha256": digest(data), "table_start": scenario_source.TABLE_START,
            "encoding": CONFIG["encoding"], "extraction_mode": "structured_json",
            "hash_algorithm": "sha256", "font_tbl": None, "entries": entries}
    save(destination / "scenario_meta.json", meta)
    return meta


def extract():
    if SCRIPTS.exists() or BASELINE.exists():
        raise ValueError("Existing workspace is never overwritten; use recover for an older incomplete extraction")
    extract_complete(BASELINE)
    shutil.copytree(BASELINE, SCRIPTS)
    choice_text.prepare()
    print(f"Editable scripts: {SCRIPTS}")


def recover():
    """Add omitted scenarios without replacing an existing translated_text."""
    old = load(BASELINE / "scenario_meta.json")
    if old["source_eboot_sha256"] != CONFIG["source_sha256"]:
        raise ValueError("Old baseline source identity mismatch")
    for entry in old["entries"]:
        if entry["text_count"] and digest((BASELINE / entry["json_filename"]).read_bytes()) != entry["json_sha256"]:
            raise ValueError(f"Old baseline changed: {entry['json_filename']}")
    validate(SCRIPTS, old, allow_growth=True)
    with tempfile.TemporaryDirectory(prefix="scenario-recovery-", dir=ROOT / "work") as temporary:
        staged = Path(temporary)
        meta = extract_complete(staged)
        files = list(staged.glob("script_*.json"))
        for path in files:
            existing = BASELINE / path.name
            if existing.exists() and existing.read_bytes() != path.read_bytes():
                raise ValueError(f"Recovery would alter existing provenance: {path.name}")
        added = []
        for path in files:
            if not (BASELINE / path.name).exists():
                shutil.copy2(path, BASELINE / path.name)
                if (SCRIPTS / path.name).exists():
                    raise ValueError(f"Untracked editable scenario already exists: {path.name}")
                shutil.copy2(path, SCRIPTS / path.name)
                added.append(path.name)
        save(BASELINE / "scenario_meta.json", meta)
        save(SCRIPTS / "scenario_meta.json", meta)
    report = {"scenario_entries": len(meta["entries"]), "editable_scripts": len(files),
              "added_scripts": added, "existing_translations_preserved": True}
    if not choice_text.baseline_dir().exists():
        choices = choice_text.prepare()
        report["added_choice_records"] = choices["choice_count"]
        report["added_choice_files"] = choices["script_count"]
    save(ROOT / "work/scenario-recovery.json", report)
    print(json.dumps(report, indent=2))


def validate(scripts, meta, *, allow_growth=False):
    paths = {e["json_filename"]: BASELINE / e["json_filename"] for e in meta["entries"] if e["text_count"]}
    if scripts.resolve() != BASELINE.resolve():
        paths.update({name: choice_text.baseline_dir() / name for name in choice_text.baseline()})
    expected = set(paths)
    actual = {p.name for p in scripts.glob("*.json")} - {"scenario_meta.json"}
    if expected != actual:
        raise ValueError(f"Script set changed: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
    if load(scripts / "scenario_meta.json") != meta:
        raise ValueError("Do not edit scenario_meta.json")
    changed = {}
    text_count = translated = 0
    for name in sorted(expected):
        original = load(paths[name])
        edited = load(scripts / name)
        if not isinstance(edited, list) or len(original) != len(edited):
            raise ValueError(f"{name}: unit count changed")
        restored = copy.deepcopy(edited)
        file_changed = False
        for ui, (before, after) in enumerate(zip(original, edited)):
            if not isinstance(after, dict) or not isinstance(after.get("items"), list) or len(before["items"]) != len(after["items"]):
                raise ValueError(f"{name}:{ui}: item structure changed")
            for ii, (old, new) in enumerate(zip(before["items"], after["items"])):
                if old["kind"] != "text":
                    continue
                text_count += 1
                value = new.get("translated_text") if isinstance(new, dict) else None
                if not isinstance(value, str):
                    raise ValueError(f"{name}:{ui}:{ii}: translated_text must be a string")
                restored[ui]["items"][ii]["translated_text"] = old["translated_text"]
                if value == old["translated_text"]:
                    continue
                where = f"{name}:{ui}:{ii}"
                if not value or any(ord(c) < 32 for c in value):
                    raise ValueError(f"{where}: blank text or literal control characters; preserve engine escapes")
                encoded = value.encode(CONFIG["encoding"], errors="strict")
                if encoded.decode(CONFIG["encoding"], errors="strict") != value:
                    raise ValueError(f"{where}: CP932 encoding would change the translated text")
                old_encoded = old["original_text"].encode(CONFIG["encoding"], errors="strict")
                if not allow_growth and len(encoded) > len(old_encoded):
                    raise ValueError(f"{where}: {len(encoded)} bytes exceeds original {len(old_encoded)}; complete manual engine acceptance is required")
                if engine_controls(value) != engine_controls(old["original_text"]):
                    raise ValueError(f"{where}: inline engine escapes changed")
                file_changed = True
                translated += 1
        if restored != original:
            raise ValueError(f"{name}: only text.translated_text may change; provenance/bytecode/order are immutable")
        if file_changed:
            changed[name] = edited
    return changed, {"editable_text_records": text_count, "changed_text_records": translated, "changed_scripts": len(changed)}


def verify_payloads(data, expected, meta, kit):
    headers = kit.read_elf_program_headers(data)
    for raw_entry in meta["entries"]:
        entry = kit.normalize_entry(raw_entry)
        # Read the output table, not the old metadata, so pointer/size errors are visible.
        off = meta["table_start"] + entry.entry_index * 16
        entry.data_ptr, entry.uncomp_size, entry.comp_size_table = struct.unpack_from(">III", data, off + 4)
        actual = scenario_source.read_entry(data, entry, kit, headers)
        wanted = expected.get(entry.json_filename, raw_entry["sha256_bin"])
        if digest(actual) != wanted or len(actual) != entry.uncomp_size:
            raise ValueError(f"Output payload verification failed: {entry.filename}")


def build(scripts, output, kit, meta, original, *, layout_columns=None, engine_growth=False):
    manual = None
    if engine_growth:
        import production_engine
        manual = production_engine.require_manual_acceptance()
        if layout_columns is not None:
            raise ValueError("The approved engine uses native VWF, not fixed-column compilation")
    changed, stats = validate(scripts, meta, allow_growth=engine_growth)
    layout_reports = {}
    if layout_columns is not None:
        for name, units in changed.items():
            changed[name], layout_reports[name] = text_layout.compile_units(
                units, columns=layout_columns, break_fragments=True)
    engine_report = None
    if engine_growth:
        data, engine_report = production_engine.rebuild_image(original, changed, kit, meta)
    else:
        data = bytearray(original)
        headers = kit.read_elf_program_headers(original)
        expected = {}
        entries = sorted(meta["entries"], key=lambda e: e["file_offset"])
        for index, raw_entry in enumerate(entries):
            name = raw_entry["json_filename"]
            choices = changed.get(choice_text.companion_name(name))
            if name not in changed and choices is None:
                continue
            entry = kit.normalize_entry(raw_entry)
            old = scenario_source.read_entry(original, entry, kit, headers)
            new = (kit.rebuild_scenario_from_structured_json(
                old, changed[name], encoding=CONFIG["encoding"], font_table=None, allow_growth=False)
                if name in changed else old)
            if choices is not None:
                new = choice_text.rebuild(new, choices, kit, allow_growth=False)
            chunk = scenario_source.pack(new, kit)
            start = entry.file_offset
            limit = entry.comp_size_table
            next_start = entries[index + 1]["file_offset"] if index + 1 < len(entries) else len(original)
            if start + limit > next_start or start + limit > len(original):
                raise ValueError(f"{name}: overlapping/out-of-bounds original slot")
            if len(chunk) > limit:
                raise ValueError(f"{name}: compressed chunk {len(chunk)} exceeds safe original slot {limit}; no relocation performed")
            data[start:start + len(chunk)] = chunk
            table = meta["table_start"] + entry.entry_index * 16
            struct.pack_into(">II", data, table + 8, len(new), len(chunk))
            expected[name] = digest(new)
        verify_payloads(bytes(data), expected, meta, kit)
    ui_assets = None
    if engine_growth:
        ui_assets = production_engine.stage_ui_archive(output.parent, engine_report)
    elif (output.parent / "data.sdat").exists():
        raise ValueError("An original-slot ELF must not be mixed with an existing staged data.sdat")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    report = {**stats, "source_sha256": digest(original), "output_sha256": digest(data), "output": str(output),
              "verified_scenario_payloads": len(meta["entries"]), "emulator_tested": False,
              "packing": "appended segment; original 64-byte allocations; native VWF/save preview" if engine_growth else "original fixed slots; unchanged pointers; no engine growth"}
    report["layout_compilation"] = layout_reports
    if engine_growth:
        report.update(engine=engine_report, manual_acceptance=manual, production_growth_enabled=True,
                      ui_assets=ui_assets)
    save(output.with_suffix(".report.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return bytes(data)


def identity(kit, meta, original):
    headers = kit.read_elf_program_headers(original)
    count = 0
    for raw_entry in meta["entries"]:
        if not raw_entry["text_count"]:
            continue
        entry = kit.normalize_entry(raw_entry)
        old = scenario_source.read_entry(original, entry, kit, headers)
        new = kit.rebuild_scenario_from_structured_json(old, load(BASELINE / entry.json_filename), encoding=CONFIG["encoding"], font_table=None, allow_growth=False)
        if old != new:
            raise ValueError(f"Codec roundtrip is not byte-identical: {entry.filename}")
        count += 1
    output = ROOT / "build/identity/EBOOT.elf"
    rebuilt = build(BASELINE, output, kit, meta, original)
    if rebuilt != original:
        raise ValueError("Identity EBOOT differs from source")
    print(f"PASS: {count} structured codec roundtrips; byte-identical identity EBOOT")


def smoke(kit, meta, original, *, engine_growth=False):
    # This is a diagnostic marker, not a translation claim. Editable work stays untouched.
    with tempfile.TemporaryDirectory(prefix="th2dxp-") as temporary:
        scripts = Path(temporary) / "script"
        choice_text.copy_baseline(scripts)
        chosen = None
        for entry in meta["entries"]:
            if not entry["text_count"]:
                continue
            path = scripts / entry["json_filename"]
            units = load(path)
            candidates = [
                (len(item["original_text"].encode(CONFIG["encoding"])), ui, ii)
                for ui, unit in enumerate(units)
                for ii, item in enumerate(unit["items"])
                if item["kind"] == "text" and not engine_controls(item["original_text"])
            ]
            if not candidates:
                continue
            size, ui, ii = max(candidates)
            if size < 16:
                continue
            item = units[ui]["items"][ii]
            item["translated_text"] = "[EN TEST] Hello."
            chosen = {"script": entry["json_filename"], "unit": ui, "item": ii, "marker": item["translated_text"]}
            save(path, units)
            break
        if not chosen:
            raise ValueError("No eligible marker text record")
        choice_baseline = choice_text.baseline()
        choice_marker = None
        for name, binding in sorted(choice_baseline.items()):
            view = load(scripts / name)
            candidates = [(len(unit["items"][0]["original_text"].encode(CONFIG["encoding"])), ui)
                          for ui, unit in enumerate(view)
                          if not engine_controls(unit["items"][0]["original_text"])]
            if not candidates or max(candidates)[0] < 16:
                continue
            _, ui = max(candidates)
            view[ui]["items"][0]["translated_text"] = "[EN CHOICE] Go."
            save(scripts / name, view)
            choice_marker = {"script": binding["script"], "choice_script": name,
                             "unit": ui, "marker": "[EN CHOICE] Go."}
            break
        if choice_baseline and choice_marker is None:
            raise ValueError("No eligible native choice marker")
        output = ROOT / "build/smoke/EBOOT.elf"
        if choice_marker is not None and not engine_growth:
            # An English choice can exceed the old compressed slot even when
            # its own record shrinks. Exercise the real appended engine in a
            # separate diagnostic, never shorten the fixture or enable production.
            import production_engine
            changed, stats = validate(scripts, meta, allow_growth=True)
            rebuilt, engine = production_engine.rebuild_image(original, changed, kit, meta)
            output.parent.mkdir(parents=True, exist_ok=True)
            ui_assets = production_engine.stage_ui_archive(output.parent, engine)
            output.write_bytes(rebuilt)
            save(output.with_suffix(".report.json"), {
                **stats, "source_sha256": digest(original), "output_sha256": digest(rebuilt),
                "output": str(output), "engine": engine, "ui_assets": ui_assets, "diagnostic_only": True,
                "verified_scenario_payloads": len(meta["entries"]),
                "runtime_verified": False, "production_growth_enabled": False})
        else:
            rebuilt = build(scripts, output, kit, meta, original, engine_growth=engine_growth)
        if rebuilt == original:
            raise ValueError("Marker did not change the executable")
        # Re-extract every scenario, including continuation chunks omitted upstream.
        extracted = Path(temporary) / "extracted"
        extracted_meta = extract_complete(extracted, data=rebuilt, source_path=output)
        observed = load(extracted / chosen["script"])[chosen["unit"]]["items"][chosen["item"]]["original_text"]
        if observed != chosen["marker"]:
            raise ValueError(f"Marker extraction mismatch: {observed!r}")
        if choice_marker is not None:
            entry = kit.normalize_entry(next(row for row in extracted_meta["entries"]
                                            if row["json_filename"] == choice_marker["script"]))
            payload = scenario_source.read_entry(rebuilt, entry, kit)
            if choice_text.records(payload, kit)[choice_marker["unit"]]["text"] != choice_marker["marker"]:
                raise ValueError("Native choice marker extraction mismatch")
            chosen["choice_marker"] = choice_marker
        save(ROOT / "build/smoke/marker.json", chosen)
        print("PASS: English message/choice markers re-extracted; every other scenario payload preserved")
        print(json.dumps(chosen, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["extract", "extract-choices", "recover", "check", "build", "identity", "smoke"])
    parser.add_argument("--engine-growth", action="store_true",
                        help="Require full manual acceptance and the staged native/capacity cutover")
    args = parser.parse_args()
    if args.engine_growth and args.command not in ("check", "build", "smoke"):
        parser.error("--engine-growth applies only to check/build/smoke")
    if args.command == "extract":
        extract()
        return
    if args.command == "extract-choices":
        choices = choice_text.prepare()
        print(json.dumps({"choice_count": choices["choice_count"], "script_count": choices["script_count"],
                          "immutable_baseline": str(choice_text.baseline_dir()),
                          "existing_files_modified": False}, indent=2))
        return
    if args.command == "recover":
        recover()
        return
    engine_growth = False
    if args.command in ("check", "build", "smoke"):
        import production_engine
        engine_growth = args.engine_growth or production_engine.evidence_present()
        if engine_growth and args.command in ("check", "smoke"):
            production_engine.require_manual_acceptance()
    original = source_bytes()
    kit = codec()
    meta = baseline()
    if args.command == "check":
        _, stats = validate(SCRIPTS, meta, allow_growth=engine_growth)
        print(json.dumps(stats, indent=2))
    elif args.command == "build":
        build(SCRIPTS, ROOT / CONFIG["output_eboot"], kit, meta, original, engine_growth=engine_growth)
    elif args.command == "identity":
        identity(kit, meta, original)
    elif args.command == "smoke":
        smoke(kit, meta, original, engine_growth=engine_growth)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"ERROR: {error}")
