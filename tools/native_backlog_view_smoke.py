"""Bounded encoded backlog scrolling/navigation replay, never controller/GPU proof."""
from __future__ import annotations

import struct
import capstone
import native_backlog_smoke
import native_backlog_view_patch
import project
import save_preview_smoke


def require(condition, message):
    if not condition:
        raise ValueError("Backlog viewport replay: " + message)


def cached_addresses(cpu):
    addresses = []
    for node in cpu.queue():
        index = 0
        while cpu.get(node + 0x94 + index * 20 + 12, 1):
            require(index < 256, "native cache sentinel missing")
            addresses.append(node + 0x94 + index * 20)
            index += 1
    return addresses


def icon_views(cpu):
    """Adapt only the source icon helper's live-register entry, before GPU ABI."""
    observations = []
    pitch, origin, inset = struct.unpack(">3f", cpu.read(0x38648, 12))
    saved = cpu.r[:], cpu.f[:], cpu.cr[:], cpu.pc, cpu.lr
    try:
        for row in (0, 9):
            cpu.r[1] = cpu.STACK - 0x120
            cpu.f[1], cpu.f[31] = row * pitch + origin, inset
            cpu.pc = int(cpu.viewport_entries["position_backlog_voice_icon"], 0)
            for _ in range(128):
                if cpu.pc in (0x38748, 0x38A10):
                    break
                cpu.step()
            else:
                raise ValueError("Backlog viewport replay: icon helper did not reach its guarded boundary")
            y = row * pitch + origin + inset - cpu.get(cpu.CTX + native_backlog_view_patch.OFFSET, 4)
            top = cpu.scalar(cpu.CTX + 0x38)
            bottom = top + cpu.scalar(cpu.CTX + 0x48)
            visible = top <= y and y + 32 <= bottom
            require((cpu.pc == 0x38748) == visible, "source voice icon escaped/missed its viewport")
            if visible:
                require(abs(cpu.f[31] - y) < 0.001, "voice icon did not follow native text offset")
            observations.append({"source_row": row, "visible": visible, "y": cpu.f[31]})
    finally:
        cpu.r[:], cpu.f[:], cpu.cr[:], cpu.pc, cpu.lr = saved
    return observations


def wrapped_coordinate_views(cpu):
    """Adapt cache/scroll storage at short-coordinate boundaries, not navigation."""
    nodes, addresses = cpu.queue(), cached_addresses(cpu)
    origins = {node: cpu.read(node + 0x68, 4) for node in nodes}
    coordinates = {address: cpu.read(address + 2, 2) for address in addresses}
    field = cpu.CTX + native_backlog_view_patch.OFFSET
    original_offset = cpu.get(field, 4)
    observations = []

    def draw():
        start = len(cpu.viewport_glyphs)
        cpu.native_call(0x1B370, cpu.queue_font)
        cpu.native_call(0x70998, cpu.CTX)
        return {glyph["address"]: (glyph["x"], glyph["y"], glyph["rgba"])
                for glyph in cpu.viewport_glyphs[start:]}

    expected = draw()
    require(expected, "coordinate fixture has no visible source glyphs")
    first = min(expected)
    initial_y = int.from_bytes(coordinates[first], "big")
    try:
        for target in (32767, 32768, 65535, 65536):
            shift = target - initial_y
            for node, raw in origins.items():
                cpu.setfloat(node + 0x68, struct.unpack(">f", raw)[0] + shift)
            for address, raw in coordinates.items():
                cpu.put(address + 2, int.from_bytes(raw, "big") + shift, 2)
            cpu.put(field, original_offset + shift, 4)
            actual = draw()
            require(actual == expected, "wrapped cached coordinates changed viewport positions or colour")
            observations.append({"true_first_y": target,
                                 "stored_first_y": cpu.get(first + 2, 2),
                                 "visible_glyphs": len(actual)})
    finally:
        for node, raw in origins.items():
            cpu.write(node + 0x68, raw)
        for address, raw in coordinates.items():
            cpu.write(address + 2, raw)
        cpu.put(field, original_offset, 4)
    return observations


