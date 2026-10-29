"""Audit retained test scripts and optionally stage an original-asset debug probe.

Never installs files, launches a game, or edits translations or source inputs.
The probe redirects the named-start path only; numeric script transfers remain
untouched. Static checks are not runtime acceptance.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

import project
import scenario_graph
import scenario_source


START_VA = 0x8BC9C
START_OFFSET = 0x7BC9C
ORIGINAL = bytes.fromhex("3c60006563e40000806326144bfd243960000000")
TARGETS = {"scene-menu": "999999999", "graphics-test": "700000000"}


def replay_named_start(source, patched, target_va):
    """Replay only the startup argument block in scratch RAM, not the game."""
    import unicorn
    from unicorn import ppc_const

    results = []
    old_name_va = next(row["name_ptr"] for row in project.baseline()["entries"]
                       if row["source_name"] == "010301000")
    for label, image, expected_va, expected_lr in (
            ("original", source, old_name_va, 0x8BCAC),
            ("probe", patched, target_va, 0x8BCB0)):
        cpu = unicorn.Uc(unicorn.UC_ARCH_PPC,
                         unicorn.UC_MODE_PPC64 | unicorn.UC_MODE_BIG_ENDIAN)
        cpu.ctl_set_cpu_model(ppc_const.UC_CPU_PPC64_970FX_V3_1)
        cpu.mem_map(0x10000, ((len(image) + 0xFFFF) // 0x10000) * 0x10000)
        cpu.mem_write(0x10000, image)
        context = 0x880000
        cpu.mem_write(0x652614, struct.pack(">I", context))
        cpu.reg_write(ppc_const.UC_PPC_REG_31, old_name_va)
        cpu.reg_write(ppc_const.UC_PPC_REG_30, 12345)
        trace = []

        def observe(machine, address, size, user_data):
            trace.append(hex(address))
            if address == 0x5E0E0:
                machine.emu_stop()

        cpu.hook_add(unicorn.UC_HOOK_CODE, observe)
        cpu.emu_start(START_VA, 0x8BCB0, count=8)
        actual_context = cpu.reg_read(ppc_const.UC_PPC_REG_3)
        actual_name_va = cpu.reg_read(ppc_const.UC_PPC_REG_4)
        actual_lr = cpu.reg_read(ppc_const.UC_PPC_REG_LR)
        if (trace[-1] != "0x5e0e0" or actual_context != context
                or actual_name_va != expected_va or actual_lr != expected_lr
                or cpu.reg_read(ppc_const.UC_PPC_REG_31) != old_name_va
                or cpu.reg_read(ppc_const.UC_PPC_REG_30) != 12345):
            raise ValueError(f"Unexpected named-start scalar replay result: {label}")
        name = bytes(cpu.mem_read(actual_name_va, 10)).split(b"\0", 1)[0].decode("ascii")
        results.append({"image": label, "trace": trace, "context": hex(actual_context),
                        "name_va": hex(actual_name_va), "name": name,
                        "return_va": hex(actual_lr), "r30_r31_preserved": True})
    return {"unicorn_version": unicorn.__version__, "cases": results,
            "scope": "Only 4/5 scalar instructions before the loader; no script VM, graphics, controller or complete game run"}


def patch_named_start(source: bytes, name_va: int) -> tuple[bytes, list[dict]]:
    if source[START_OFFSET:START_OFFSET + 20] != ORIGINAL:
        raise ValueError("Named-start instruction guard does not match the original ELF")
    if not 0 < name_va <= 0xFFFFFFFF:
        raise ValueError("Test-script name pointer must be a nonzero 32-bit VA")
    # Same context lookup and callee as the original path, but an exact source
    # script-name pointer replaces r31. The call moves into the old nop slot;
    # its return address is the original common continuation at 0x8BCB0.
    call_va = START_VA + 16
    delta = 0x5E0E0 - call_va
    words = (0x3C800000 | (name_va >> 16),
             0x60840000 | (name_va & 0xFFFF),
             0x3C600065, 0x80632614,
             0x48000001 | (delta & 0x03FFFFFC))
    replacement = struct.pack(">5I", *words)
    result = source[:START_OFFSET] + replacement + source[START_OFFSET + 20:]
    writes = [{"va": hex(START_VA + i * 4),
               "file_offset": hex(START_OFFSET + i * 4),
               "before": ORIGINAL[i * 4:i * 4 + 4].hex(),
               "after": replacement[i * 4:i * 4 + 4].hex()}
              for i in range(5)]
    return result, writes


def investigate(source: bytes, target: str):
    kit = project.codec()
    headers = kit.read_elf_program_headers(source)
    entries = project.baseline()["entries"]
    name = TARGETS[target]
    entry = next(row for row in entries if row["source_name"] == name)
    normalized = kit.normalize_entry(entry)
    # Read the actual native index, rather than assuming a location from a name.
    index_offset = 0xEE8B4 + normalized.entry_index * 16
    name_va = struct.unpack_from(">I", source, index_offset)[0]
    offset = kit.vaddr_to_fileoff(name_va, headers)
    if source[offset:offset + 10] != name.encode("ascii") + b"\0":
        raise ValueError("Test-menu index does not point at the expected native name")
    patched, writes = patch_named_start(source, name_va)
    payload = scenario_source.read_entry(source, normalized, kit, headers)
    code_start, labels, sites, _ = scenario_graph.scan_sites(
        payload, kit, commands={0x1F: 1, 0x22: 1, 0x61: 2, 0x63: 1})
    records = kit.read_text_records_structured(payload, project.CONFIG["encoding"], None)
    by_name = {row["source_name"]: row for row in entries}
    choices = []
    transfers = []
    for site in sites:
        if site["command_id"] == 0x22:
            choices.append(site["operands"][0])
        if site["command_id"] == 0x1F:
            argument = site["operands"][0]
            if argument["status"] != "literal_string":
                raise ValueError("Test-menu script transfer is not a literal name")
            destination = by_name.get(argument["value"])
            if destination is None:
                raise ValueError("Test-menu script transfer points at a missing scenario")
            destination_payload = scenario_source.read_entry(
                source, kit.normalize_entry(destination), kit, headers)
            transfers.append({"name": argument["value"],
                              "json": destination["json_filename"],
                              "payload_sha256": project.digest(destination_payload)})
    # All source data outside the guarded native block remains byte-identical,
    # including every scenario table entry, compressed payload and UI binding.
    if (len(patched) != len(source) or patched[:START_OFFSET] != source[:START_OFFSET]
            or patched[START_OFFSET + 20:] != source[START_OFFSET + 20:]):
        raise ValueError("Probe changed data outside its guarded startup block")
    import capstone
    decoder = capstone.Cs(capstone.CS_ARCH_PPC,
                          capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    instructions = list(decoder.disasm(patched[START_OFFSET:START_OFFSET + 20], START_VA))
    if (len(instructions) != 5 or instructions[-1].mnemonic != "bl"
            or instructions[-1].op_str != "0x5e0e0"):
        raise ValueError("Patched native dispatch failed disassembly verification")
    report = {
        "source_sha256": project.digest(source),
        "probe_sha256": project.digest(patched),
        "target_name": name, "target_json": entry["json_filename"],
        "name_va": hex(name_va), "index_file_offset": hex(index_offset),
        "payload_sha256": project.digest(payload), "code_start": code_start,
        "labels": labels, "sites": sites,
        "menu_choices": choices, "verified_transfer_targets": transfers,
        "native_text_record_count": len(records),
        "writes": writes,
        "disassembly": [f"{i.address:08x} {i.mnemonic} {i.op_str}" for i in instructions],
        "scope": "Original Japanese source with named-start redirect only; numeric script loads untouched",
        "verification": "Exact source hash, native-name index, payload decode, instruction guards and unchanged bytes outside the 20-byte block",
        "runtime_tested": False,
        "warnings": [
            "Developer scripts may rely on state the normal story has not initialized.",
            "Not a full native debug console and not a discovered controller code.",
            "Use original matching data.sdat, never a localized archive with this original-font ELF.",
            "Do not save progress or overwrite existing saves during debug testing.",
            "Named-start redirection can recur at calendar transitions; this is not a normal-play build.",
        ],
    }
    return patched, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, default="scene-menu")
    parser.add_argument("--stage", type=Path,
                        help="New workspace directory for a standalone original-asset probe; refuses existing paths")
    parser.add_argument("--scalar-smoke", action="store_true",
                        help="Replay only startup argument setup in Unicorn scratch RAM")
    parser.add_argument("--report", type=Path,
                        help="New workspace JSON report path; refuses existing files")
    args = parser.parse_args()
    output = args.stage.resolve() if args.stage else None
    if output is not None:
        if not output.is_relative_to(project.ROOT.resolve()):
            raise ValueError("Stage directory must be inside this workspace")
        if output.exists():
            raise ValueError("Stage directory already exists; preserve it and choose a new path")
    report_path = args.report.resolve() if args.report else None
    if report_path is not None:
        if not report_path.is_relative_to(project.ROOT.resolve()) or report_path.exists():
            raise ValueError("Report must be a new path inside this workspace")
    source = project.source_bytes()
    patched, report = investigate(source, args.target)
    if args.scalar_smoke:
        report["startup_scalar_replay"] = replay_named_start(source, patched, int(report["name_va"], 0))
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
        (output / "EBOOT.elf").write_bytes(patched)
        project.save(output / "debug-probe-report.json", report)
        print(f"Staged (not installed): {output / 'EBOOT.elf'}")
    if report_path is not None:
        project.save(report_path, report)
        print(f"Audit report: {report_path}")
    print(f"Target {report['target_name']} ({report['target_json']}), pointer {report['name_va']}")
    print(f"Probe SHA-256: {report['probe_sha256']}")
    for line in report["disassembly"]:
        print(line)
    print("Offline verification only; no game or RPCS3 launched and no runtime pass claimed.")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(f"ERROR: {error}") from error
