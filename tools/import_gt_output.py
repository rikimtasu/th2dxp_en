"""Validate LinguaGacha gt_output and optionally write it into script/.

Rows come from one export subset written by ``tools/linguagacha_export.py``.
Every row must still describe the same native fragment in the same order, so a
count, control, encoding or blank-carrier change fails the whole file before
anything is written. ``--write`` updates only ``translated_text`` in ``script/``;
it never touches baselines, builds, the installed game or saves.

    python -X utf8 tools/import_gt_output.py --check
    python -X utf8 tools/import_gt_output.py --write
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import choice_text
import project

DEFAULT_EXPORT = project.ROOT / "work/linguagacha-original"
SUBSETS = ("base-game", "all-original")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def baseline_units(script):
    """Read the immutable original for a message script or a choice companion."""
    directory = choice_text.baseline_dir() if script.endswith("_choices.json") else project.BASELINE
    return project.load(directory / script)


def private_glyphs(text):
    return [character for character in text if 0xE000 <= ord(character) <= 0xF8FF]


def check_rows(rows, records, script, units=None):
    """Return (defects, translated_texts) for one file; defects block all writes."""
    if not isinstance(rows, list):
        return [f"{script}: Message-JSON must be an array"], []
    if len(rows) != len(records):
        return [f"{script}: {len(rows)} rows for {len(records)} native items; row count changed"], []
    units = baseline_units(script) if units is None else units
    defects, values = [], []
    for row, record in zip(rows, records):
        where = record["record_id"]
        if not isinstance(row, dict) or set(row) != {"name", "message"}:
            defects.append(f"{where}: expected exactly name/message fields")
            values.append(None)
            continue
        if row["name"] != "":
            defects.append(f"{where}: speaker name is unverified; keep name empty")
        value = row["message"]
        if not isinstance(value, str):
            defects.append(f"{where}: message must be a string")
            values.append(None)
            continue
        values.append(value)
        item = units[record["unit"]]["items"][record["item"]]
        require(item.get("kind") == "text", f"{where}: sidecar does not point at a text item")
        original = item["original_text"]
        if not isinstance(value, str) or any(ord(character) < 32 for character in value):
            defects.append(f"{where}: literal control character or non-string message")
            continue
        try:
            encoded = value.encode("cp932", errors="strict")
        except UnicodeEncodeError:
            bad = sorted({character for character in value
                          if not character.encode("cp932", errors="ignore")})
            defects.append(f"{where}: not representable in CP932 ({' '.join(bad[:6])})")
            continue
        if encoded.decode("cp932", errors="strict") != value:
            defects.append(f"{where}: CP932 encoding would change the text")
            continue
        if not original.strip():
            if value != original:
                defects.append(f"{where}: original blank carrier changed")
            continue
        if not value.strip():
            defects.append(f"{where}: readable source text was deleted")
            continue
        if project.engine_controls(value) != project.engine_controls(original):
            defects.append(f"{where}: ordered inline engine controls moved or changed")
        if private_glyphs(value) != private_glyphs(original):
            defects.append(f"{where}: private-use glyphs changed")
    return defects, values


def load_export(export, subset):
    export = Path(export)
    # Paths inside the project resolve relative to the repository root so the
    # command works from any directory; absolute paths are accepted as-is.
    if not export.is_absolute():
        export = (project.ROOT / export).resolve()
    require(export.is_dir(), f"Export directory not found: {export}")
    require(subset in SUBSETS, f"Unknown subset: {subset}")
    manifest = project.load(export / "metadata/manifest.json")
    require(manifest.get("format") == "LinguaGacha Message-JSON", "Export manifest has an unexpected format")
    records = {path.stem: project.load(path)
               for path in sorted((export / "metadata/records").glob("*.json"))}
    outputs = sorted((export / subset / "gt_output").glob("*.json"))
    require(outputs, f"No translated files in {export / subset / 'gt_output'}")
    return manifest, records, outputs


def run(export, subset, *, write):
    manifest, records, outputs = load_export(export, subset)
    defects, per_file, translated_files, untranslated_rows = [], {}, 0, 0
    pending = {}
    for path in outputs:
        sidecar = records.get(path.stem)
        if sidecar is None:
            defects.append(f"{path.name}: no sidecar; not produced by this export")
            continue
        script = sidecar["script"]
        rows = project.load(path)
        baseline = baseline_units(script)
        problems, values = check_rows(rows, sidecar["records"], script, baseline)
        unchanged = sum(1 for record, value in zip(sidecar["records"], values)
                        if value is not None and
                        value == baseline[record["unit"]]["items"][record["item"]]["original_text"])
        if unchanged:
            untranslated_rows += unchanged
        defects.extend(problems)
        if problems:
            per_file[path.name] = {"defects": len(problems), "written": False}
            continue
        units = baseline
        changed = 0
        for record, value in zip(sidecar["records"], values):
            item = units[record["unit"]]["items"][record["item"]]
            if value != item.get("translated_text"):
                item["translated_text"] = value
                changed += 1
        per_file[path.name] = {"translated_text_rows": len(rows), "changed": changed,
                               "target": script, "written": bool(write and changed)}
        if changed:
            translated_files += 1
            pending[script] = units
    report = {"subset": subset, "files": len(outputs), "files_with_changes": translated_files,
              "blocked_files": sum(1 for entry in per_file.values() if entry.get("defects")),
              "rows_still_original": untranslated_rows,
              "defect_count": len(defects), "defects": defects,
              "defect_kinds": dict(Counter(d.split(": ", 1)[-1].split(" (")[0] for d in defects)),
              "per_file": per_file, "written": False}
    if defects:
        report["blocked"] = "Fix every listed defect before writing; nothing was changed."
        return report
    if write:
        for script, units in pending.items():
            project.save(project.SCRIPTS / script, units)
        report["written"] = True
        report["written_files"] = sorted(pending)
        report["next"] = ("Run python -X utf8 tools/project.py check. Growth builds still need "
                          "complete manual acceptance; no build or deployment happens here.")
    else:
        report["next"] = "Re-run with --write to update script/ for these valid translations."
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT,
                        help="Private export root containing gt_output and metadata/")
    parser.add_argument("--subset", choices=SUBSETS, default="base-game")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="Validate only; change nothing")
    action.add_argument("--write", action="store_true", help="Write valid translated_text into script/")
    parser.add_argument("--report", type=Path, default=None,
                        help="Write the full JSON report to this path instead of printing a summary")
    args = parser.parse_args()
    report = run(args.export, args.subset, write=args.write)
    summary = {key: value for key, value in report.items() if key not in ("defects", "per_file")}
    if args.report:
        project.save(args.report, report)
        summary["report"] = str(args.report)
    else:
        summary["defects"] = report["defects"][:20]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if report["defect_count"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"ERROR: {error}")
