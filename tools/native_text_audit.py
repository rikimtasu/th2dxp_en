"""Audit the pinned renderer; optionally replay isolated scalar branches, never RPCS3."""
import argparse
import json
from pathlib import Path
import struct

import project

def _terminal_branch_smoke(data, decoder):
    """Replay integer flush decisions, not the renderer's vector/GPU/VM behavior."""
    try:
        import unicorn
        from unicorn import ppc_const
    except ImportError as error:
        raise ValueError("Optional smoke dependency missing: python -m pip install unicorn==2.1.4") from error
    site = 0x6E64C
    image = bytearray(data[0x50000:0x60000])
    skipped = []
    for begin, end in ((0x6E318, 0x6E34C), (0x6E638, 0x6E650)):
        for instruction in decoder.disasm(data[begin - 0x10000:end - 0x10000], begin):
            if instruction.mnemonic == "vsldoi":
                # Vector copies cannot affect the integer predicate in these
                # windows. Unicorn's PPC backend cannot execute them.
                offset = instruction.address - 0x60000
                image[offset:offset + 4] = bytes.fromhex("60000000")
                skipped.append(hex(instruction.address))
    cases = [
        ("final ordinary byte", 0x6E638, 1, 1, 0, 0, 1),
        ("nonfinal ordinary byte", 0x6E638, 4, 1, 0, 0, 0),
        ("existing flush retained", 0x6E638, 4, 1, 1, 1, 1),
        ("final double-byte character", 0x6E318, 2, 2, 0, 1, 1),
        ("nonfinal double-byte character", 0x6E318, 4, 2, 0, 0, 0),
    ]
    results = []
    for patched in (False, True):
        for label, start, remaining, width, initial, old_expected, new_expected in cases:
            cpu = unicorn.Uc(unicorn.UC_ARCH_PPC, unicorn.UC_MODE_PPC64 | unicorn.UC_MODE_BIG_ENDIAN)
            cpu.ctl_set_cpu_model(ppc_const.UC_CPU_PPC64_970FX_V3_1)
            cpu.mem_map(0x60000, 0x10000)
            cpu.mem_write(0x60000, bytes(image))
            if patched:
                cpu.mem_write(site, bytes.fromhex("4082fccc"))
            for number, value in {3: ord("A"), 20: remaining, 23: 1, 24: initial, 25: width, 26: 0}.items():
                cpu.reg_write(getattr(ppc_const, f"UC_PPC_REG_{number}"), value)
            trace = []

            def observe(machine, address, size, user_data):
                trace.append(hex(address))
                if address == 0x6E9D8:
                    machine.emu_stop()

            cpu.hook_add(unicorn.UC_HOOK_CODE, observe)
            cpu.emu_start(start, 0x6E9DC, count=80)
            actual = cpu.reg_read(ppc_const.UC_PPC_REG_24)
            if trace[-1] != "0x6e9d8" or actual != (new_expected if patched else old_expected):
                raise ValueError(f"Unexpected native flush result: {label}, patched={patched}, flag={actual}")
            results.append({"case": label, "patched": patched, "remaining_bytes": remaining,
                            "character_bytes": width, "flush_before": initial, "flush_after": actual,
                            "trace": trace})
    return {"unicorn_version": unicorn.__version__, "cases": results,
            "vector_copy_nops_in_scratch_ram_only": skipped,
            "scope": "Integer terminal-branch replay only; stops before common cursor/emission path. "
                     "Vector, GPU, VM, page and complete renderer behavior are not exercised."}



