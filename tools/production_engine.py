"""Build full-length scenarios with the exact staged native correction.

Pure assembly is reusable for offline diagnostics. Production callers must first
require_manual_acceptance; this module never writes an ELF or deploys anything.
"""
from __future__ import annotations

import struct
from pathlib import Path
import shutil
import tempfile
import choice_text

import native_layout_patch
import project
import scenario_capacity
import scenario_source

TEMPLATE_SHA256 = "a15f4f08499d7bbc07a5ce19eda0c8a9fccac0274ae4541a8a3acd479765c806"


def require_manual_acceptance():
    """Fail closed before production growth if any required evidence is absent."""
    import gates
    try:
        evidence = gates.read_evidence(gates.EVIDENCE)
    except (OSError, ValueError, KeyError) as error:
        raise ValueError(f"Production engine growth needs complete manual acceptance: {error}") from error
    if evidence["windows"]["output_sha256"] != TEMPLATE_SHA256:
        raise ValueError("Manual acceptance identifies a different native/capacity template")
    return {"path": gates.EVIDENCE.relative_to(project.ROOT).as_posix(),
            "sha256": project.digest(gates.EVIDENCE.read_bytes())}


def evidence_present():
    import gates
    return gates.EVIDENCE.exists()


def stage_ui_archive(output_dir, engine_report):
    """Copy the exact paired UI archive to a build directory, never an install.

    Production callers own require_manual_acceptance; offline smoke callers
    remain explicitly diagnostic. Neither path may mix native UI geometry with
    a missing, modified, or unrelated texture archive.
    """
    if not engine_report.get("ui_archive_required"):
        return None
    import assets
    import gates
    info = gates.ui_asset_info()
    if info["elf_sha256"] != engine_report["native_template_sha256"]:
        raise ValueError("Native UI correction and texture archive identify different templates")
    output_dir = Path(output_dir).resolve()
    build = (project.ROOT / "build").resolve()
    if output_dir == build or build not in output_dir.parents:
        raise ValueError("Paired UI archives may only be staged inside a build/ subdirectory")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "data.sdat"
    copied = False
    if target.exists():
        if not target.is_file() or assets.sha(target) != info["sha256"]:
            raise ValueError("Existing staged data.sdat differs; refusing to overwrite unrelated assets")
    else:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix=".ui-", suffix=".sdat", dir=output_dir, delete=False) as stream:
                temporary = Path(stream.name)
                with info["path"].open("rb") as original:
                    shutil.copyfileobj(original, stream, 4 * 1024 * 1024)
            if assets.sha(temporary) != info["sha256"]:
                raise ValueError("Paired UI archive copy differs from its exact staged SHA-256")
            temporary.rename(target)
            temporary = None
            copied = True
        finally:
            if temporary is not None:
                temporary.unlink()
    return {"path": str(target), "sha256": info["sha256"],
            "source": str(info["path"]), "copied": copied, "runtime_approval_inferred": False}