def reachable_views(cpu):
    """Draw/scroll the existing completed record; return ordered emitted glyphs.

    The source scanner and cache producer have already run through settle().
    Only 69FE8's native input-handler boundary is entered directly; neither
    cached glyph coordinates nor the scroll offset are assigned by this replay.
    """
    addresses = cached_addresses(cpu)
    expected = set(addresses)
    seen, offsets, views = {}, [], []
    cursor = 0
    initial_nodes = cpu.queue()
    field = cpu.CTX + native_backlog_view_patch.OFFSET
    for _ in range(4096):
        offset = cpu.get(field, 4)
        offsets.append(offset)
        emitted = []
        for glyph in cpu.viewport_glyphs[cursor:]:
            if glyph["address"] not in expected:
                continue
            node = next(node for node in initial_nodes
                        if node + 0x94 <= glyph["address"] < node + 0x1494)
            top = int(cpu.scalar(cpu.CTX + 0x38))
            bottom = int(cpu.scalar(cpu.CTX + 0x38) + cpu.scalar(cpu.CTX + 0x48))
            cell = int(cpu.scalar(cpu.CTX + 0x98) * cpu.scalar(cpu.CTX + 0x88)
                       * cpu.scalar(node + 0x88)) + 1
            require(top <= glyph["y"] and glyph["y"] + cell <= bottom,
                    "a submitted native glyph cell escaped the viewport")
            seen[glyph["address"]] = glyph
            emitted.append(glyph["address"])
        cursor = len(cpu.viewport_glyphs)
        views.append({"offset": offset, "glyphs": len(set(emitted)), "voice_icons": icon_views(cpu)})
        if set(seen) == expected:
            break
        cpu.native_call(0x69FE8, cpu.CTX, 1)
        require(cpu.queue() == initial_nodes, "scroll changed the logical history entry")
        require(cpu.get(field, 4) > offset, "unreachable glyphs remain at the last native view")
        cpu.native_call(0x1B370, cpu.queue_font)
        cpu.native_call(0x70998, cpu.CTX)
    else:
        raise ValueError("Backlog viewport replay: finite navigation bound exceeded")
    require(set(seen) == expected, "not every cached glyph entered the viewport")
    return {"offsets": offsets, "views": views, "glyph_count": len(seen),
            "complete_text": b"".join(seen[address]["text"] for address in addresses),
            "opaque_text": b"".join(seen[address]["text"] for address in addresses
                                      if seen[address]["alpha"] or seen[address]["text"] == b" ")}


