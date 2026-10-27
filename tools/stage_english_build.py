"""Stage the finished base-game translation as an English EBOOT, offline.

This assembles the same engine-growth image ``project.py build --engine-growth``
would build, from ``script/`` as it stands, and writes it under ``build/`` only:

    build/english-v0.1/EBOOT.elf        canonical artifact
    build/english-v0.1/EBOOT_EN.elf     same bytes, install name used by patch_game
    build/english-v0.1/data.sdat        the exact paired UI/Latin/punctuation archive
    build/english-v0.1/EBOOT.report.json

On top of the reviewed native template it adds the two corrections the shipped
translation needs and the earlier diagnostic pair lacked:

* the ASCII punctuation aliases (``. , ! ? ' " : ; - ~ * < > …``) are redrawn from
  the approved face so English punctuation is Latin rather than wide Japanese,
* the six native default-player-name strings become ``Kouno Takaaki`` / ``Taka``
  and every reviewed load site is repointed.

It deliberately does **not** write ``work/qa/manual-evidence.json``: manual
acceptance is the user's observation, and this tool must not invent tester,
timestamp or screenshot records. So the report records ``manual_acceptance:
null`` and ``runtime_verified: false``. Installing and running it stays a
separate, user-run step (``tools/patch_game.py``); nothing is deployed here and
no emulator is started.

Every changed scenario is re-read out of the assembled image and compared with
``script/`` before anything is written, and the corrections are proven not to
touch a single scenario payload, so a staged file cannot silently differ from
the translation it claims to contain.

    python -X utf8 tools/stage_english_build.py --verify-only
    python -X utf8 tools/stage_english_build.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

import choice_text
import native_default_name_patch
import native_latin_punct_patch
import production_engine
import project
import scenario_source

OUTPUT = project.ROOT / "build/english-v0.1"
ELF_NAME = "EBOOT.elf"
INSTALL_NAME = "EBOOT_EN.elf"
REPORT_NAME = "EBOOT.report.json"
PRISTINE_REPORT = project.ROOT / "build/ui-native-probe/assets/report.json"


def flatten(units):
    return [item for unit in units for item in unit["items"]]


def full_text(item):
    return item["translated_text"] + item.get("control_suffix", "")


def expect_items(name, payload, units, kit, *, choice_parent=False):
    """Compare one rebuilt payload with its ``script/`` units; return text count."""
    observed = flatten(kit.make_structured_units(
        payload, kit.read_text_records_structured(payload, "cp932", None),
        include_offsets=False, encoding="cp932", font_table=None, decode_gaps=False))
    wanted = flatten(units)
    if len(observed) != len(wanted):
        raise ValueError(f"{name}: {len(observed)} items for {len(wanted)} in script/")
    texts = 0
    for index, (want, got) in enumerate(zip(wanted, observed)):
        if want["kind"] != got["kind"]:
            raise ValueError(f"{name}: item {index} changed kind")
        if want["kind"] == "text":
            if full_text(want) != got["original_text"] + got.get("control_suffix", ""):
                raise ValueError(f"{name}: item {index} text differs from the translation")
            texts += 1
        elif want["kind"] == "opcode_gap" and choice_parent:
            continue
        elif want != got:
            raise ValueError(f"{name}: item {index} original bytecode/control changed")
    return texts


def expect_captions(name, parent_payload, units, kit):
    """Compare spliced choice captions and require their bytes in the parent."""
    observed = [row["text"] for row in choice_text.records(parent_payload, kit)]
    expected = [item["translated_text"] for unit in units for item in unit["items"]]
    if observed != expected:
        raise ValueError(f"{name}: choice captions did not re-extract from the rebuilt image")
    for text in expected:
        if text.encode("cp932") not in parent_payload:
            raise ValueError(f"{name}: translated caption bytes absent from the parent payload")
    return len(expected)


def verify_image(rebuilt, changed, original_rows, kit):
    """Prove the assembled image carries exactly the translations in ``script/``.

    Growth re-aligns records, so unit grouping is not stable across a rebuild;
    the durable invariant is the flattened item order. Text is compared as
    ``translated_text + control_suffix`` because trailing controls re-extract as
    the item's ``control_suffix``. Choice captions are spliced into the parent
    payload, so a parent's gap bytes may legitimately change; those captions are
    verified separately through ``choice_text.records``.
    """
    rows = {entry.json_filename: payload for entry, payload, _, _ in scenario_source.scan(rebuilt, kit)}
    before = {entry.json_filename: payload for entry, payload, _, _ in original_rows}
    parents = {name[: -len("_choices.json")] + ".json"
               for name in changed if name.endswith("_choices.json")}
    texts = 0
    for name, units in sorted(changed.items()):
        if name.endswith("_choices.json"):
            texts += expect_captions(name, rows[name[: -len("_choices.json")] + ".json"], units, kit)
            continue
        texts += expect_items(name, rows[name], units, kit, choice_parent=name in parents)
    untouched = 0
    for entry, payload, _, _ in scenario_source.scan(rebuilt, kit):
        name = entry.json_filename
        if name in changed or choice_text.companion_name(name) in changed:
            continue
        if payload != before[name]:
            raise ValueError(f"{name}: untouched scenario payload changed")
        untouched += 1
    return {"changed_scripts": len(changed), "verified_text_rows": texts,
            "untouched_payloads_identical": untouched,
            "choice_files": sum(1 for name in changed if name.endswith("_choices.json"))}


def corrections(source, rebuilt):
    """Add the shipped punctuation atlas and the English default name.

    Both steps refuse to run unless their source bytes still match the immutable
    executable, and both re-read what they wrote before returning.
    """
    font_tpl, punct = native_latin_punct_patch.substitute_cached(source)
    image, names = native_default_name_patch.apply(rebuilt, source=source)
    names_proof = native_default_name_patch.verify(image, names, source=source)
    image, punct = native_latin_punct_patch.apply(image, punct, source=source)
    punct_proof = native_latin_punct_patch.verify(image, font_tpl, punct)
    return {"image": image, "font_tpl": font_tpl, "name_manifest": names,
            "name_proof": names_proof, "punct_manifest": punct, "punct_proof": punct_proof}


def stage_archive(output, applied):
    """Repack the paired SDAT so its main-font atlas carries the same cells."""
    import ui_archive
    import ui_probe

    replacements, graphics = ui_probe.graphics_inputs()
    punct = applied["punct_manifest"]
    if punct["base_output_tpl_sha256"] != graphics["latin_font"]["output_tpl_sha256"]:
        raise ValueError("Punctuation atlas is not chained on the paired Latin atlas")
    if punct["base_tpl_sha256"] != graphics["latin_font"]["source_tpl_sha256"]:
        raise ValueError("Punctuation atlas source differs from the paired Latin source TPL")
    replacements["_initial/font.tpl"] = applied["font_tpl"]
    pristine = Path(project.load(PRISTINE_REPORT)["original_sdat"]["path"])
    if not pristine.is_file():
        raise ValueError(f"Pristine SDAT backup is missing: {pristine}")
    archive = ui_archive.stage(replacements, output / "assets", source_sdat=pristine)
    return archive, graphics


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--verify-only", action="store_true",
                        help="assemble and verify in memory; write nothing")
    args = parser.parse_args(argv)

    output = Path(args.output).resolve()
    if not args.verify_only and (output / ELF_NAME).exists():
        raise ValueError(f"Existing artifact preserved: {output / ELF_NAME}; choose another --output")

    source, kit, meta = project.source_bytes(), project.codec(), project.baseline()
    changed, stats = project.validate(project.SCRIPTS, meta, allow_growth=True)
    rebuilt, engine = production_engine.rebuild_image(source, changed, kit, meta)
    original_rows = scenario_source.scan(source, kit)
    proof = verify_image(rebuilt, changed, original_rows, kit)

    applied = corrections(source, rebuilt)
    image = applied["image"]
    if project.digest(image) == project.digest(rebuilt):
        raise ValueError("Corrections did not change the assembled image")
    if [(entry.json_filename, payload) for entry, payload, _, _ in scenario_source.scan(image, kit)] != [
            (entry.json_filename, payload) for entry, payload, _, _ in scenario_source.scan(rebuilt, kit)]:
        raise ValueError("Default-name/punctuation corrections changed a scenario payload")

    rows = sum(1 for units in changed.values() for unit in units
               for item in unit["items"] if item["kind"] == "text")
    summary = {"output_sha256": project.digest(image), "source_sha256": project.digest(source),
               "bytes": len(image), "translated_files": len(changed), "translated_rows": rows,
               "validation": stats, "proof": proof,
               "font_tpl_sha256": project.digest(applied["font_tpl"]),
               "default_name": applied["name_proof"],
               "punctuation": applied["punct_proof"]}

    if args.verify_only:
        summary["written"] = False
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    archive, graphics = stage_archive(output, applied)
    output.mkdir(parents=True, exist_ok=True)
    elf = output / ELF_NAME
    elf.write_bytes(image)
    shutil.copyfile(elf, output / INSTALL_NAME)
    if project.digest(elf.read_bytes()) != summary["output_sha256"]:
        raise ValueError("Staged EBOOT.elf differs from the verified image")
    report = {
        **stats,
        "output": str(output / INSTALL_NAME),
        "output_sha256": summary["output_sha256"],
        "source_sha256": summary["source_sha256"],
        "bytes": len(image),
        "verified_scenario_payloads": len(meta["entries"]),
        "packing": "appended segment; original 64-byte allocations; native VWF/save preview",
        "translation": {"files": len(changed), "text_rows": rows},
        "rebuilt_image_proof": proof,
        "engine": engine,
        "default_name": applied["name_manifest"],
        "punctuation": applied["punct_manifest"],
        "punctuation_proof": applied["punct_proof"],
        "font_tpl_sha256": project.digest(applied["font_tpl"]),
        "ui_graphics": {"source_report": "work/ui/gen-latin-reload-graphics/graphics-report.json",
                        "manifest_sha256": graphics["manifest_sha256"],
                        "label_instances": len(graphics["labels"]),
                        "assets": len(graphics["replacement_hashes"]) + 1},
        "ui_archive": {"path": "assets/data.sdat", "sha256": archive["sdat"]["sha256"],
                       "report": "assets/report.json", "size": archive["sdat"]["size"],
                       "complete_dat_roundtrip": True,
                       "every_ciphertext_block_authenticated": True,
                       "source_sdat": archive["original_sdat"]["path"]},
        "paired_pair": {"elf_sha256": summary["output_sha256"],
                        "data_sdat_sha256": archive["sdat"]["sha256"],
                        "note": "Never mix this ELF with another archive, or this archive with another ELF."},
        "manual_acceptance": None,
        "production_growth_enabled": False,
        "diagnostic_staging": True,
        "runtime_verified": False,
        "emulator_tested": False,
        "notes": [
            "Assembled offline from script/ with the full manual-acceptance engine path, "
            "but no work/qa/manual-evidence.json was written or implied.",
            "Installing and running this build is a separate user step; nothing was deployed.",
            "Latin letters/digits, six bracket aliases and 23 ASCII punctuation aliases are redrawn; "
            "the default player name is 'Kouno Takaaki' (short form 'Taka').",
        ],
    }
    project.save(output / REPORT_NAME, report)
    summary.update(written=True, elf=str(output / INSTALL_NAME),
                   report=str(output / REPORT_NAME),
                   data_sdat=str(output / "assets/data.sdat"),
                   data_sdat_sha256=archive["sdat"]["sha256"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"ERROR: {error}")
