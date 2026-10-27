"""Diagnostic-only 85% normal-dialogue scale; never modifies installed files."""
from __future__ import annotations

import copy
import struct

import native_layout_patch
import project


HOOK = 0x64004
CONTINUE = 0x64008
SCALE_BITS = 0x3F59999A  # nearest binary32 to 0.85


def apply(image, native):
    """Patch the normal-context constructor return, not the shared font setup."""
    if not native_layout_patch.native_code_matches(image, image, native):
        raise ValueError("Dialogue scale requires the complete pinned native template")
    source = project.source_bytes()
    callers = bytes.fromhex("38a0000038600000809df7884800caf960000000"
                            "809df78838a00001907f02b04800cae5")
    caller_offset = 0x63FF4 - 0x10000
    if (source[caller_offset:caller_offset + len(callers)] != callers
            or image[caller_offset:caller_offset + len(callers)] != callers):
        raise ValueError("Normal and backlog dialogue constructor calls differ from source")
    off = HOOK - 0x10000
    if image[off:off + 4] != source[off:off + 4] or source[off:off + 4] != bytes.fromhex("60000000"):
        raise ValueError("Dialogue constructor return is not the expected source nop")
    if any(int(row["va"], 0) == HOOK for row in native["patches"]):
        raise ValueError("Dialogue constructor return is already patched")
    start = native["rx_extension"]["file_end"]
    if any(image[start:native_layout_patch.CAVE_END]) or any(source[start:native_layout_patch.CAVE_END]):
        raise ValueError("Dialogue scale needs the original empty RX tail")
    asm = native_layout_patch._assembler()
    address = start + 0x10000
    # Hook follows the sole normal-dialogue constructor call at 64000. Backlog
    # is constructed by the separate call at 64014. Save condition and GPRs;
    # write both scales equally, leaving glyph advances and font pixels intact.
    body = """
        stdu 1,-0x50(1)
        std 0,0x20(1)
        std 11,0x28(1)
        mfcr 0
        std 0,0x30(1)
        cmpwi 3,0
        beq done
        lis 11,0x3f59
        ori 11,11,0x999a
        stw 11,0xa4(3)
        stw 11,0xa8(3)
    done:
        ld 0,0x30(1)
        mtcrf 255,0
        ld 11,0x28(1)
        ld 0,0x20(1)
        addi 1,1,0x50
    """
    code = bytes(asm.asm(body, addr=address)[0])
    branch = bytes(asm.asm(f"b {CONTINUE:#x}", addr=address + len(code))[0])
    code += branch
    if len(branch) != 4 or start + len(code) > native_layout_patch.CAVE_END:
        raise ValueError("Dialogue scale helper exceeds RX padding")
    hook = bytes(asm.asm(f"b {address:#x}", addr=HOOK)[0])
    if len(hook) != 4:
        raise ValueError("Dialogue scale hook is not one instruction")
    result = bytearray(image)
    result[off:off + 4] = hook
    result[start:start + len(code)] = code
    phoff = struct.unpack_from(">Q", image, 0x20)[0]
    filesz, memsz = struct.unpack_from(">QQ", image, phoff + 32)
    if filesz != start or memsz != start:
        raise ValueError("Dialogue scale RX mapping does not end at the reviewed tail")
    end = start + len(code)
    struct.pack_into(">QQ", result, phoff + 32, end, end)
    report = copy.deepcopy(native)
    report["rx_extension"].update(file_end=end, new_filesz=end, new_memsz=end,
                                  size=end - report["rx_extension"]["file_begin"])
    report["patches"].append({"va": hex(HOOK), "file_offset": hex(off),
                              "source_before": source[off:off + 4].hex(),
                              "input_before": image[off:off + 4].hex(),
                              "after": hook.hex(), "purpose": "normal_dialogue_scale_85_percent"})
    report["injected_blocks"].append({"name": "normal_dialogue_scale_85_percent",
                                       "va": hex(address), "size": len(code),
                                       "sha256": project.digest(code)})
    report["dialogue_scale"] = {"factor": 0.85, "scope": "normal dialogue constructor only",
                                "tracking_changed": False, "runtime_accepted": False}
    report["output_sha256"] = project.digest(result)
    if not native_layout_patch.native_code_matches(result, result, report):
        raise ValueError("Dialogue scale candidate failed the native guard")
    return bytes(result), report