def _advance_smoke(data, decoder):
    """Replay bounded metric lookups; model, rather than execute, FP advances."""
    try:
        import unicorn
        from unicorn import ppc_const
    except ImportError as error:
        raise ValueError("Optional smoke dependency missing: python -m pip install unicorn==2.1.4") from error

    # 0x1AF60 builds this range list; 0x1183C attaches the metric table.
    ranges = []
    for offset in range(0xDA430, 0xDA430 + 98 * 8, 8):
        first, last = struct.unpack_from(">II", data, offset)
        if not first:
            break
        ranges.append((struct.unpack_from(">H", data, first - 0x10000)[0],
                       struct.unpack_from(">H", data, last - 0x10000)[0]))
    if len(ranges) != 97 or sum(last - first + 1 for first, last in ranges) != 7402:
        raise ValueError("Unexpected original-font glyph ranges")

    cpu = unicorn.Uc(unicorn.UC_ARCH_PPC, unicorn.UC_MODE_PPC64 | unicorn.UC_MODE_BIG_ENDIAN)
    cpu.ctl_set_cpu_model(ppc_const.UC_CPU_PPC64_970FX_V3_1)
    cpu.mem_map(0x10000, ((len(data) + 0xFFFF) // 0x10000) * 0x10000)
    cpu.mem_write(0x10000, data)
    cpu.mem_map(0x800000, 0x10000)
    cpu.mem_write(0x801000, b"".join(struct.pack(">HH", *pair) for pair in ranges) + b"\0" * 4)
    cpu.mem_write(0x800000, struct.pack(">I", 0x801000))
    cpu.mem_write(0x80007C, struct.pack(">I", 0x257038))
    cpu.mem_write(0x80008C, struct.pack(">I", 46))  # 0x11824 -> 0x1D510.
    cpu.mem_write(0x657EB0, b"\1")  # Initialized metric-table path; fallback initialization is not replayed.

    # Unicorn traps on these wide index operations. Every operand here is
    # bounded below 2**32; these rlwinm replacements have identical results.
    # Only scratch RAM is adapted. No instruction in any ELF is changed.
    replacements = [
        (0x1D598, "sldi", "r4, r4, 1", 4, 4, 1, 30),
        (0x1D5A8, "clrldi", "r6, r6, 0x20", 6, 6, 0, 31),
        (0x1D614, "clrldi", "r7, r9, 0x20", 9, 7, 0, 31),
        (0x1D644, "clrldi", "r3, r3, 0x20", 3, 3, 0, 31),
    ]
    adapted = []
    for address, mnemonic, operands, source, target, shift, mask_end in replacements:
        before = data[address - 0x10000:address - 0x10000 + 4]
        instruction = next(decoder.disasm(before, address))
        if (instruction.mnemonic, instruction.op_str) != (mnemonic, operands):
            raise ValueError("Unexpected glyph lookup index instruction")
        after = struct.pack(">I", (21 << 26) | (source << 21) | (target << 16) |
                            (shift << 11) | (mask_end << 1))
        cpu.mem_write(address, after)
        adapted.append({"address": hex(address), "before": before.hex(), "scratch_after": after.hex()})

    def lookup(encoded):
        cpu.mem_write(0x802000, encoded + b"\0")
        cpu.reg_write(ppc_const.UC_PPC_REG_3, 0x800000)
        cpu.reg_write(ppc_const.UC_PPC_REG_4, 0x802000)
        cpu.reg_write(ppc_const.UC_PPC_REG_LR, 0x1D658)
        cpu.emu_start(0x1D538, 0x1D658, count=4000)
        if cpu.reg_read(ppc_const.UC_PPC_REG_PC) != 0x1D658:
            raise ValueError("Glyph lookup did not return within its instruction bound")
        pointer = cpu.reg_read(ppc_const.UC_PPC_REG_3)
        return pointer, list(cpu.mem_read(pointer, 2))

    metrics = {}
    for code in range(0x20, 0x7F):
        mapped = struct.unpack_from(">H", data, 0x2514B0 + 2 * (code - 0x20))[0]
        index = 0
        for first, last in ranges:
            if first <= mapped <= last:
                index += mapped - first
                break
            index += last - first + 1
        else:
            raise ValueError("ASCII mapping is outside original glyph ranges")
        expected_pointer = 0x257038 + 2 * index
        expected = list(data[expected_pointer - 0x10000:expected_pointer - 0x10000 + 2])
        pointer, actual = lookup(bytes([code]))
        if pointer != expected_pointer or actual != expected:
            raise ValueError(f"Native metric lookup differs for ASCII {code:#x}")
        metrics[chr(code)] = actual

    samples = []
    for text in ("[F09] OK", "[F02] abcdefgh", "[F08] END", "[F11] OK"):
        drawing = 0
        for char in text:
            bearing, width = metrics[char]
            drawing -= bearing - 3  # 0x59918–0x59934: move glyph origin.
            drawing += bearing + width + 3  # 0x59A58–0x59ACC: advance pen.
        scanner = len(text) * 48 * 0.5
        samples.append({"text": text, "drawing_advance": drawing,
                        "scanner_and_flower_advance": scanner, "shortfall": drawing - scanner})
    return {
        "unicorn_version": unicorn.__version__, "ascii_lookup_cases_executed": len(metrics),
        "ascii_metrics": metrics,
        "scratch_index_replacements": adapted,
        "scanner_formula": "cell_width * horizontal_scale * visible_bytes * 0.5",
        "drawing_ascii_formula": "(metric_second_byte + 6) * horizontal_scale * position_scale",
        "drawing_double_byte_formula": "cell_width * horizontal_scale * position_scale",
        "sample_model": {"cell_width": 48, "horizontal_scale": 1, "position_scale": 1,
                         "cases": samples},
        "scope": "95 source-backed ASCII metric lookups executed with four "
                 "equivalent bounded 32-bit index operations in scratch RAM. Floating-point pen "
                 "advances are arithmetic models of disassembly, not native FP execution. "
                 "No renderer, GPU, VM, flower drawing or RPCS3 execution is claimed.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scalar-smoke", action="store_true",
                        help="Replay isolated PPC integer branches with optional Unicorn; not full renderer execution")
    parser.add_argument("--advance-smoke", action="store_true",
                        help="Replay original glyph-metric lookups and model cursor/drawing differences")
    args = parser.parse_args()
    try:
        import capstone
    except ImportError as error:
        raise SystemExit("Optional RE dependency missing: python -m pip install capstone") from error
    data = project.source_bytes()
    decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    decoder.skipdata = True

    def disassemble(start, end):
        return "\n".join(f"{item.address:08x} {item.mnemonic:10} {item.op_str}" for item in
                         decoder.disasm(data[start - 0x10000:end - 0x10000], start))

    scale = data[0x5DF84:0x5DF88]
    if scale != bytes.fromhex("3F000000"):
        raise ValueError("Unexpected renderer scale constant")
    if data[0x5E64C:0x5E650] != bytes.fromhex("4082038c"):
        raise ValueError("Unexpected ordinary-character dispatch branch")
    report = {
        "source_sha256": project.digest(data), "capstone_version": capstone.__version__,
        "renderer_entry": "0x6DF90", "newline_dispatch": disassemble(0x6E34C, 0x6E438),
        "lead_byte_classifier": disassemble(0x42F40, 0x42F70),
        "double_byte_terminal_check": disassemble(0x6E318, 0x6E34C),
        "ordinary_byte_dispatch": disassemble(0x6E638, 0x6E650),
        "span_emission_gate": disassemble(0x6EC14, 0x6EC54),
        "span_submission": disassemble(0x6EE30, 0x6EEC4),
        "scan_exit": disassemble(0x6F078, 0x6F0B4),
        "cursor_bytes_to_pixels": disassemble(0x6E9D8, 0x6EAA8),
        "span_cursor_commit": disassemble(0x6EFF8, 0x6F078),
        "glyph_bearing_adjustment": disassemble(0x598DC, 0x59938),
        "glyph_pen_advance": disassemble(0x59A24, 0x59AD4),
        "glyph_metric_lookup": disassemble(0x1D538, 0x1D658),
        "font_metric_initialization": disassemble(0x11810, 0x11840),
        "font_range_initialization": disassemble(0x1AF98, 0x1B018),
        "following_fragment_cursor_reload": disassemble(0x6E0CC, 0x6E114),
        "flower_completed_span_endpoint": disassemble(0x706CC, 0x706E4),
        "flower_wait_span_endpoint": disassemble(0x70514, 0x7054C),
        "flower_final_span_endpoint": disassemble(0x7061C, 0x7064C),
        "flower_reposition_endpoint": disassemble(0x6F988, 0x6F9BC),
        "half_byte_scale_constant": {"virtual_address": "0x6DF84", "value": struct.unpack(">f", scale)[0], "bytes": scale.hex()},
        "terminal_span_defect": {
            "remaining_bytes": "r20", "consumed_bytes": "r25", "flush_flag": "r24",
            "double_byte_behavior": "0x6E318 sets flush when remaining-consumed <= 0",
            "ordinary_byte_behavior": "0x6E64C bypasses that terminal check",
            "effect": "0x6EC50 skips submission; 0x6F0AC exits with the final ordinary-byte span unsubmitted",
            "diagnostic": {"site": "0x6E64C", "file_offset": "0x5E64C",
                           "before": "4082038c", "after": "4082fccc", "target": "0x6E318"},
        },
        "scope": ["Original glyphs and font metrics stay unchanged",
                  "The terminal-span defect explains missing unsuffixed ASCII and post-newline tails",
                  "This does not establish English auto-wrap, complete renderer or runtime acceptance"],
    }
    if args.scalar_smoke:
        report["scalar_smoke"] = _terminal_branch_smoke(data, decoder)
    output = Path(__file__).resolve().parents[1] / "work/qa/text-renderer-audit.json"
    if args.advance_smoke:
        report["advance_smoke"] = _advance_smoke(data, decoder)
    project.save(output, report)
    print(json.dumps({"output": str(output), "source_sha256": report["source_sha256"],
                      "capstone_version": report["capstone_version"],
                      "native_scalar_cases_executed": len(report.get("scalar_smoke", {}).get("cases", [])),
                      "native_ascii_metric_lookups_executed": report.get("advance_smoke", {}).get("ascii_lookup_cases_executed", 0),
                      "native_floating_point_executed": False,
                      "full_renderer_executed": False, "emulator_launched": False}, indent=2))


if __name__ == "__main__":
    main()
