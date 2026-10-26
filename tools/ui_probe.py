"""Stage the complete readable UI ELF/SDAT pair; never deploy or run RPCS3."""
from __future__ import annotations

import copy
import json
import mmap
from pathlib import Path
import tempfile

import geninterface_latin
import native_layout_patch
import native_pagination_smoke
import native_runtime_text_smoke
import native_history_patch
import native_history_smoke
import native_latin_font_patch
import native_latin_font_smoke
import native_backlog_smoke
import native_backlog_view_patch
import native_backlog_view_smoke
import native_save_reload_patch
import native_save_reload_smoke
import native_ui_patch
import native_ui_smoke
import production_engine
import project
import runtime_text_probe
import scenario_capacity
import scenario_source
import ui_archive
import ui_graphics

INPUT = project.ROOT / "build/typography-probe/EBOOT.elf"
INPUT_SHA256 = "ce9da83e005d999e33966e45d449ac04d574cec867219fbb5176873826bb0f4c"
GRAPHICS = project.ROOT / "work/ui/gen-latin-reload-graphics"
OUTPUT = project.ROOT / "build/gen-latin-reload-probe"
FORM = project.ROOT / "work/qa/gen-latin-reload-results-to-fill.json"
FAILED = project.ROOT / "build/gen-latin-backlog-probe"
SAVE_SNAPSHOT = project.ROOT / "work/qa/probe-observations/gen-latin-reload-ui-runtime/SAVEDATA.BIN"


def assemble(source, kit, meta):
    incoming = INPUT.read_bytes()
    previous = project.load(INPUT.parent / "manifest.json")
    if project.digest(incoming) != INPUT_SHA256 or previous["output_sha256"] != INPUT_SHA256:
        raise ValueError("UI input differs from the retained typography diagnostic")
    clean, _, native = production_engine.native_image(
        source, meta, template_path=INPUT, template_sha256=INPUT_SHA256)
    native = copy.deepcopy(native)
    native["output_sha256"] = project.digest(clean)
    native_only, native = native_ui_patch.apply(clean, native)
    native_only, native = native_history_patch.apply(native_only, native)
    native_only, native = native_latin_font_patch.apply(native_only, native)
    native_only, native = native_backlog_view_patch.apply(native_only, native)
    native_only, native = native_save_reload_patch.apply(native_only, native)
    originals = {entry.json_filename: payload for entry, payload, _, _ in scenario_source.scan(source, kit)}
    incoming_rows = scenario_source.scan(incoming, kit)
    replacements = {entry.json_filename: payload for entry, payload, _, _ in incoming_rows
                    if originals[entry.json_filename] != payload}
    candidate, capacity = scenario_capacity.relocate(native_only, replacements, kit, meta)
    native["output_sha256"] = project.digest(candidate)
    candidate_rows = scenario_source.scan(candidate, kit)
    if (len(candidate_rows) != 1884 or
            [(row[0].json_filename, row[1], row[2]) for row in candidate_rows] !=
            [(row[0].json_filename, row[1], row[2]) for row in incoming_rows]):
        raise ValueError("UI staging changed a retained diagnostic scenario payload/identity")
    if not native_layout_patch.native_code_matches(candidate, candidate, native):
        raise ValueError("UI staging fails the complete native correction guard")
    report = copy.deepcopy(previous)
    report.update(build_kind="ui-runtime-correction-diagnostic", input=str(INPUT.relative_to(project.ROOT)),
                  input_sha256=INPUT_SHA256, output=str(OUTPUT / "EBOOT.elf"),
                  output_sha256=project.digest(candidate), native_layout=native,
                  native_template_sha256=project.digest(candidate), capacity=capacity,
                  scenario_payloads_identical_to_input=True,
                  retained_diagnostic_scenarios=sorted(replacements),
                  scenario_translations_inserted=False, font_assets_modified=True,
                  limits=[
                      "Bounded encoded PPC/FP replay, not GPU/RPCS3/controller/full-scheduler execution.",
                      "GPU buffer/texture resources and allocator/font/libc boundaries are modeled.",
                      "Long backlog updates isolate spans; icon and signed-coordinate edge inputs use adapted fixtures.",
                      "Native controls delimit lookahead runs; overlong tokens retain character fallback.",
                      "Approved Latin cells/metrics and UI assets change; immutable sources, retained scenario payloads and installed files do not.",
                      "Runtime history/navigation/save behavior and full-game memory fit remain manual."],
                  runtime_verified=False, production_growth_enabled=False)
    report["supersedes_failed_ui_pair"] = {
        "elf_sha256": "66786e6314959ef59e01e4bdfde87cab98a8c6b50ce65bc544f0dc6a8a32a108",
        "data_sdat_sha256": "a660c8275ec92fd42b87f27893a42e1273f4e78bdcf41dd9c6fa198702255c0c",
        "evidence": "work/qa/probe-observations/gen-latin-reload-ui-runtime.json"}
    return candidate, report