def native_image(original, meta, *, template_path=None, template_sha256=None):
    """Copy only reviewed native sites/mapping/helpers, never diagnostic text."""
    import gates
    if project.digest(original) != native_layout_patch.SOURCE_SHA256:
        raise ValueError("Production engine assembly requires the immutable source image")
    if (template_path is None) != (template_sha256 is None):
        raise ValueError("An explicit diagnostic template requires both path and pinned hash")
    staged_path = gates.ARTIFACTS["windows"] if template_path is None else template_path
    expected = TEMPLATE_SHA256 if template_sha256 is None else template_sha256
    staged = staged_path.read_bytes()
    report = project.load(staged_path.parent / "manifest.json")
    if project.digest(staged) != expected or report["output_sha256"] != expected:
        raise ValueError("Staged native/capacity template has changed")
    native = report["native_layout"]
    if (native["source_sha256"] != project.digest(original) or
            not native_layout_patch.native_code_matches(staged, staged, native)):
        raise ValueError("Staged native manifest does not match its image/source")
    begin, end = (native["rx_extension"][key] for key in ("file_begin", "file_end"))
    if any(original[begin:end]):
        raise ValueError("Native extension would replace nonzero source bytes")
    result = bytearray(original)
    sites = set()
    for patch in native["patches"]:
        offset = int(patch["file_offset"], 0)
        before, after = (bytes.fromhex(patch[key]) for key in ("source_before", "after"))
        if (offset in sites or len(before) != 4 or len(after) != 4 or
                not 0 <= offset <= begin - 4 or original[offset:offset + 4] != before or
                staged[offset:offset + 4] != after):
            raise ValueError("Native template site differs from pinned source/staged bytes")
        sites.add(offset)
        result[offset:offset + 4] = after
    result[begin:end] = staged[begin:end]
    phoff = struct.unpack_from(">Q", original, 0x20)[0]
    # PT_LOAD0 file/memory sizes only; the original empty RW header remains free.
    result[phoff + 0x20:phoff + 0x30] = staged[phoff + 0x20:phoff + 0x30]
    for patch in native.get("data_patches", []):
        offset = int(patch["file_offset"], 0)
        before, after = (bytes.fromhex(patch[key]) for key in ("source_before", "after"))
        if (offset in sites or not native_layout_patch.ui_data_site(offset)
                or len(before) != 4 or len(after) != 4
                or original[offset:offset + 4] != before or staged[offset:offset + 4] != after):
            raise ValueError("Native UI table differs from pinned source/staged bytes")
        sites.add(offset)
        result[offset:offset + 4] = after
    latin = native.get("latin_font")
    if latin:
        import native_latin_font_patch
        if not native_latin_font_patch.manifest_matches(latin):
            raise ValueError("Native Latin metric provenance differs from selected face/source")
        for patch in latin["patches"]:
            offset = int(patch["file_offset"], 0)
            before, after = (bytes.fromhex(patch[key]) for key in ("source_before", "after"))
            if (offset in sites or original[offset:offset + 2] != before
                    or staged[offset:offset + 2] != after):
                raise ValueError("Native Latin metric pair differs from source/staged bytes")
            sites.add(offset)
            result[offset:offset + 2] = after
    ui = native.get("ui_strings")
    if ui:
        header = phoff + 2 * 56
        if original[header:header + 56] != bytes.fromhex(ui["source_header"]):
            raise ValueError("Native UI read-only header differs from pinned source")
        offset, size = ui["file_offset"], ui["file_size"]
        result.extend(b"\0" * (offset - len(result)))
        result.extend(staged[offset:offset + size])
        result[header:header + 56] = staged[header:header + 56]
    if not native_layout_patch.native_code_matches(result, staged, native):
        raise ValueError("Assembled native code differs from the complete staged correction")
    # Prove no template native difference was omitted from its patch list.
    # The only remaining differences may be the diagnostic arena header/index.
    ranges = [(phoff + 3 * 56, phoff + 4 * 56)]
    ranges.extend((meta["table_start"] + entry["entry_index"] * 16 + 4,
                   meta["table_start"] + entry["entry_index"] * 16 + 16)
                  for entry in meta["entries"])
    left, right = memoryview(result), memoryview(staged)
    cursor = 0
    for start, stop in sorted(ranges):
        if not cursor <= start <= stop <= len(original) or left[cursor:start] != right[cursor:start]:
            raise ValueError("Template has an unaccounted original-image difference")
        cursor = stop
    if left[cursor:len(original)] != right[cursor:len(original)]:
        raise ValueError("Template has an unaccounted original-image tail difference")
    return bytes(result), staged, native


def rebuild_image(original, changed, kit, meta, *, template_path=None, template_sha256=None):
    """Rebuild validated translated units with growth; retain every other payload.

    This is an offline assembly API, not manual approval. project.build guards
    production writes separately. No fixed original text or compressed-slot
    budget applies; the codec still enforces encoding/control/label contracts.
    """
    native, staged, native_report = native_image(
        original, meta, template_path=template_path, template_sha256=template_sha256)
    scanned = scenario_source.scan(original, kit)
    known = {name for entry, *_ in scanned
             for name in (entry.json_filename, choice_text.companion_name(entry.json_filename))}
    if set(changed) - known:
        raise ValueError("Translated scenario is outside the complete source index")
    replacements = {}
    for entry, payload, _, _ in scanned:
        choices = changed.get(choice_text.companion_name(entry.json_filename))
        if entry.json_filename in changed or choices is not None:
            rebuilt = (kit.rebuild_scenario_from_structured_json(
                payload, changed[entry.json_filename], encoding=project.CONFIG["encoding"],
                font_table=None, allow_growth=True) if entry.json_filename in changed else payload)
            if choices is not None:
                rebuilt = choice_text.rebuild(rebuilt, choices, kit, allow_growth=True)
            replacements[entry.json_filename] = rebuilt
    rebuilt, report = scenario_capacity.relocate(native, replacements, kit, meta)
    import gates
    okay, explanation = gates.engine_cutover(rebuilt, staged, native_report, kit)
    if not okay:
        raise ValueError(f"Production engine assembly failed its full cutover guard: {explanation}")
    report.update(native_template_sha256=project.digest(staged),
                  native_correction_matches_staged=True,
                  diagnostic_text_copied=False,
                  ui_archive_required=bool(native_report.get("ui_strings")),
                  engine_cutover=explanation)
    return rebuilt, report
