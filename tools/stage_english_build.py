"""Stage the finished base-game translation as an English EBOOT, offline.

This assembles the same engine-growth image ``project.py build --engine-growth``
would build, from ``script/`` as it stands, and writes it under ``build/`` only:

    build/english-v0.1/EBOOT.elf        canonical artifact
    build/english-v0.1/EBOOT_EN.elf     same bytes, install name used by patch_game
    build/english-v0.1/assets/data.sdat the exact paired UI/Latin/punctuation archive
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
no emulator is started. ``--reuse-ui-archive`` is an explicit option for reusing
a prior build's SDAT only after its archive, DAT round-trip and every current
replacement hash match.

Every changed scenario is re-read out of the assembled image and compared with
the staged translation before anything is written. Lexical curly apostrophes in
translated English are canonicalized to ASCII. Ruby readings become zero-length
staged text records, retaining their control pairs and source files; the base
text carries the English meaning. Neither transformation writes to ``script/``.

    python -X utf8 tools/stage_english_build.py --verify-only
    python -X utf8 tools/stage_english_build.py
    python -X utf8 tools/stage_english_build.py --output build/english-v0.3 --dialogue-scale 0.75 --reuse-ui-archive build/english-v0.1
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

import choice_text
import dialogue_scale_probe
import geninterface_latin
import native_auxiliary_latin_patch
import native_compound_punct_patch
import native_default_name_patch
import native_dialogue_scale_patch
import native_latin_punct_patch
import native_japanese_font_patch
import native_ui_smoke
import production_engine
import project
import scenario_source
import ui_probe

OUTPUT = project.ROOT / "build/english-v0.1"
ELF_NAME = "EBOOT.elf"
INSTALL_NAME = "EBOOT_EN.elf"
REPORT_NAME = "EBOOT.report.json"
PRISTINE_REPORT = project.ROOT / "build/ui-native-probe/assets/report.json"


def flatten(units):
    return [item for unit in units for item in unit["items"]]


def full_text(item):
    return item["translated_text"] + item.get("control_suffix", "")


FONT_TAG = re.compile(r'<G(\d)>')
SPLIT_FONT_TAG = re.compile(r'^G(\d)$')
INLINE_TAG = re.compile(r'<[^>]*>')
BACKSLASH_ESCAPE = re.compile(r'\\.')

# Consume the whole Unicode word chain first, so mixed Japanese/digit tokens
# cannot backtrack into a smaller apparent English contraction.
APOSTROPHE_WORD = re.compile(r"\w+(?:[‘’']\w+)+")
LEXICAL_APOSTROPHE = re.compile(r"[A-Za-z]+(?:[‘’'][A-Za-z]+)+")


def canonicalize_apostrophe_word(match):
    text = match[0]
    return text.replace("’", "'").replace("‘", "'") if LEXICAL_APOSTROPHE.fullmatch(text) else text


def canonicalize_english_apostrophes(changed):
    """Normalize translated lexical apostrophes in memory, never source/control text."""
    counts = {"apostrophes": 0, "text_rows": 0, "scripts": 0}
    for units in changed.values():
        script_changed = False
        in_tag = False
        for unit in units:
            for item in unit["items"]:
                if item["kind"] != "text":
                    continue
                original = item["original_text"]
                if original == "<":
                    in_tag = True
                    continue
                if original == ">":
                    in_tag = False
                    continue
                text = item["translated_text"]
                if in_tag or text == original:
                    continue
                # Use the validator's control parser; each escape/tag is an
                # opaque boundary, including substitution names and operands.
                pieces = []
                offset = 0
                for control in project.engine_controls(text):
                    start = text.index(control, offset)
                    pieces.append(APOSTROPHE_WORD.sub(canonicalize_apostrophe_word, text[offset:start]))
                    pieces.append(control)
                    offset = start + len(control)
                pieces.append(APOSTROPHE_WORD.sub(canonicalize_apostrophe_word, text[offset:]))
                canonical = "".join(pieces)
                if canonical == text:
                    continue
                if (project.engine_controls(canonical) != project.engine_controls(text) or
                        canonical.encode("cp932", errors="strict").decode("cp932") != canonical):
                    raise ValueError("Apostrophe canonicalization changed controls or CP932 text")
                counts["apostrophes"] += sum(text.count(c) - canonical.count(c) for c in "‘’")
                counts["text_rows"] += 1
                script_changed = True
                item["translated_text"] = canonical
        counts["scripts"] += int(script_changed)
    return counts


def suppress_ruby(changed, meta):
    """Empty split R...R0 readings in staged native literals, retaining controls."""
    count = 0
    for entry in meta["entries"]:
        if not entry["text_count"]:
            continue
        name = entry["json_filename"]
        units = changed.get(name)
        if units is None:
            units = project.load(project.SCRIPTS / name)
        modified = False
        for unit in units:
            items = unit["items"]
            for i, item in enumerate(items):
                if item.get("kind") != "text" or not re.fullmatch(r"R[1-9][0-9]*", item["original_text"]):
                    continue
                if (i < 1 or i + 5 >= len(items) or
                        [items[j].get("original_text") for j in (i - 1, i + 1, i + 3, i + 4, i + 5)] !=
                        ["<", ">", "<", "R0", ">"]):
                    raise ValueError(f"{name}: unexpected ruby control structure")
                reading = items[i + 2]
                text = reading.get("translated_text", "")
                if (reading.get("kind") != "text" or not isinstance(text, str) or
                        reading.get("control_suffix") or project.engine_controls(text) or
                        any(ord(c) < 32 or 0xE000 <= ord(c) <= 0xF8FF for c in text)):
                    raise ValueError(f"{name}: ruby reading contains controls or unsupported text")
                if text != "":
                    reading["translated_text"] = ""
                    modified = True
                count += 1
        if modified:
            changed[name] = units
    return count


def auxiliary_latin_codes(scripts, source, font):
    """Full-width alias codes the changed scripts select from one auxiliary font.

    Only font3's texture banks are too small for the whole alias set, so it is
    extended with exactly the codes its ``G3`` spans use. Deriving the set here
    keeps that subset complete for the text actually being built instead of
    trusting a snapshot; an overflow fails closed inside the patch.
    """
    aliases = geninterface_latin.aliases(source)
    needed = set()
    for units in scripts.values():
        current = 0
        for unit in units:
            pending = False
            for item in unit["items"]:
                if item["kind"] != "text":
                    continue
                original = item["original_text"]
                if original == "<":
                    pending = True
                    continue
                if original == ">":
                    continue
                if pending:
                    pending = False
                    split = SPLIT_FONT_TAG.match(original)
                    if split:
                        current = int(split.group(1))
                    continue
                for inline in FONT_TAG.finditer(original):
                    current = int(inline.group(1))
                if current != font:
                    continue
                body = BACKSLASH_ESCAPE.sub("", INLINE_TAG.sub("", item["translated_text"]))
                needed.update(aliases[char][0] for char in body if 0x20 <= ord(char) <= 0x7E)
    return needed


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

def verify_ui_replay(image, replay, native):
    """Bind the bounded UI replay to the final image without truncating either."""
    ui = native["ui_strings"]
    spans = [
        ("UI strings", ui["file_offset"], ui["file_offset"] + ui["file_size"]),
        ("UI/helper RX prefix", native["rx_extension"]["file_begin"], native["rx_extension"]["file_end"]),
        ("main glyph metrics", geninterface_latin.METRICS_OFFSET,
         geninterface_latin.METRICS_OFFSET + native_japanese_font_patch.SPECS[0][2] * 2),
        ("ASCII aliases", geninterface_latin.ALIAS_OFFSET, geninterface_latin.ALIAS_OFFSET + 95 * 2),
    ]
    for patch in native["patches"] + native.get("data_patches", []):
        start = int(patch["file_offset"], 0)
        spans.append(("native patch", start, start + len(bytes.fromhex(patch["after"]))))
    for name, start, end in spans:
        if not 0 <= start < end <= min(len(image), len(replay)) or image[start:end] != replay[start:end]:
            raise ValueError(f"Final image differs from UI replay: {name} at {start:#x}")
    return {"replayed_image_sha256": project.digest(replay),
            "final_image_sha256": project.digest(image),
            "compared_spans": len(spans), "main_metric_pairs": native_japanese_font_patch.SPECS[0][2],
            "scope": "native UI code/data and main-font metrics; scenario growth is not replayed",
            "runtime_accepted": False}



def corrections(source, rebuilt, *, japanese_font=False):
    """Add names, Latin/compound punctuation and optional Japanese font cells.

    Each step binds the immutable source and verifies its generated output.
    """
    font_tpl, punct = native_latin_punct_patch.substitute_cached(source)
    image, names = native_default_name_patch.apply(rebuilt, source=source)
    names_proof = native_default_name_patch.verify(image, names, source=source)
    image, punct = native_latin_punct_patch.apply(image, punct, source=source)
    punct_proof = native_latin_punct_patch.verify(image, font_tpl, punct)
    japanese, japanese_proof, japanese_replacements = None, None, {}
    if japanese_font:
        japanese_replacements, japanese = native_japanese_font_patch.substitute(source)
        image = native_japanese_font_patch.apply(image, japanese, source=source)
        japanese_proof = native_japanese_font_patch.verify(source, image, japanese_replacements, japanese)
        font_tpl = japanese_replacements['_initial/font.tpl']
    incoming = japanese_replacements if japanese_font else {"_initial/font.tpl": font_tpl}
    compound_replacements, compound = native_compound_punct_patch.substitute(source, incoming)
    image = native_compound_punct_patch.apply(image, compound, source=source)
    compound_proof = native_compound_punct_patch.verify(source, image, compound_replacements, compound)
    font_tpl = compound_replacements["_initial/font.tpl"]
    if japanese_font:
        japanese_replacements = compound_replacements
    return {"image": image, "font_tpl": font_tpl, "name_manifest": names,
            "name_proof": names_proof, "punct_manifest": punct, "punct_proof": punct_proof,
            "japanese_manifest": japanese, "japanese_proof": japanese_proof,
            "japanese_replacements": japanese_replacements,
            "compound_manifest": compound, "compound_proof": compound_proof}


def stage_archive(output, applied, *, reuse=None, source_sdat=None):
    """Stage matching UI assets from the pristine source or a verified prior pair."""
    import assets
    import ui_archive
    import ui_probe

    replacements, graphics = ui_probe.graphics_inputs()
    punct = applied["punct_manifest"]
    if punct["base_output_tpl_sha256"] != graphics["latin_font"]["output_tpl_sha256"]:
        raise ValueError("Punctuation atlas is not chained on the paired Latin atlas")
    if punct["base_tpl_sha256"] != graphics["latin_font"]["source_tpl_sha256"]:
        raise ValueError("Punctuation atlas source differs from the paired Latin source TPL")
    replacements["_initial/font.tpl"] = applied["font_tpl"]
    if applied.get('japanese_manifest'):
        if applied['japanese_manifest']['base_punctuation_tpl_sha256'] != punct['output_tpl_sha256']:
            raise ValueError('Japanese atlas is not chained on the current Latin/punctuation atlas')
        replacements.update(applied['japanese_replacements'])
    if reuse is None:
        pristine = (Path(source_sdat) if source_sdat is not None else
                    Path(project.load(PRISTINE_REPORT)["original_sdat"]["path"]))
        if not pristine.is_file():
            raise ValueError(f"Pristine SDAT backup is missing: {pristine}")
        archive = ui_archive.stage(replacements, output / "assets", source_sdat=pristine)
        return archive, graphics

    reuse = Path(reuse).resolve()
    build_root = (project.ROOT / "build").resolve()
    if reuse == output or reuse in output.parents or build_root not in reuse.parents:
        raise ValueError("Reusable UI archive must be a separate existing build/ artifact")
    prior_report_path = reuse / REPORT_NAME
    prior_assets = reuse / "assets"
    prior_sdat = prior_assets / "data.sdat"
    prior_archive_report = prior_assets / "report.json"
    if not all(path.is_file() for path in (prior_report_path, prior_sdat, prior_archive_report)):
        raise ValueError(f"Reusable UI archive is incomplete: {reuse}")
    prior = project.load(prior_report_path)
    archive_report = project.load(prior_archive_report)
    expected = prior.get("ui_archive", {})
    dat = archive_report.get("dat", {})
    roundtrip = archive_report.get("roundtrip", {})
    archived_replacements = {row["name"]: row["raw_sha256"]
                             for row in dat.get("replacements", [])}
    replacement_hashes = {name: project.digest(raw) for name, raw in replacements.items()}
    original = archive_report.get("original_sdat", {})
    pristine = project.load(PRISTINE_REPORT)["original_sdat"]
    staged_dat = prior_assets / "data.dat"
    if (prior.get("ui_graphics", {}).get("manifest_sha256") != graphics["manifest_sha256"]
            or prior.get("font_tpl_sha256") != project.digest(applied["font_tpl"])
            or expected.get("path") != "assets/data.sdat"
            or expected.get("sha256") != archive_report.get("sdat", {}).get("sha256")
            or expected.get("size") != archive_report.get("sdat", {}).get("size")
            or expected.get("complete_dat_roundtrip") is not True
            or expected.get("every_ciphertext_block_authenticated") is not True
            or expected.get("sha256") != prior.get("paired_pair", {}).get("data_sdat_sha256")
            or not archive_report.get("sdat", {}).get("header")
            or ui_archive._sdat_header(prior_sdat) != archive_report["sdat"]["header"]
            or prior_sdat.stat().st_size != expected.get("size")
            or assets.sha(prior_sdat) != expected.get("sha256")
            or not staged_dat.is_file()
            or staged_dat.stat().st_size != dat.get("output_size")
            or assets.sha(staged_dat) != dat.get("output_sha256")
            or archived_replacements != replacement_hashes
            or original.get("manifest_sha256") != pristine.get("manifest_sha256")
            or not original.get("full_archive_hash_rechecked")
            or roundtrip.get("matches_staged_dat") is not True
            or roundtrip.get("every_ciphertext_block_authenticated") is not True
            or roundtrip.get("complete_dat_sha256") != dat.get("output_sha256")):
        raise ValueError("Reusable archive does not prove an exact match for current UI replacements")

    target_assets = output / "assets"
    target_assets.mkdir(parents=True, exist_ok=False)
    target_sdat = target_assets / "data.sdat"
    shutil.copyfile(prior_sdat, target_sdat)
    if assets.sha(target_sdat) != expected["sha256"]:
        raise ValueError("Reused paired SDAT differs from its verified source")
    archive_report["reuse"] = {
        "source_build": str(reuse),
        "source_report_sha256": project.digest(prior_report_path.read_bytes()),
        "source_sdat_sha256": expected["sha256"],
        "current_graphics_manifest_sha256": graphics["manifest_sha256"],
        "current_font_tpl_sha256": project.digest(applied["font_tpl"]),
        "replacement_hashes_match": True,
    }
    archive_report["sdat"]["path"] = str(target_sdat)
    project.save(target_assets / "report.json", archive_report)
    return {"sdat": {**archive_report["sdat"], "path": str(target_sdat)},
            "original_sdat": {"path": None},
            "reuse": {"build": str(reuse), "source_report_sha256": archive_report["reuse"]["source_report_sha256"]},
            "roundtrip": roundtrip}, graphics


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(OUTPUT))
    archive_source = parser.add_mutually_exclusive_group()
    archive_source.add_argument("--reuse-ui-archive", type=Path,
                                help="reuse a previously authenticated archive only when all current UI hashes match")
    archive_source.add_argument("--source-sdat", type=Path,
                                help="read-only original SDAT or separately pinned and validated source variant")
    parser.add_argument("--dialogue-scale", type=float, choices=(0.75, 0.85),
                        help="apply a diagnostic scale to normal dialogue only")
    parser.add_argument("--verify-only", action="store_true",
                        help="assemble and verify in memory; write nothing")
    parser.add_argument("--japanese-font", action="store_true",
                        help="also replace Japanese cells in all four native fonts with GenInterfaceJP Regular")
    args = parser.parse_args(argv)

    output = Path(args.output).resolve()
    if not args.verify_only and (output / ELF_NAME).exists():
        raise ValueError(f"Existing artifact preserved: {output / ELF_NAME}; choose another --output")

    source, kit, meta = project.source_bytes(), project.codec(), project.baseline()
    changed, stats = project.validate(project.SCRIPTS, meta, allow_growth=True)
    ruby_readings = suppress_ruby(changed, meta)
    apostrophes = canonicalize_english_apostrophes(changed)
    template, template_report = ui_probe.assemble(source, kit, meta)
    native = template_report["native_layout"]
    # Copy current source-guarded UI corrections, not the older retained UI geometry.
    # The temporary template is diagnostic only; production/manual pins stay unchanged.
    with tempfile.TemporaryDirectory(prefix=".english-ui-", dir=project.ROOT / "build") as temporary:
        template_path = Path(temporary) / ELF_NAME
        template_path.write_bytes(template)
        project.save(template_path.parent / "manifest.json", template_report)
        rebuilt, engine = production_engine.rebuild_image(
            source, changed, kit, meta, template_path=template_path,
            template_sha256=template_report["output_sha256"])
    original_rows = scenario_source.scan(source, kit)
    proof = verify_image(rebuilt, changed, original_rows, kit)

    applied = corrections(source, rebuilt, japanese_font=args.japanese_font)
    image = applied["image"]
    if project.digest(image) == project.digest(rebuilt):
        raise ValueError("Corrections did not change the assembled image")
    if [(entry.json_filename, payload) for entry, payload, _, _ in scenario_source.scan(image, kit)] != [
            (entry.json_filename, payload) for entry, payload, _, _ in scenario_source.scan(rebuilt, kit)]:
        raise ValueError("Default-name/punctuation corrections changed a scenario payload")
    scale_report = None
    layout_replay = None
    if args.dialogue_scale is not None:
        image, scale_report = native_dialogue_scale_patch.apply(
            image, native, staged=template, scale=args.dialogue_scale)
        dialogue_scale_probe.check_hook(source, image, scale_report)
        dialogue_scale_probe.check_hook(source, image, scale_report, null=True)
        layout_replay = dialogue_scale_probe.check_layout(
            source, template, image, native, scale_report, scale=args.dialogue_scale)
        before = [(entry.json_filename, payload) for entry, payload, _, _ in
                  scenario_source.scan(applied["image"], kit)]
        after = [(entry.json_filename, payload) for entry, payload, _, _ in
                 scenario_source.scan(image, kit)]
        if len(before) != 1884 or before != after:
            raise ValueError("Dialogue-scale patch changed a scenario payload")

    # Replay the genuine small UI template with the final main metrics. The full
    # translated scenario arena overlaps the CPU fixture's synthetic objects.
    replay_image = corrections(source, template, japanese_font=args.japanese_font)["image"]
    if args.dialogue_scale is not None:
        replay_image, _ = native_dialogue_scale_patch.apply(
            replay_image, native, staged=template, scale=args.dialogue_scale)
    replay_native = copy.deepcopy(scale_report if scale_report is not None else native)
    ui_geometry = native_ui_smoke.geometry_smoke(source, replay_image, replay_native)

    story_font_latin, story_font_latin_proof = {}, {}
    if args.japanese_font:
        # The auxiliary atlases carry no ASCII cells in the source; without
        # appended aliases their English records compose to blank index0.
        tail = scale_report if scale_report is not None else native
        for font in (1, 2, 3):
            name = native_auxiliary_latin_patch.FONTS[font]["tpl"]
            codes = None if font != 3 else auxiliary_latin_codes(changed, source, font)
            image, tpl, report = native_auxiliary_latin_patch.apply(
                image, applied["font_tpl"], applied["japanese_replacements"][name],
                tail, source=source, font=font, codes=codes)
            applied["japanese_replacements"][name] = tpl
            story_font_latin[font] = report
            story_font_latin_proof[font] = native_auxiliary_latin_patch.verify(image, tpl, report)
            tail["rx_extension"].update(file_end=report["rx_end"], new_filesz=report["rx_end"],
                                        new_memsz=report["rx_end"],
                                        size=report["rx_end"] - tail["rx_extension"]["file_begin"])
            if [(entry.json_filename, payload) for entry, payload, _, _ in scenario_source.scan(image, kit)] != [
                    (entry.json_filename, payload) for entry, payload, _, _ in
                    scenario_source.scan(applied["image"], kit)]:
                raise ValueError(f"{name} Latin aliases changed a scenario payload")
    ui_geometry["final_image_correspondence"] = verify_ui_replay(image, replay_image, replay_native)


    rows = sum(1 for units in changed.values() for unit in units
               for item in unit["items"] if item["kind"] == "text")
    summary = {"output_sha256": project.digest(image), "source_sha256": project.digest(source),
               "bytes": len(image), "translated_files": len(changed), "translated_rows": rows,
               "validation": stats, "proof": proof,
               "suppressed_ruby_readings": ruby_readings,
               "canonicalized_english_apostrophes": apostrophes,
               "font_tpl_sha256": project.digest(applied["font_tpl"]),
               "default_name": applied["name_proof"],
                "punctuation": applied["punct_proof"],
                "japanese_font": applied["japanese_proof"],
               "compound_punctuation": applied["compound_proof"],
               "ui_geometry": {"complete_native_rows": ui_geometry["complete_native_rows"],
                               "panel_cases": len(ui_geometry["native_music_panel_cases"]),
                               "final_image_correspondence": ui_geometry["final_image_correspondence"]},
               "story_font_latin": story_font_latin_proof,
               "dialogue_scale": None if scale_report is None else scale_report["dialogue_scale"],
               "dialogue_scale_replay": layout_replay}

    if args.verify_only:
        summary["written"] = False
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    archive, graphics = stage_archive(output, applied, reuse=args.reuse_ui_archive,
                                     source_sdat=args.source_sdat)
    output.mkdir(parents=True, exist_ok=True)
    elf = output / ELF_NAME
    elf.write_bytes(image)
    shutil.copyfile(elf, output / INSTALL_NAME)
    if project.digest(elf.read_bytes()) != summary["output_sha256"]:
        raise ValueError("Staged EBOOT.elf differs from the verified image")
    report = {
        **stats,
        "version": "0.3-diagnostic" if args.dialogue_scale == 0.75 else "diagnostic",
        "output": str(output / INSTALL_NAME),
        "output_sha256": summary["output_sha256"],
        "source_sha256": summary["source_sha256"],
        "bytes": len(image),
        "verified_scenario_payloads": len(meta["entries"]),
        "packing": "appended segment; original 64-byte allocations; native VWF/save preview",
        "translation": {"files": len(changed), "text_rows": rows},
        "rebuilt_image_proof": proof,
        "suppressed_ruby_readings": ruby_readings,
        "canonicalized_english_apostrophes": apostrophes,
        "engine": engine,
        "default_name": applied["name_manifest"],
        "punctuation": applied["punct_manifest"],
        "punctuation_proof": applied["punct_proof"],
        "japanese_font": applied["japanese_manifest"],
        "japanese_font_proof": applied["japanese_proof"],
        "story_font_latin": story_font_latin,
        "story_font_latin_proof": story_font_latin_proof,
        "compound_punctuation": applied["compound_manifest"],
        "compound_punctuation_proof": applied["compound_proof"],
        "ui_geometry": ui_geometry,
        "font_tpl_sha256": project.digest(applied["font_tpl"]),
        "dialogue_scale": summary["dialogue_scale"],
        "dialogue_scale_replay": layout_replay,
        "dialogue_scale_native_report": scale_report,
        "ui_graphics": {"source_report": (ui_probe.GRAPHICS / "graphics-report.json").relative_to(project.ROOT).as_posix(),
                        "manifest_sha256": graphics["manifest_sha256"],
                        "label_instances": len(graphics["labels"]),
                        "assets": len(graphics["replacement_hashes"]) + (4 if args.japanese_font else 1)},
        "ui_archive": {"path": "assets/data.sdat", "sha256": archive["sdat"]["sha256"],
                       "report": "assets/report.json", "size": archive["sdat"]["size"],
                       "complete_dat_roundtrip": True,
                       "every_ciphertext_block_authenticated": True,
                        "source_sdat": archive["original_sdat"]["path"],
                        "source_variant": archive.get("source_variant"),
                       "reused_from": archive.get("reuse")},
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
            "Lexical curly apostrophes in translated English are staged as ASCII; source scripts, "
            "quotation marks and controls are retained. Text length changes require fresh same-build checkpoints.",
            "Ruby readings are staged as zero-length literals with their native R controls retained; "
            "semantic glosses, emphasis and required joins remain in the reviewed base wording.",
        ],
    }
    if scale_report is not None:
        report["notes"].append(
            f"Normal dialogue alone is scaled to {args.dialogue_scale:.0%}; backlog and UI text are not scaled. "
            "The scale replay is offline evidence, not runtime acceptance.")
    if args.japanese_font:
        with (output / 'GenInterfaceJP-OFL.txt').open('xb') as license_file:
            license_file.write(geninterface_latin.OFL.read_bytes())
        report['notes'].append(
            'Japanese kana, CJK and Japanese punctuation use GenInterfaceJP Regular in all four fonts. '
            'Latin/punctuation aliases, all private icons except the three approved compound-punctuation cells, '
            'and native fixed-cell Japanese advances remain unchanged. '
            'Changed pixels require this newly rebuilt paired archive and fresh manual acceptance.')
        report['notes'].append(
            'Story font1 gains the same Latin letters/digits, quotes and punctuation aliases; its137 source '
            'Japanese/private cells, ordered lookup and fixed48 advances are unchanged. This is what makes '
            'English story records compose visible glyphs instead of blank cells.')
    report["notes"].append(
        "Private compound punctuation E000 (!?), E001 (!!) and E00E (??) now uses the approved Gen face. "
        "Map labels use direct final-em grayscale coverage; music panel/selection/scrollbar geometry moves together. "
        "The fresh diagnostic has no runtime acceptance and does not replace the published release.")
    project.save(output / "native-ui-geometry-smoke.json", ui_geometry)
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