def graphics_inputs():
    report = project.load(GRAPHICS / "graphics-report.json")
    if report["manifest_sha256"] != project.digest(ui_graphics.MANIFEST.read_bytes()):
        raise ValueError("Final readable graphics do not identify the current bilingual/native layout manifest")
    expected = {row["asset"] for row in ui_graphics.editorial_labels()}
    if set(report["replacement_hashes"]) != expected:
        raise ValueError("UI graphics omit a current asset or include a non-UI/font replacement")
    replacements = {}
    for name, digest in report["replacement_hashes"].items():
        raw = (GRAPHICS / "tpl" / name).read_bytes()
        if project.digest(raw) != digest:
            raise ValueError(f"Final readable TPL changed: {name}")
        replacements[name] = raw
    for row in report["labels"]:
        layout = row["rendered_layout"]
        if layout["horizontal_compression"]:
            raise ValueError("A readable UI label is horizontally condensed")
        if layout.get("date_separator"):
            continue
        minimum = 12 if row.get("rotate") else 14
        if (layout["font_pixels"] < minimum or
                " ".join(layout["lines"]).split() != row["english"].split()):
            raise ValueError("UI readability lost a word or crossed its font-size floor")
    font_raw, font_report = geninterface_latin.replacement(project.source_bytes())
    provenance = geninterface_latin.PROVENANCE_KEYS
    if report.get("selected_font") != {key: font_report[key] for key in provenance}:
        raise ValueError("UI redraw and native Latin font do not identify the same selected face")
    dat = ui_archive._dat_module()
    _, entries = ui_archive._table(ui_archive.SOURCE, dat, 3516)
    lookup = {entry.name: entry for entry in entries}
    with ui_archive.SOURCE.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as blob:
        for name in replacements:
            raw, _ = dat.decompress_archive_entry(blob, lookup[name])
            if project.digest(raw) != report["inventory"][name]["sha256"]:
                raise ValueError("UI source TPL provenance differs from the actual immutable DAT entry")
        original_font, _ = dat.decompress_archive_entry(blob, lookup["_initial/font.tpl"])
        if project.digest(original_font) != font_report["source_tpl_sha256"]:
            raise ValueError("Latin font source differs from the immutable DAT entry")
    replacements["_initial/font.tpl"] = font_raw
    report["latin_font"] = font_report
    report["font_assets_modified"] = True
    return replacements, report