def smoke(source, image, native, payload, paragraph):
    require(native.get("backlog_view") and native.get("history"), "finished correction missing")
    require(project.digest(source) == native["source_sha256"], "immutable source/report mismatch")
    require(project.digest(image) == native["output_sha256"], "corrected image/report mismatch")
    require(all(token in paragraph for token in (b"[H01]", b"[H02]", b"[H08]", b"[HEND]")),
            "full diagnostic H01-H08/HEND paragraph required")
    decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)

    def source_instruction(pc):
        ins = next(decoder.disasm(source[pc - 0x10000:pc - 0x10000 + 4], pc))
        return ins.mnemonic, ins.op_str

    require(source_instruction(0x5D45C) == ("li", "r3, 0x400")
            and source_instruction(0x5D460) == ("bl", "0x59dd0")
            and source_instruction(0x5D470) == ("li", "r4, -1")
            and source_instruction(0x5D478) == ("bl", "0x69fe8"), "source older repeat path differs")
    require(source_instruction(0x5D484) == ("li", "r3, 0x800")
            and source_instruction(0x5D488) == ("bl", "0x59dd0")
            and source_instruction(0x5D498) == ("li", "r4, 1")
            and source_instruction(0x5D4A0) == ("bl", "0x69fe8"), "source newer repeat path differs")
    require(source_instruction(0x6400C) == ("li", "r5, 1")
            and source_instruction(0x64014) == ("bl", "0x70af8"), "source mode1 construction differs")
    older = b"Older owned voice-group record."
    newest = b"Newest owned record; reopen returns here."
    cpu = native_backlog_smoke.BacklogCPU(source, image, native, payload, paragraph, parent_progress=32)
    cpu.initialize()
    cpu.native_call(0x69ABC, 321, 0, 1)
    cpu.append(older)
    cpu.native_call(0x69D0C)
    cpu.append(paragraph)
    cpu.native_call(0x69D0C)
    cpu.append(newest)
    arena, field = cpu.arena, cpu.CTX + native_backlog_view_patch.OFFSET
    record_snapshot = cpu.read(arena + 0x10, 100 * 0x354)
    owned_payloads = []
    for index in range(100):
        record = arena + 0x10 + index * 0x354
        pointer, capacity = cpu.get(record + 12, 4), cpu.get(record + 16, 4)
        owned_payloads.append((pointer, cpu.read(pointer, capacity)))
    accounting = cpu.read(arena + 0x14CE0, 0x10)

    def intact():
        require(cpu.read(arena + 0x10, 100 * 0x354) == record_snapshot,
                "navigation rewrote history slots/metadata/ownership")
        require(all(cpu.read(pointer, len(data)) == data for pointer, data in owned_payloads),
                "navigation rewrote an owned history payload")
        require(cpu.read(arena + 0x14CE0, 0x10) == accounting,
                "navigation changed native writer/count/append accounting")
        require(cpu.parent_snapshot == (cpu.read(cpu.PARENT, 0x560), cpu.read(cpu.SPANS, 0x15E0)),
                "navigation changed gameplay parent state")
        require(cpu.read(cpu.STATE + 0x20, 4) == cpu.raw_checkpoint_snapshot,
                "navigation changed raw gameplay progress")
        cpu.assert_flags()

    def settle_text(expected):
        rows = cpu.settle(isolate_updates=True)
        require(b"".join(row["glyphs"] for row in rows) == expected,
                "native reconstructed record text/order differs")
        require(all(row["state"] == 3 for row in rows), "record did not complete reveal")
        proof = reachable_views(cpu)
        require(proof["complete_text"] == expected and proof["opaque_text"] == expected,
                "complete opaque record did not reach viewport submissions")
        require(proof["glyph_count"] == len(save_preview_smoke.units(expected)),
                "viewport glyph coverage differs from complete source text")
        intact()
        return proof

    cpu.native_call(0x69FE8, cpu.CTX, 0)
    newest_proof = settle_text(newest)
    cpu.native_call(0x69FE8, cpu.CTX, -1)
    require(cpu.get(field, 4) == 0, "older record did not start at its first view")
    rows = cpu.settle(isolate_updates=True)
    require(max(cpu.scalar(row["node"] + 0x68)
                + cpu.scalar(cpu.CTX + 0x98) * cpu.scalar(cpu.CTX + 0x88)
                * cpu.scalar(row["node"] + 0x88) for row in rows)
            > cpu.scalar(cpu.CTX + 0x38) + cpu.scalar(cpu.CTX + 0x48),
            "long fixture is not taller than the actual source viewport")
    long_proof = reachable_views(cpu)
    require(long_proof["complete_text"] == paragraph and long_proof["opaque_text"] == paragraph,
            "H01-H08/HEND complete text/opacity is inaccessible")
    require(len(long_proof["offsets"]) > 1, "long fixture never used native scroll")
    for token in (b"[H01]", b"[H02]", b"[H08]", b"[HEND]"):
        require(token in long_proof["complete_text"], "section never reached a native view")
    intact()
    # Up consumes intra-record offsets before calling the original ring selector.
    while cpu.get(field, 4):
        before = cpu.get(field, 4)
        nodes = cpu.queue()
        cpu.native_call(0x69FE8, cpu.CTX, -1)
        require(cpu.queue() == nodes and cpu.get(field, 4) < before,
                "up changed records before reaching the first view")
    cpu.native_call(0x69FE8, cpu.CTX, -1)
    older_proof = settle_text(older)
    cpu.native_call(0x69FE8, cpu.CTX, 1)
    require(cpu.get(field, 4) == 0, "newer record retained another record's offset")
    repeated_long = settle_text(paragraph)
    cpu.native_call(0x69FE8, cpu.CTX, 1)
    require(cpu.get(field, 4) == 0, "newest record did not reset scroll")
    settle_text(newest)
    cpu.native_call(0x6A474, cpu.CTX)
    require(not cpu.queue() and cpu.get(cpu.CTX + 0x29, 1) == 0,
            "native close did not release/hide the backlog queue")
    intact()
    cpu.native_call(0x69FE8, cpu.CTX, 0)
    cpu.put(cpu.CTX + 0x29, 1, 1)  # Source 5DF08..5DF14 caller visibility boundary.
    require(cpu.get(field, 4) == 0, "reopen inherited an obsolete scroll offset")
    reopen_proof = settle_text(newest)
    coordinate_proof = wrapped_coordinate_views(cpu)
    intact()
    require(cpu.get(arena + 0x14CEC, 4) == 2, "viewport added fake logical history records")
    entries = native["backlog_view"]["entries"]
    require(all(int(entries[name], 0) in cpu.executed for name in
                ("navigate_record_viewport", "reset_rebuilt_record_scroll", "clipped_cache_consumer",
                 "draw_backlog_viewport")), "correction helpers were not actually executed")
    return {"source_sha256": project.digest(source), "image_sha256": project.digest(image),
            "native_controls": {"older_repeat": "5D45C/5D460/5D478: 0x400 -> 69FE8(-1)",
                                "newer_repeat": "5D484/5D488/5D4A0: 0x800 -> 69FE8(+1)"},
            "source_geometry": {"x": 160, "y": 52, "width": 984, "height": 628,
                                "position_y_scale": cpu.scalar(cpu.CTX + 0x88),
                                "font_cell": cpu.scalar(cpu.CTX + 0x98),
                                "normal_row_pitch": cpu.scalar(cpu.CTX + 0x88) * cpu.scalar(cpu.CTX + 0x98)},
            "history_records": 3, "logical_slots": 100, "owned_payloads_preserved": True,
            "metadata_voice_group_preserved": True, "gameplay_progress_flags_parent_preserved": True,
            "long_record": {key: value for key, value in long_proof.items()
                            if key not in ("complete_text", "opaque_text")},
            "older_views": older_proof["offsets"], "newest_views": newest_proof["offsets"],
            "newer_long_views": repeated_long["offsets"], "reopen_views": reopen_proof["offsets"],
            "signed_coordinate_views": coordinate_proof,
            "complete_text_sha256": project.digest(long_proof["complete_text"]),
            "all_glyphs_enter_viewport": True, "offscreen_submissions": 0,
            "close_reopen_native_queue": True, "runtime_accepted": False,
            "limitations": ["Finite encoded CPU/FP replay, not controller polling, GPU pixels or a full scheduler run.",
                            "Source repeat-button callers are disassembled/guarded; their 69FE8 boundary is directly invoked with the same arguments.",
                            "Voice-icon helper executes from adapted source live registers to its pre-GPU continuation/clip return; no icon GPU submission is simulated.",
                            "Shared font/resource/allocator/libc fixtures and source-cell viewport bounds; no rasterized ink/scissor proof.",
                            "Each adapted drawing frame executes native1B370 to reset the finite font submission queue; no GPU flush or scheduler is claimed.",
                            "Per-span updates temporarily isolate queue nodes as in the existing long-paragraph replay, restoring the full queue before native drawing.",
                            "Signed16/unsigned16 wrap cases adapt cache coordinates, full-precision span origins and scroll storage before executing the real draw consumer; not a huge-record scheduler replay.",
                            "Caller visibility store on reopen is an explicit adapted boundary; native69FE8/6A474 record and queue lifecycle execute.",
                            "The fixture exercises source 48-pixel font cells with source 1.3 vertical placement scale; intrinsically viewport-taller individual glyphs are not resized."]}
