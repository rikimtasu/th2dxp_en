"""Stage a separate 85% dialogue diagnostic; no installer or deployment."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile

import capstone
import native_dialogue_scale_patch
import native_layout_smoke
import native_pagination_smoke
import native_runtime_text_smoke
import native_scanner_model
import project
import scenario_source


INPUT = project.ROOT / "build/gen-latin-reload-probe/EBOOT.elf"
OUTPUT = project.ROOT / "build/dialogue-scale-85-probe"


def replay_image(image, source):
    """Exclude scenario arena from synthetic RAM; code and UI mappings stay real."""
    result = bytearray(image)
    phoff = struct.unpack_from(">Q", image, 0x20)[0]
    phsize, count = struct.unpack_from(">HH", image, 0x36)
    if phsize != 56 or count != 8 or struct.unpack_from(">Q", source, 0x20)[0] != phoff:
        raise ValueError("Unexpected replay program headers")
    offset = phoff + 3 * phsize
    result[offset:offset + phsize] = source[offset:offset + phsize]
    return bytes(result)


def check_hook(source, image, native, *, null=False):
    cpu = native_scanner_model.Scanner(source, b"A", image=replay_image(image, source), patch_report=native)
    decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    for ins in decoder.disasm(cpu.read(native_dialogue_scale_patch.HOOK, 4), native_dialogue_scale_patch.HOOK):
        cpu.code[ins.address] = (ins.mnemonic, ins.op_str)
    cpu.r[3] = 0 if null else cpu.CTX
    cpu.r[0], cpu.r[11] = 0x12345678, 0x1122334455667788
    cpu.cr = [bool(i % 3) for i in range(32)]
    registers, flags, context = cpu.r[:], cpu.cr[:], cpu.read(cpu.CTX, 0x560)
    cpu.pc = native_dialogue_scale_patch.HOOK
    cpu.execute_until(native_dialogue_scale_patch.CONTINUE)
    if cpu.r != registers or cpu.cr != flags:
        raise ValueError("Dialogue scale hook changed registers or condition flags")
    after = bytearray(cpu.read(cpu.CTX, 0x560))
    if not null:
        scale = native["dialogue_scale"]["factor"]
        expected = struct.unpack(">I", struct.pack(">f", scale))[0]
        for offset in (0xA4, 0xA8):
            if cpu.get(cpu.CTX + offset, 4) != expected:
                raise ValueError(f"Dialogue scale is not {scale:.0%} on both axes")
            after[offset:offset + 4] = context[offset:offset + 4]
    if bytes(after) != context:
        raise ValueError("Dialogue scale hook modified unrelated context")


def check_layout(source, old, new, previous, native, *, scale=0.85):
    text = ("A long example question should be readable and should wrap naturally on the screen."
            "\\k\\nAnother deliberately lengthy example line exercises word wrapping and ensures "
            "that complete text remains visible without abbreviation.\\k\\nThen a short line."
            "\\k\\nA final example paragraph crosses several lines while retaining all native "
            "wait and newline controls for the replay.\\k\\nOne last reply.\\k\\n").encode("cp932")
    results = []
    for image, report, current_scale in ((old, previous, 1.0), (new, native, scale)):
        model = native_runtime_text_smoke.RuntimeCPU(source, replay_image(image, source), report, text, bytes(32), 16,
                                                     width=984, height=628, scale=current_scale, dialogue=True)
        model.write(model.TEXT, text + b"\0")
        model.r[4] = model.TEXT
        result = model.run()
        paged = native_pagination_smoke.paginate(model)
        results.append((result, paged))
    if native_layout_smoke.control_records(results[0][0]) != native_layout_smoke.control_records(results[1][0]):
        raise ValueError("Scale changed the control records")
    if results[0][1]["raw_vm_progress"] != results[1][1]["raw_vm_progress"]:
        raise ValueError("Scale changed raw text progress")
    short = b"Readable dialogue example."
    widths = []
    for image, report, current_scale in ((old, previous, 1.0), (new, native, scale)):
        model = native_runtime_text_smoke.RuntimeCPU(source, replay_image(image, source), report, short, bytes(32), 16,
                                                     width=984, height=628, scale=current_scale, dialogue=True)
        model.write(model.TEXT, short + b"\0")
        model.r[4] = model.TEXT
        result = model.run()
        if any(abs(span["scale_x"] - current_scale) > 0.000001 or
               abs(span["scale_y"] - current_scale) > 0.000001 for span in result["spans"]):
            raise ValueError("Scanner did not retain the requested uniform scale")
        widths.append(result["final_cursor"][0])
    if not 0 < widths[1] < widths[0] or abs(widths[1] / widths[0] - scale) > 0.02:
        raise ValueError(
            f"Dialogue measurement did not shrink to approximately {scale:.0%}: widths={widths}")
    return {"source_page_count": results[0][1]["page_count"],
            "smaller_page_count": results[1][1]["page_count"],
            "sample_cursor_widths": widths, "scale": scale,
            "text_and_progress_preserved": True,
            "limitation": "Synthetic combined literal; not a live VM, audio, or GPU test"}




def main():
    if OUTPUT.exists():
        raise ValueError(f"Existing diagnostic preserved: {OUTPUT}")
    previous = project.load(INPUT.parent / "manifest.json")["native_layout"]
    image = INPUT.read_bytes()
    source = project.source_bytes()
    candidate, native = native_dialogue_scale_patch.apply(image, previous)
    check_hook(source, candidate, native)
    check_hook(source, candidate, native, null=True)
    layout = check_layout(source, image, candidate, previous, native)
    kit = project.codec()
    before, after = scenario_source.scan(image, kit), scenario_source.scan(candidate, kit)
    if len(before) != 1884 or [(vars(row[0]), row[1:]) for row in before] != [
            (vars(row[0]), row[1:]) for row in after]:
        raise ValueError("Dialogue scale changed scenario payloads")
    report = {"diagnostic_only": True, "runtime_verified": False,
              "production_growth_enabled": False, "scenario_payloads_unchanged": len(before),
              "output_sha256": project.digest(candidate), "native_layout": native,
              "layout_replay": layout,
              "required_paired_sdat": "build/gen-latin-reload-probe/assets/data.sdat",
              "limitations": ["No live GPU, readability, whole VM or voice synchronization proof.",
                              "Uses retained diagnostic scenarios, not the released translated build."]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dialogue-scale-", dir=OUTPUT.parent) as folder:
        target = Path(folder)
        (target / "EBOOT.elf").write_bytes(candidate)
        project.save(target / "manifest.json", report)
        target.rename(OUTPUT)
    print(json.dumps({"output": str(OUTPUT / "EBOOT.elf"), "sha256": report["output_sha256"],
                      "scenario_payloads_unchanged": len(before), "layout": layout}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        raise SystemExit(f"ERROR: {error}")