def stage():
    if OUTPUT.exists() or FORM.exists():
        raise ValueError("Existing UI diagnostic/evidence preserved; staging is not repeated")
    source, kit, meta = project.source_bytes(), project.codec(), project.baseline()
    replacements, graphics = graphics_inputs()
    candidate, report = assemble(source, kit, meta)
    native = report["native_layout"]
    if report["output_sha256"] != production_engine.TEMPLATE_SHA256:
        raise ValueError("UI candidate differs from the current reviewed native template pin")
    if native["ui_graphic_layout"]["graphics_manifest_sha256"] != graphics["manifest_sha256"]:
        raise ValueError("Native sprite geometry and readable atlas manifest are not paired")
    if native["latin_font"]["output_tpl_sha256"] != graphics["latin_font"]["output_tpl_sha256"]:
        raise ValueError("Native Latin metrics and replacement font pixels are not paired")
    execution = native_ui_smoke.smoke(source, candidate, native)
    latin = native_latin_font_smoke.smoke(source, candidate, native, tpl=replacements["_initial/font.tpl"])
    text = runtime_text_probe.long_literal(candidate, report, kit)
    payload = next(row[1] for row in scenario_source.scan(candidate, kit) if row[2] == "010301000")
    history = native_history_smoke.smoke(source, candidate, native, payload, text)
    backlog = native_backlog_smoke.smoke(source, candidate, native, payload, text)
    backlog_view = native_backlog_view_smoke.smoke(source, candidate, native, payload, text)
    reload = native_save_reload_smoke.smoke(
        source, candidate, native, (FAILED / "EBOOT.elf").read_bytes(),
        project.load(FAILED / "EBOOT.report.json")["native_layout"], SAVE_SNAPSHOT.read_bytes())
    cpu = native_runtime_text_smoke.RuntimeCPU(source, candidate, native, text, payload, payload.find(text),
                                               dialogue=True, height=628)
    literal = cpu.decode_literal()
    if literal["text"] != text or literal["consumed_bytes"] != len(text) or literal["next_byte"] != 2:
        raise ValueError("UI literal replay lost text bytes or its native VM terminator")
    cpu.run()
    cpu.assert_flags()
    pages = native_pagination_smoke.paginate(cpu)
    if pages["raw_vm_progress"] != len(text):
        raise ValueError("UI mapping disturbed complete long-text raw VM progress")
    OUTPUT.mkdir(parents=True, exist_ok=False)
    (OUTPUT / "EBOOT.elf").write_bytes(candidate)
    project.save(OUTPUT / "manifest.json", report)
    projected, projection = production_engine.rebuild_image(
        source, {}, kit, meta, template_path=OUTPUT / "EBOOT.elf", template_sha256=report["output_sha256"])
    if [(row[0].json_filename, row[1]) for row in scenario_source.scan(source, kit)] != [
            (row[0].json_filename, row[1]) for row in scenario_source.scan(projected, kit)]:
        raise ValueError("UI production projection copied diagnostic scenario English or lost a source payload")
    projection.update(image_sha256=project.digest(projected), unchanged_source_payloads=1884,
                      native_ui_strings_copied=142, production_written=False, runtime_accepted=False)
    original_archive = project.load(project.ROOT / "build/ui-native-probe/assets/report.json")
    archive = ui_archive.stage(replacements, OUTPUT / "assets",
                               source_sdat=Path(original_archive["original_sdat"]["path"]))
    report.update(engine=projection,
                  ui_archive={"path": "assets/data.sdat", "sha256": archive["sdat"]["sha256"],
                              "report": "assets/report.json", "complete_dat_roundtrip": True,
                              "native_chunk_contract_validated":
                                  archive["dat"]["verification"]["native_chunk_contract_validated"]},
                  ui_graphics={"source_report": str((GRAPHICS / "graphics-report.json").relative_to(project.ROOT)),
                               "manifest_sha256": graphics["manifest_sha256"],
                               "label_instances": len(graphics["labels"]), "assets": len(replacements),
                               "horizontal_condensation": False},
                  manual_acceptance=[
                      "The ELF and assets/data.sdat are one exact-build pair; never mix an older ELF or atlas.",
                      "User-run runtime testing only; no automatic deployment, emulator launch or save edits.",
                      "Inspect title/options, save/load, name entry, calendar, maps and Visual/Music screens at native display size.",
                      "Read every complete control hint, location, character-story label and BGM credit without glyph clipping or forced narrow letters.",
                      "GenInterfaceJP Regular replaces Latin letters/digits and six bracket aliases; keep immutable font sources, other Japanese/punctuation/private glyphs, music audio, script payloads and PS3 credit roles.",
                      "Fresh normal ToHeart2 New Game: retain H01-H08/HEND, corrected opening/skip state and disposable same-build save/load checks.",
                      "Use backlog's existing up/down controls to read every page of the long logical entry through HEND, then older/newer records; close/reopen and return to unchanged gameplay without a crash.",
                      "Check normally spaced complete name help and options labels/help, including all slider/value clearances.",
                      "Full SDAT crypto roundtrip is offline proof only; the new RX UI/helper mapping, SDAT loader behavior and full-game memory fit remain manual."])
    project.save(OUTPUT / "manifest.json", report)
    with tempfile.TemporaryDirectory(prefix=".ui-copy-proof-", dir=project.ROOT / "build") as temporary:
        copied = production_engine.stage_ui_archive(Path(temporary), projection)
        if copied is None or copied["sha256"] != archive["sdat"]["sha256"]:
            raise ValueError("Production/diagnostic UI archive staging did not retain the exact asset pair")
        projection["paired_ui_archive_copy_verified"] = True
    project.save(OUTPUT / "native-ui-smoke.json", execution)
    project.save(OUTPUT / "native-history-smoke.json", history)
    project.save(OUTPUT / "native-backlog-smoke.json", backlog)
    project.save(OUTPUT / "native-backlog-view-smoke.json", backlog_view)
    project.save(OUTPUT / "native-latin-font-smoke.json", latin)
    project.save(OUTPUT / "native-save-reload-smoke.json", reload)
    (OUTPUT / "GenInterfaceJP-OFL.txt").write_bytes(geninterface_latin.OFL.read_bytes())
    project.save(OUTPUT / "pagination-smoke.json", {"image_sha256": report["output_sha256"],
                                                   "text_bytes": len(text), "pages": pages,
                                                   "literal": {key: value for key, value in literal.items() if key != "text"},
                                                   "runtime_accepted": False})
    project.save(OUTPUT / "projection-smoke.json", projection)
    project.save(OUTPUT / "graphics-report.json", graphics)
    project.save(OUTPUT / "manifest.json", report)
    project.save(OUTPUT / "EBOOT.report.json", report)
    import gates
    form = project.load(project.ROOT / "work/qa/gen-latin-backlog-results-to-fill.json")
    form["previous_results"] = "work/qa/gen-latin-backlog-results-to-fill.json"
    form["windows"] = {"output_sha256": report["output_sha256"],
                       "data_sdat_sha256": archive["sdat"]["sha256"],
                       "tester": "", "rpcs3_version": "", "tested_at": "", "scene": "", "notes": "",
                       "checks": {check: None for check in gates.CHECKS["windows"]}, "screenshots": []}
    project.save(FORM, form)
    return {"output": str(OUTPUT / "EBOOT.elf"), "sha256": report["output_sha256"],
            "data_sdat": str(OUTPUT / "assets/data.sdat"), "data_sdat_sha256": archive["sdat"]["sha256"],
            "translated_native_strings": 142, "redrawn_label_instances": len(graphics["labels"]),
            "redrawn_assets": len(replacements), "verified_scenario_payloads": 1884,
            "results_form": str(FORM), "runtime_verified": False}


if __name__ == "__main__":
    try:
        print(json.dumps(stage(), indent=2))
    except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration) as error:
        raise SystemExit(f"ERROR: {error}")
