"""Diagnostic-only normal-dialogue scale; never modifies installed files."""
from __future__ import annotations

import copy
import struct

import native_layout_patch
import project


HOOK = 0x64004
CONTINUE = 0x64008
FONT_HOOK = 0x6D710
FONT_CONTINUE = 0x6D718
SCALE_BITS = 0x3F59999A  # nearest binary32 to the default 0.85


def apply(image, native, *, staged=None, scale=0.85):
    """Patch normal dialogue in a source-bound image, never the shared font setup."""
    if not 0.0 < scale < 1.0:
        raise ValueError("Dialogue scale must be strictly between zero and one")
    staged = image if staged is None else staged
    if not native_layout_patch.native_code_matches(image, staged, native):
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
    font_off = FONT_HOOK - 0x10000
    font_before = bytes.fromhex("d05f00a4d03f00a8")
    if (source[font_off:font_off + 8] != font_before
            or image[font_off:font_off + 8] != font_before
            or any(int(row["va"], 0) == FONT_HOOK for row in native["patches"])):
        raise ValueError("Font-size control stores differ from source")
    start = native["rx_extension"]["file_end"]
    if any(image[start:native_layout_patch.CAVE_END]) or any(source[start:native_layout_patch.CAVE_END]):
        raise ValueError("Dialogue scale needs the original empty RX tail")
    scale_bits = struct.unpack(">I", struct.pack(">f", scale))[0]
    asm = native_layout_patch._assembler()
    address = start + 0x10000
    # Hook follows the sole normal-dialogue constructor call at 64000. Backlog
    # is constructed by the separate call at 64014. Save condition and GPRs;
    # write both scales equally, leaving glyph advances and font pixels intact.
    body = f"""
        stdu 1,-0x50(1)
        std 0,0x20(1)
        std 11,0x28(1)
        mfcr 0
        std 0,0x30(1)
        cmpwi 3,0
        beq done
        lis 11,{scale_bits >> 16:#x}
        ori 11,11,{scale_bits & 0xffff:#x}
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
    font_address = address + len(code)
    # F controls specify absolute source sizes. Apply the same factor only to
    # the live normal-dialogue context, not backlog or other text surfaces.
    # The engine singleton owns the context at +0x2b0.
    font_body = f"""
        stdu 1,-0x50(1)
        std 0,0x20(1)
        std 11,0x28(1)
        stfd 0,0x30(1)
        mffs 0
        stfd 0,0x48(1)
        mfcr 0
        std 0,0x38(1)
        lis 11,0x65
        lwz 11,0x2614(11)
        cmpwi 11,0
        beq original
        lwz 11,0x2b0(11)
        cmplw 11,31
        bne original
        lis 11,{scale_bits >> 16:#x}
        ori 11,11,{scale_bits & 0xffff:#x}
        stw 11,0x40(1)
        lfs 0,0x40(1)
        fmuls 0,2,0
        stfs 0,0xa4(31)
        lfs 0,0x40(1)
        fmuls 0,1,0
        stfs 0,0xa8(31)
        b restored
    original:
        stfs 2,0xa4(31)
        stfs 1,0xa8(31)
    restored:
        ld 0,0x38(1)
        mtcrf 255,0
        lfd 0,0x48(1)
        mtfsf 255,0
        lfd 0,0x30(1)
        ld 11,0x28(1)
        ld 0,0x20(1)
        addi 1,1,0x50
    """
    font_code = bytes(asm.asm(font_body, addr=font_address)[0])
    font_branch = bytes(asm.asm(f"b {FONT_CONTINUE:#x}", addr=font_address + len(font_code))[0])
    code += font_code + font_branch
    if len(branch) != 4 or len(font_branch) != 4 or start + len(code) > native_layout_patch.CAVE_END:
        raise ValueError("Dialogue scale helper exceeds RX padding")
    hook = bytes(asm.asm(f"b {address:#x}", addr=HOOK)[0])
    if len(hook) != 4:
        raise ValueError("Dialogue scale hook is not one instruction")
    font_hook = bytes(asm.asm(f"b {font_address:#x}", addr=FONT_HOOK)[0])
    if len(font_hook) != 4:
        raise ValueError("Font-size control hook is not one instruction")
    result = bytearray(image)
    result[off:off + 4] = hook
    result[font_off:font_off + 4] = font_hook
    result[start:start + len(code)] = code
    phoff = struct.unpack_from(">Q", image, 0x20)[0]
    filesz, memsz = struct.unpack_from(">QQ", image, phoff + 32)
    if filesz != start or memsz != start:
        raise ValueError("Dialogue scale RX mapping does not end at the reviewed tail")
    end = start + len(code)
    struct.pack_into(">QQ", result, phoff + 32, end, end)
    percent = round(scale * 100)
    purpose = f"normal_dialogue_scale_{percent}_percent"
    report = copy.deepcopy(native)
    report["rx_extension"].update(file_end=end, new_filesz=end, new_memsz=end,
                                  size=end - report["rx_extension"]["file_begin"])
    report["patches"].append({"va": hex(HOOK), "file_offset": hex(off),
                              "source_before": source[off:off + 4].hex(),
                              "input_before": image[off:off + 4].hex(),
                              "after": hook.hex(), "purpose": purpose})
    report["patches"].append({"va": hex(FONT_HOOK), "file_offset": hex(font_off),
                              "source_before": source[font_off:font_off + 4].hex(),
                              "input_before": image[font_off:font_off + 4].hex(),
                              "after": font_hook.hex(), "purpose": "normal_dialogue_font_control_scale"})
    report["injected_blocks"].append({"name": purpose, "va": hex(address),
                                       "size": len(code), "sha256": project.digest(code)})
    report["dialogue_scale"] = {"factor": scale,
                                "scope": "normal dialogue constructor and font-size controls",
                                "tracking_changed": False, "runtime_accepted": False}
    report["output_sha256"] = project.digest(result)
    if not native_layout_patch.native_code_matches(result, result, report):
        raise ValueError("Dialogue scale candidate failed the native guard")
    return bytes(result), report
