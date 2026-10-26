"""Queue-safe original-font pagination for a source-bound diagnostic image.

Unread native spans remain in the original linked list. An automatic boundary
uses the existing wait/advance path, not inserted script controls. Advancing
retires only the completed prefix and rebases the unread spans. This module
writes no ELF, changes no production gate and claims no runtime acceptance.
"""
from __future__ import annotations

import copy
import re
import struct
import textwrap

import project
import native_layout_patch

CONTEXT_SIZE = 0x560
BOUNDARY = 0x550


def apply(image, native):
    source = project.source_bytes()
    if not native_layout_patch.native_code_matches(image, image, native):
        raise ValueError("Pagination requires the complete source-bound native diagnostic")
    if native.get("pagination"):
        raise ValueError("Pagination is already applied; existing diagnostic preserved")
    start = native["rx_extension"]["file_end"]
    end_limit = native_layout_patch.CAVE_END
    if any(image[start:end_limit]) or any(source[start:end_limit]):
        raise ValueError("Pagination helper extension is not original zero padding")
    ks = native_layout_patch._assembler()
    result, code = bytearray(image), bytearray()
    report = copy.deepcopy(native)
    existing_sites = {int(row["va"], 0) for row in native["patches"]}
    entries = {}

    def assemble(body, address):
        # Keystone misrelocates numeric external branches in mixed local-label
        # blocks. Resolve each external instruction separately at its actual PC.
        lines, external, index = [], [], 0
        for line in textwrap.dedent(body).strip().splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.fullmatch(r"(b|bl|beq|bne|bgt|bge|blt|ble)\s+(?:(cr[0-7]),\s*)?(0x[0-9a-fA-F]+)", line)
            if match:
                external.append((index, line))
                lines.append("nop")
            else:
                lines.append(line)
            if not line.endswith(":"):
                index += 1
        encoded, _ = ks.asm("\n".join(lines), addr=address)
        blob = bytearray(encoded)
        if len(blob) != index * 4:
            raise ValueError("Unexpected pagination instruction expansion")
        for index, instruction in external:
            replacement, _ = ks.asm(instruction, addr=address + index * 4)
            if len(replacement) != 4:
                raise ValueError("Pagination external branch is not one instruction")
            blob[index * 4:index * 4 + 4] = bytes(replacement)
        return bytes(blob)

    def emit(name, body):
        address = start + 0x10000 + len(code)
        blob = assemble(body, address)
        if start + len(code) + len(blob) > end_limit:
            raise ValueError("Pagination exceeds the bounded RX extension")
        code.extend(blob)
        entries[name] = address
        report["injected_blocks"].append({"name": name, "va": hex(address),
                                          "size": len(blob), "sha256": project.digest(blob)})
        return address

    def replace(va, instruction, purpose):
        offset = va - 0x10000
        before = source[offset:offset + 4]
        if va in existing_sites or image[offset:offset + 4] != before:
            raise ValueError(f"Pagination site {va:#x} is not an unmodified source instruction")
        after = assemble(instruction, va)
        if len(after) != 4:
            raise ValueError("Pagination hook must replace exactly one instruction")
        result[offset:offset + 4] = after
        report["patches"].append({"va": hex(va), "file_offset": hex(offset),
                                   "source_before": before.hex(), "input_before": before.hex(),
                                   "after": after.hex(), "purpose": purpose})

    prepare = emit("pagination_prepare", """
        stdu 1,-0x100(1)
        std 0,0x20(1)
        mflr 0
        std 0,0x28(1)
        std 3,0x30(1)
        std 4,0x38(1)
        std 5,0x40(1)
        std 6,0x48(1)
        std 7,0x50(1)
        std 8,0x58(1)
        std 9,0x60(1)
        std 10,0x68(1)
        std 11,0x70(1)
        std 12,0x78(1)
        mfcr 0
        std 0,0x80(1)
        stfd 0,0x88(1)
        stfd 1,0x90(1)
        stfd 2,0x98(1)
        stfd 3,0xa0(1)
        stfd 4,0xa8(1)
        stfd 5,0xb0(1)
        lwz 4,0x550(3)
        cmpwi 4,0
        bne prepare_done
        lbz 4,0x28(3)
        cmpwi 4,0
        bne prepare_done
        lwz 4,0x530(3)
        cmpwi 4,0
        beq prepare_done
        li 4,0
        stw 4,0xb8(1)
        lfs 0,0xb8(1)
        lfs 1,0x48(3)
        fcmpu cr0,1,0
        ble prepare_done
        lfs 5,0x88(3)
        fcmpu cr0,5,0
        ble prepare_done
        lfs 0,0x38(3)
        lwz 4,0x510(3)
        cmpwi 4,0
        beq prepare_done
        li 5,0
        li 7,0
        lfs 2,0x68(4)
    prepare_row:
        lfs 3,0x68(4)
        fcmpu cr0,3,2
        beq prepare_height
        fmr 2,3
        mr 7,5
    prepare_height:
        lfs 4,0x98(3)
        lfs 5,0x88(4)
        fmuls 4,4,5
        lfs 5,0x88(3)
        fmuls 4,4,5
        fsubs 5,3,0
        fadds 5,5,4
        fcmpu cr0,5,1
        ble prepare_next
        cmpwi 7,0
        beq prepare_next
        stw 7,0x550(3)
        li 8,1
        stb 8,0x1c(7)
        lwz 9,0x18(7)
        cmpwi 9,3
        bne prepare_done
        stb 8,0x1d(7)
        stb 8,0x22(3)
        stb 8,0x51c(3)
        lwz 9,0x530(3)
        stb 8,0x20(9)
        b prepare_done
    prepare_next:
        mr 5,4
        lwz 4,0x14(4)
        cmpwi 4,0
        bne prepare_row
    prepare_done:
        lfd 0,0x88(1)
        lfd 1,0x90(1)
        lfd 2,0x98(1)
        lfd 3,0xa0(1)
        lfd 4,0xa8(1)
        lfd 5,0xb0(1)
        ld 0,0x80(1)
        mtcrf 255,0
        ld 3,0x30(1)
        ld 4,0x38(1)
        ld 5,0x40(1)
        ld 6,0x48(1)
        ld 7,0x50(1)
        ld 8,0x58(1)
        ld 9,0x60(1)
        ld 10,0x68(1)
        ld 11,0x70(1)
        ld 12,0x78(1)
        ld 0,0x28(1)
        mtlr 0
        ld 0,0x20(1)
        addi 1,1,0x100
        blr
    """)
    advance = emit("pagination_advance", f"""
        lwz 4,0x550(3)
        cmpwi 4,0
        beq advance_native
        lwz 5,0x18(4)
        cmpwi 5,3
        bne advance_native
        lbz 5,0x22(3)
        cmpwi 5,0
        beq advance_native
        stdu 1,-0xc0(1)
        mflr 0
        std 0,0xd0(1)
        std 29,0xa0(1)
        std 30,0xa8(1)
        std 31,0xb0(1)
        stfd 30,0xb8(1)
        mr 31,3
        lwz 29,0x14(4)
        lfs 30,0x68(29)
        lfs 1,0x38(31)
        fsubs 30,30,1
        li 0,0
        stw 0,0x550(31)
    advance_remove:
        lwz 30,0x510(31)
        cmpw 30,29
        beq advance_rebase
        addi 3,31,0x510
        mr 4,30
        bl 0x42fc8
        lwz 3,0x30(30)
        cmpwi 3,0
        beq advance_free_node
        bl 0x63da0
    advance_free_node:
        mr 3,30
        bl 0x63da0
        b advance_remove
    advance_rebase:
        mr 4,29
    advance_rebase_node:
        lfs 1,0x68(4)
        fsubs 1,1,30
        stfs 1,0x68(4)
        lwz 4,0x14(4)
        cmpwi 4,0
        bne advance_rebase_node
        lfs 1,0x88(31)
        fdivs 1,30,1
        lfs 2,0x58(31)
        fsubs 2,2,1
        stfs 2,0x58(31)
        lfs 1,0x524(31)
        fsubs 1,1,30
        stfs 1,0x524(31)
        stw 29,0xf8(31)
        li 4,0
        stb 4,0x22(31)
        stb 4,0x51c(31)
        lwz 3,0x530(31)
        stb 4,0x20(3)
        mr 3,31
        bl {prepare:#x}
        mr 3,31
        lfd 30,0xb8(1)
        ld 29,0xa0(1)
        ld 30,0xa8(1)
        ld 31,0xb0(1)
        ld 0,0xd0(1)
        mtlr 0
        addi 1,1,0xc0
        blr
    advance_native:
        stdu 1,-0x80(1)
        b 0x6f888
    """)
    restore = emit("pagination_restore", f"""
        stdu 1,-0x90(1)
        mflr 0
        std 0,0xa0(1)
        std 30,0x80(1)
        std 31,0x88(1)
        mr 31,3
        li 30,0
    restore_page:
        lwz 4,0x550(31)
        cmpwi 4,0
        beq restore_done
        lwz 5,0x14(4)
        lwz 6,0x18(5)
        cmpwi 6,2
        blt restore_done
        cmpwi 6,3
        bgt restore_done
        lwz 5,0x510(31)
        lwz 7,0xf4(31)
        lwz 8,0(7)
    restore_account:
        lwz 6,0x18(5)
        cmpwi 6,2
        bne restore_account_next
        lwz 9,0x14c8(5)
        add 8,8,9
        li 6,3
        stw 6,0x18(5)
    restore_account_next:
        cmpw 5,4
        beq restore_account_done
        lwz 5,0x14(5)
        b restore_account
    restore_account_done:
        stw 8,0(7)
        li 6,1
        stb 6,0x22(31)
        mr 3,31
        bl {advance:#x}
        li 30,1
        b restore_page
    restore_done:
        cmpwi 30,0
        beq restore_return
        li 4,1
        stb 4,0x22(31)
        lwz 3,0x530(31)
        stb 4,0x20(3)
    restore_return:
        mr 3,31
        ld 30,0x80(1)
        ld 31,0x88(1)
        ld 0,0xa0(1)
        mtlr 0
        addi 1,1,0x90
        blr
    """)
    restore_hook = emit("pagination_restore_complete", f"""
        mr 3,31
        bl {restore:#x}
        li 3,1
        b 0x6fa2c
    """)
    scanner = emit("pagination_scanner_complete", f"""
        mr 3,27
        bl {prepare:#x}
        lbz 3,0x4d8(1)
        lwz 0,0x550(27)
        cmpwi 0,0
        beq scanner_no_boundary
        li 3,1
    scanner_no_boundary:
        b 0x6f0b4
    """)
    render = emit("pagination_render_prepare", f"""
        mr 3,31
        bl {prepare:#x}
        lwz 30,0x510(31)
        b 0x70004
    """)
    initialize = emit("pagination_context_initialize", """
        stb 27,0x22(28)
        stw 27,0x550(28)
        b 0x70b78
    """)
    clear = emit("pagination_context_clear", """
        li 0,0
        stw 0,0x550(3)
        stdu 1,-0x90(1)
        b 0x6de60
    """)
    replace(0x70B20, "li 3,0x560", "Allocate owned per-context automatic-page boundary")
    replace(0x70B74, f"b {initialize:#x}", "Initialize automatic-page state in every context")
    replace(0x6DE5C, f"b {clear:#x}", "Invalidate automatic-page state before native whole-queue clear")
    replace(0x6F884, f"b {advance:#x}", "Advance only completed automatic pages; preserve native waits")
    replace(0x6F0B0, f"b {scanner:#x}", "Block VM at a queued automatic page without changing byte progress")
    replace(0x70000, f"b {render:#x}", "Prepare row-safe automatic-page boundary before queue drawing")
    replace(0x6FA28, f"b {restore_hook:#x}", "Restore the saved raw-byte page without changing save format")
    end = start + len(code)
    result[start:end] = code
    phoff = struct.unpack_from(">Q", result, 0x20)[0]
    struct.pack_into(">QQ", result, phoff + 0x20, end, end)
    report["rx_extension"].update(new_filesz=end, new_memsz=end, file_end=end,
                                  size=end - native_layout_patch.CAVE_START)
    report.update(input_sha256=project.digest(image), output_sha256=project.digest(result),
                  runtime_accepted=False, production_cutover=False)
    report["pagination"] = {"context_allocation": {"old": 0x550, "new": CONTEXT_SIZE},
                             "boundary_field": BOUNDARY,
                             "entries": {key: hex(value) for key, value in entries.items()},
                             "viewport": "context+48 rendered extent; complete row baseline plus captured glyph height",
                             "queue_semantics": "Unread spans stay linked; native completed-prefix unlink/free only on automatic advance",
                             "raw_byte_progress_unchanged": True,
                             "script_controls_added": False, "backlog_and_no_flower_contexts_excluded": True}
    if not native_layout_patch.native_code_matches(bytes(result), bytes(result), report):
        raise ValueError("Complete paginated native correction fails its own equivalence guard")
    return bytes(result), report
