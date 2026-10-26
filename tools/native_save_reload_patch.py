"""Correct the saved-literal decoder ABI without changing historical builders."""
from __future__ import annotations

import copy

import native_layout_patch
import project


DECODER_VA = 0x28D28
LEGACY_LOADS = bytes.fromhex("8099000480b9000880d9000c")
NATIVE_LOADS = bytes.fromhex("8099000880b9000480d9000c")


def apply(image, native):
    """Use the immutable loader's (destination, size, source, slot) contract."""
    source = project.source_bytes()
    if not native.get("runtime_text") or native.get("save_reload"):
        raise ValueError("Save reload correction requires runtime text exactly once")
    if not native_layout_patch.native_code_matches(image, image, native):
        raise ValueError("Save reload input differs from its source-bound manifest")
    # The original VM loader, not the former replay's modeled ABI, is authority.
    if source[0x44928 - 0x10000:0x44938 - 0x10000] != bytes.fromhex(
            "809c000880bc000480dc000c4bfe43f5"):
        raise ValueError("Immutable native decoder caller contract changed")
    result, report = bytearray(image), copy.deepcopy(native)
    entry = next(row for row in report["injected_blocks"]
                 if row["name"] == "replay_saved_literal_references")
    address, size = int(entry["va"], 0), entry["size"]
    start = address - 0x10000
    block = image[start:start + size]
    if project.digest(block) != entry["sha256"] or block.count(LEGACY_LOADS) != 1:
        raise ValueError("Saved-literal decoder call differs from the guarded historical helper")
    relative = block.index(LEGACY_LOADS)
    call = address + relative + len(LEGACY_LOADS)
    expected_branch = (0x48000001 | ((DECODER_VA - call) & 0x03FFFFFC)).to_bytes(4, "big")
    if block[relative + len(LEGACY_LOADS):relative + len(LEGACY_LOADS) + 4] != expected_branch:
        raise ValueError("Saved-literal loads no longer call the immutable native decoder")
    offset = start + relative
    result[offset:offset + len(NATIVE_LOADS)] = NATIVE_LOADS
    entry["sha256"] = project.digest(result[start:start + size])
    report["save_reload"] = {
        "decoder_va": hex(DECODER_VA),
        "decoder_abi": ["r3=owned output", "r4=uncompressed bytes",
                        "r5=compressed chunk pointer", "r6=compressed slot bytes"],
        "native_caller_va": "0x44928",
        "call_va": hex(call), "file_offset": hex(offset),
        "input_before": LEGACY_LOADS.hex(), "after": NATIVE_LOADS.hex(),
        "save_slot_size": 0x3FC0, "trace_capacity": 0x300,
        "serialized_bytes_changed": False, "history_ring_slots": 100,
        "scenario_payloads_changed": False, "mapping_permissions_changed": False,
        "runtime_accepted": False,
    }
    report["runtime_text"]["decoder_abi"] = report["save_reload"]["decoder_abi"]
    report.update(input_sha256=project.digest(image), output_sha256=project.digest(result),
                  runtime_accepted=False, production_cutover=False)
    if not native_layout_patch.native_code_matches(bytes(result), bytes(result), report):
        raise ValueError("Save reload correction fails the complete native write guard")
    return bytes(result), report
