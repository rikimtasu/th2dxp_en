"""Finite encoded literal/opacity/save replay; no native FP/GPU/emulator claim."""
from __future__ import annotations

import struct

import capstone
import native_pagination_smoke
from native_scanner_model import MASK
import native_runtime_text_patch as patch
import project
import scenario_source


def require(condition, message):
    if not condition:
        raise ValueError("Runtime text replay: " + message)


class RuntimeCPU(native_pagination_smoke.Replay):
    CTX, TEXT, FONTS, RANGES = 0xE00000, 0xE10000, 0xE20000, 0xE21000
    STRINGS, SPANS, SPAN_END, STACK = 0xE30000, 0xE40000, 0xEE0000, 0x1200000
    VM, PROGRAM, ENGINE, HEAP = 0xEE0000, 0xF00000, 0xE04000, 0xF20000
    STATE = 0x6671B4

    def __init__(self, source, image, report, text, payload, body_offset, **options):
        self.SPAN_SIZE = report.get("runtime_text", {}).get("span_allocation", 0x14D0)
        super().__init__(source, text, image=image, patch_report=report, **options)
        self.runtime = report.get("runtime_text", {})
        self.scratch = self.runtime.get("vm_scratch", 0x174)
        self.heap = {}
        self.heap_next = self.HEAP
        self.heap_fill = 0
        self.decoder_calls = 0
        self.backlog_submissions = []
        self.skip_mode = False
        self.glyph_calls = []
        self.code_start = 16 + 36 * struct.unpack_from("<I", payload, 8)[0]
        self.write(self.PROGRAM, payload)
        self.put(self.VM + 0x144, self.PROGRAM, 4)
        self.put(self.VM + 0x138, self.PROGRAM + self.code_start, 4)
        self.put(self.VM + 0x13C, len(payload), 4)
        self.put(self.VM + 0x79C, patch.TABLE_VA, 4)
        self.put(self.VM + 0x160, self.ENGINE + 0x1000, 4)
        self.put(self.VM + 0x164, self.ENGINE + 0x1000, 4)
        self.put(self.VM + 0x15C, 256, 4)
        self.put(0x652614, self.ENGINE, 4)
        self.put(self.ENGINE + 0x7C, self.VM, 4)
        self.put(self.ENGINE + 0x80, self.STATE, 4)
        self.put(self.ENGINE + 0x2B0, self.CTX, 4)
        self.put(self.CTX + 0xF0, self.STATE + 0x128, 4)
        self.put(self.CTX + 0xFC, self.STATE + 0x12C, 4)
        self.put(self.CTX + 0xF4, self.STATE + 0x20, 4)
        self.write(self.STATE + 0x128, bytes(0x304))
        # Real main-state date flags and adjacent fields, not an unbounded fake
        # text arena. This sentinel catches the original saved-state corruption.
        self.write(0x667628, bytes((3, 1, 0, 255)) + b"FLAG-INVARIANT" * 10)
        self.flag_snapshot = self.read(0x667628, 144)
        # Keep synthetic metric objects out of the real font object's opacity
        # extent; source drawing uses a different object from its range fonts.
        for index in range(4):
            previous = self.get(self.FONTS + index * 4, 4)
            current = self.FONTS + 0x3000 + index * 0x100
            self.write(current, self.read(previous, 0x100))
            self.put(self.FONTS + index * 4, current, 4)
        self.TEXT = self.VM + self.scratch
        self.body_offset = body_offset
        decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        decoder.skipdata = True
        for begin, end in ((0x43550, 0x43E60), (0x590E8, 0x591B8), (0x59878, 0x5989C),
                           (0x6D9F8, 0x6DAFC), (0x6FCDC, 0x7084C),
                           (0x44750, 0x44754), (0x4453C, 0x44540)):
            self.code.update({ins.address: (ins.mnemonic, ins.op_str)
                              for ins in decoder.disasm(self.read(begin, end - begin), begin)})

    def step(self):
        mnemonic, operands = self.code[self.pc]
        if mnemonic == "trap":
            raise ValueError("Runtime text replay: native checkpoint guard trapped")
        if mnemonic == "andi.":
            dest, value, immediate = operands.split(", ")
            result = self.number(value) & self.number(immediate)
            self.r[int(dest[1:])] = result
            self.compare(0, result, 0)
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        if mnemonic in ("mtctr", "bdnz", "bdz"):
            self.executed.add(self.pc)
            if mnemonic == "mtctr":
                self.ctr = self.number(operands)
                self.pc += 4
            else:
                self.ctr = (self.ctr - 1) & MASK
                taken = bool(self.ctr) if mnemonic == "bdnz" else not self.ctr
                self.pc = self.number(operands) if taken else self.pc + 4
            self.steps += 1
            return
        if mnemonic == "subfic":
            dest, value, immediate = operands.split(", ")
            left, right = self.number(value), self.number(immediate) & MASK
            self.r[int(dest[1:])] = (right - left) & MASK
            self.xer_ca = right >= left
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        if mnemonic == "cntlzw":
            dest, value = operands.split(", ")
            self.r[int(dest[1:])] = 32 - (self.number(value) & 0xFFFFFFFF).bit_length()
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        if mnemonic in ("vspltb", "vsplth", "vcfux", "vctuxs", "stvebx", "stvehx"):
            args = [value.strip() for value in operands.split(",")]
            index = lambda value: int(value[1:])
            dest = index(args[0])
            if mnemonic in ("stvebx", "stvehx"):
                size = 1 if mnemonic == "stvebx" else 2
                address = self.indexed(args[1], args[2])
                lane = (address & 15) & -size
                self.write(address & -size, self.v[dest][lane:lane + size])
            elif mnemonic in ("vspltb", "vsplth"):
                size = 1 if mnemonic == "vspltb" else 2
                lane = int(args[2], 0) * size
                self.v[dest] = self.v[index(args[1])][lane:lane + size] * (16 // size)
            elif mnemonic == "vcfux":
                self.setv(dest, [value / 2 ** int(args[2], 0) for value in self.vu(index(args[1]))], True)
            else:
                self.setv(dest, [max(0, min(0xFFFFFFFF, int(value * 2 ** int(args[2], 0))))
                                 for value in self.vf(index(args[1]))])
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        if mnemonic in ("vsrw", "vrlw", "vsel"):
            args = [int(value.strip()[1:]) for value in operands.split(",")]
            dest, a, b = args[:3]
            if mnemonic == "vsel":
                mask = self.vu(args[3])
                values = [(x & ~m) | (y & m) for x, y, m in zip(self.vu(a), self.vu(b), mask)]
            elif mnemonic == "vsrw":
                values = [x >> (y & 31) for x, y in zip(self.vu(a), self.vu(b))]
            else:
                values = [((x << (y & 31)) | (x >> ((32 - y) & 31))) & 0xFFFFFFFF
                          for x, y in zip(self.vu(a), self.vu(b))]
            self.setv(dest, values)
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        super().step()

    def call(self, target):
        if target == 0xD83A4:
            self.write(self.r[3], bytes([self.r[4] & 255]) * self.r[5])
            self.lr = self.pc + 4
            return self.pc + 4
        if target in (0x45580, 0x591B8, 0x591C0, 0x591C8, 0x591D4, 0x5923C, 0x594E8,
                      0x8CE40, 0x8BECC, 0x8CE60, 0x8BED8):
            if target == 0x45580:
                self.write(self.r[3], bytes(16))
            elif target == 0x591B8:
                self.put(self.r[3] + 0x5C, self.r[4], 4)
            elif target == 0x591C0:
                self.setfloat(self.r[3] + 0x58, self.f[1])
            elif target == 0x591C8:
                self.setfloat(self.r[3] + 0xC4, self.f[1])
                self.setfloat(self.r[3] + 0xC8, self.f[2])
            elif target in (0x591D4, 0x5923C):
                self.write(self.r[3] + (0xA4 if target == 0x591D4 else 0xB4), self.read(self.r[4], 16))
            elif target == 0x594E8:
                self.glyph_calls.append({"node": self.r[30], "text": self.string(self.get(self.r[3] + 0x138, 4)),
                                         "opacity": self.read(self.r[3] + 0x164, 256)})
            else:
                self.r[3] = int(self.skip_mode and target != 0x8BED8)
            self.lr = self.pc + 4
            return self.pc + 4
        if target in (0x63D70, 0xE29FC):
            size = self.r[3]
            pointer = (self.heap_next + 15) & ~15
            require(0 < size <= 0x200000 and pointer + size < self.STACK - 0x10000, "heap fixture bound")
            self.heap_next = pointer + size
            self.heap[pointer] = size
            self.write(pointer, bytes([self.heap_fill]) * size)
            self.r[3], self.lr = pointer, self.pc + 4
            return self.pc + 4
        if target in (0x63DA0, 0xE2950) and self.r[3] in self.heap:
            del self.heap[self.r[3]]
            self.r[3], self.lr = 0, self.pc + 4
            return self.pc + 4
        if target == 0x28D28:
            destination, size, pointer, slot = self.r[3:7]
            raw = self.read(pointer, slot)
            decoded, _ = scenario_source.read_chunks(raw, 0, slot, size)
            require(self.heap.get(destination) == len(decoded), "decoder output differs from owned allocation")
            self.write(destination, decoded)
            self.decoder_calls += 1
            self.lr = self.pc + 4
            return self.pc + 4
        if target == 0x69B38:
            self.backlog_submissions.append(self.string(self.r[3]))
            self.lr = self.pc + 4
            return self.pc + 4
        return super().call(target)

    def decode_literal(self):
        """Execute the actual native 0A handler and common cursor advance."""
        saved = self.r[:], self.f[:], self.v[:], self.cr[:], self.lr, self.pc
        self.r[31] = self.VM
        self.r[27], self.r[26], self.r[25] = self.VM + 0x148, self.VM + 0x164, self.TEXT
        self.r[28] = 0x43544
        self.r[4] = self.body_offset - self.code_start - 2
        self.put(self.VM + 0x148, self.r[4], 4)
        self.r[30] = 0
        self.setv(29, [0x0000FF00] * 4)
        self.f[30] = self.f[31] = 0.0
        self.pc = 0x436F0
        self.execute_until(0x437B8)
        copied = self.string(self.TEXT)
        consumed = self.r[30]
        self.pc = 0x43E28
        while self.pc not in (0x43E5C, 0x435F4):
            self.step()
        next_byte = self.get(self.PROGRAM + self.code_start + self.get(self.VM + 0x148, 4), 1)
        self.r, self.f, self.v, self.cr, self.lr, self.pc = saved
        self.r[4] = self.TEXT
        return {"copied_bytes": len(copied), "consumed_bytes": consumed,
                "next_byte": next_byte, "text": copied}

    def assert_flags(self):
        require(self.read(0x667628, 144) == self.flag_snapshot, "raw text overwrote native date/story flags")

    def opacity_copy(self, text, values):
        span = self.SPANS
        alpha = self.runtime.get("span_alpha", 0x1494)
        self.write(span + alpha, bytes(values))
        self.write(self.TEXT, text + b"\0")
        self.r[3:6] = [self.FONTS, self.TEXT, span + alpha]
        self.pc, self.lr = 0x590E8, native_pagination_smoke.STOP
        self.execute_until(native_pagination_smoke.STOP)
        observed = []
        for index in range(len(text)):
            self.r[22], self.r[19], self.r[27] = self.FONTS + index, 255, 255
            self.pc = 0x59878
            self.execute_until(0x5989C)
            observed.append(self.get(self.r[4], 1))
        return observed

    def skip_pages(self, *, settle_opacity=False):
        """Execute native skip/resume; optionally hold each pause for opacity."""
        self.skip_mode = True
        initial = self.queue()
        expected = b"".join(self.string(self.get(node + 0x30, 4)) for node in initial)
        expected_progress = self.get(self.STATE + 0x20, 4) + sum(
            self.get(node + 0x14C8, 4) for node in initial if self.get(node + 0x18, 4) != 3)
        frames = advances = 0
        while any(self.get(node + 0x18, 4) != 3 for node in self.queue()):
            require(frames < 100, "skip did not make bounded progress")
            self.r[4] = self.get(self.CTX + 0x510, 4)
            self.pc, self.lr = 0x6FCDC, native_pagination_smoke.STOP
            self.execute_until(native_pagination_smoke.STOP)
            self.r[3:7] = [self.CTX, 1, 1, 0]
            self.pc, self.lr = 0x6FD48, native_pagination_smoke.STOP
            self.execute_until(native_pagination_smoke.STOP)
            frames += 1
            self.assert_flags()
            if settle_opacity:
                self.r[3:7] = [self.CTX, 1, 1, 0]
                self.pc, self.lr = 0x6FD48, native_pagination_smoke.STOP
                self.execute_until(native_pagination_smoke.STOP)
                frames += 1
            if self.get(self.CTX + 0x22, 1):
                self.invoke(0x6F884)
                advances += 1
        observed, visible = {}, set()
        for row in self.glyph_calls:
            observed.setdefault(row["node"], row["text"])
            glyphs = len(row["text"].decode("cp932"))
            if glyphs and all(row["opacity"][:glyphs]):
                visible.add(row["node"])
        require(set(observed) == set(initial), "native skip did not submit every queued span")
        require(b"".join(observed[node] for node in initial) == expected, "native skip lost or reordered submitted text")
        require(self.get(self.STATE + 0x20, 4) == expected_progress, "native skip lost raw VM progress")
        if settle_opacity:
            require(visible == set(initial), "held pages retained invisible glyphs at the modeled draw boundary")
        self.assert_flags()
        return {"frames": frames, "automatic_advances": advances,
                "native_skip_renderer_wait_resume_executed": True,
                "full_text_presented_to_draw_boundary": True,
                "opacity_settled_before_advances": settle_opacity,
                "full_text_visible_at_modeled_draw_boundary": visible == set(initial),
                "raw_vm_progress": self.get(self.STATE + 0x20, 4),
                "global_date_story_flags_preserved": True}

    def replay_saved(self, trace, *, checkpoint=0):
        self.write(self.STATE + 0x12C, trace)
        self.put(self.STATE + 0x128, len(trace), 4)
        self.r[31], self.r[27] = self.ENGINE, checkpoint
        self.pc = int(self.runtime["entries"]["replay_saved_literal_references"], 0)
        self.execute_until(0x5CC30)


def checkpoint_edges(source, image, native, payload, offset, long_text, trace):
    def fixture():
        return RuntimeCPU(source, image, native, b"A", payload, offset, dialogue=True, height=628)

    mixed = fixture()
    mixed.replay_saved(b"OLD\0" + trace * 2)
    expected = b"OLD" + long_text * 2
    actual = b"".join(mixed.string(mixed.get(node + 0x30, 4)) for node in mixed.queue())
    require(actual == expected and mixed.backlog_submissions == [b"OLD", long_text, long_text],
            "mixed legacy/reference entries lost or reordered text")
    require(mixed.decoder_calls == 1 and not mixed.heap, "same-program references did not share/release the decoder")
    mixed.assert_flags()

    restored = fixture()
    restored.replay_saved(trace, checkpoint=600)
    restored.invoke(0x6F8F0)
    remaining = restored.queue()
    remaining_text = b"".join(restored.string(restored.get(node + 0x30, 4)) for node in remaining)
    prefix = restored.get(restored.STATE + 0x20, 4)
    require(0 < prefix < 600 and remaining_text == long_text[prefix:],
            "saved reference did not restore the later page without losing unread text")
    require(restored.scalar(remaining[0] + 0x68) == 0, "restored reference retained prior-page Y")
    resumed = restored.skip_pages(settle_opacity=True)
    require(resumed["raw_vm_progress"] == len(long_text), "restored reference double-counted raw bytes")

    original = b"ORIGINAL0000"
    dynamic_payload = bytes(16) + b"\x0a" + struct.pack("<H", len(original)) + original + b"\x02"
    dynamic = RuntimeCPU(source, image, native, b"A", dynamic_payload, 19, dialogue=True, height=628)
    dynamic.decode_literal()
    replacement = b"REPLACED0000"
    dynamic.write(dynamic.TEXT, replacement + b"\0")
    dynamic.run()
    require(dynamic.read(dynamic.STATE + 0x12C, 13) == replacement + b"\0",
            "a modified scratch string was incorrectly saved as its stale source reference")
    dynamic.assert_flags()

    exact = fixture()
    exact.decode_literal()
    exact.write(exact.STATE + 0x12C, trace * 95)
    exact.put(exact.STATE + 0x128, patch.TRACE_CAPACITY - 8, 4)
    exact.run()
    require(exact.get(exact.STATE + 0x128, 4) == patch.TRACE_CAPACITY
            and exact.read(exact.STATE + 0x12C + patch.TRACE_CAPACITY - 8, 8) == trace,
            "last fitting reference was rejected or changed")
    exact.assert_flags()

    guarded = []
    for name, used, data in (
        ("partial_reference", 4, trace[:4]),
        ("invalid_program", 8, struct.pack(">II", patch.TRACE_TAG, 2047 << 21)),
        ("unterminated_inline", 4, b"ABCD"),
        ("unaligned_length", 3, b"AB\0"),
        ("oversized_length", patch.TRACE_CAPACITY + 4, b""),
    ):
        model = fixture()
        model.write(model.STATE + 0x12C, data)
        model.put(model.STATE + 0x128, used, 4)
        model.r[31], model.r[27] = model.ENGINE, 0
        model.pc = int(model.runtime["entries"]["replay_saved_literal_references"], 0)
        try:
            model.execute_until(0x5CC30)
        except ValueError as error:
            require("native checkpoint guard trapped" in str(error), name + ": unexpected rejection")
        else:
            raise ValueError("Runtime text replay accepted invalid " + name)
        model.assert_flags()
        require(not model.backlog_submissions, name + ": submitted malformed text")
        guarded.append(name)
    for name, used in (("full_trace", patch.TRACE_CAPACITY), ("wrapped_length", 0xFFFFFFFC)):
        model = fixture()
        model.decode_literal()
        model.put(model.STATE + 0x128, used, 4)
        before = model.read(model.STATE + 0x12C, patch.TRACE_CAPACITY)
        try:
            model.run()
        except ValueError as error:
            require("native checkpoint guard trapped" in str(error), name + ": unexpected rejection")
        else:
            raise ValueError("Runtime text replay accepted invalid " + name)
        require(model.read(model.STATE + 0x12C, patch.TRACE_CAPACITY) == before,
                name + ": guard partially wrote the trace")
        model.assert_flags()
        guarded.append(name)
    return {"legacy_and_two_references_replayed_in_order": True,
            "same_program_reference_decoder_calls": mixed.decoder_calls,
            "modified_scratch_preserved_inline": True,
            "last_fitting_reference_accepted": True,
            "saved_later_page_prefix_bytes": prefix, "saved_later_page_resume": resumed,
            "invalid_entries_rejected_before_submission": guarded}


def smoke(image, native, failed_image, failed_native, long_text):
    source = project.source_bytes()
    scanned = scenario_source.scan(image, project.codec())
    payload = next(payload for entry, payload, name, chunks in scanned if name == "010301000")
    offset = payload.find(long_text)
    require(offset >= 3 and payload[offset - 3] == 10, "actual diagnostic literal binding")
    before = RuntimeCPU(source, failed_image, failed_native, long_text, payload, offset, dialogue=True, height=628)
    before_literal = before.decode_literal()
    require(before_literal["copied_bytes"] == 1023 and before_literal["next_byte"] != 2,
            "original VM literal truncation was not reproduced")
    before.run()
    flag_offset = 0x667628 - (before.STATE + 0x12C)
    require(before.read(0x667628, 2) == before_literal["text"][flag_offset:flag_offset + 2]
            and before.read(0x667628, 2) != before.flag_snapshot[:2],
            "original single-literal global flag corruption was not reproduced")
    corrected = RuntimeCPU(source, image, native, long_text, payload, offset, dialogue=True, height=628)
    corrected.write(corrected.VM + 0x574, b"M" * 0x200)
    locals_before = corrected.read(corrected.VM + 0x574, 0x200)
    after_literal = corrected.decode_literal()
    require(after_literal["text"] == long_text and after_literal["next_byte"] == 2,
            "full literal bytes or VM terminator were lost")
    corrected.run()
    corrected.assert_flags()
    require(corrected.read(corrected.VM + 0x574, 0x200) == locals_before, "long scratch changed VM locals")
    require(corrected.get(corrected.STATE + 0x128, 4) == 8, "long literal was not stored as one bounded reference")
    trace = corrected.read(corrected.STATE + 0x12C, 8)
    require(struct.unpack_from(">I", trace)[0] == patch.TRACE_TAG, "checkpoint reference marker differs")
    pagination = native_pagination_smoke.paginate(corrected)
    require(pagination["raw_vm_progress"] == len(long_text), "full source-byte progress was not retained")
    corrected.assert_flags()
    opacity_values = [(index * 3 + 17) & 255 for index in range(256)]
    opacity_text = b"W" * len(opacity_values)
    old_alpha = RuntimeCPU(source, failed_image, failed_native, b"A", payload, offset)
    new_alpha = RuntimeCPU(source, image, native, b"A", payload, offset)
    previous = old_alpha.opacity_copy(opacity_text, opacity_values)
    current = new_alpha.opacity_copy(opacity_text, opacity_values)
    require(previous[32] != opacity_values[32] and current == opacity_values,
            "native opacity copy/consumer boundary did not expose and fix glyph32 aliasing")
    require(new_alpha.get(new_alpha.FONTS + 0x15C, 4) == len(opacity_text), "opacity writes changed raw byte length")
    constructor = RuntimeCPU(source, image, native, b"A", payload, offset)
    constructor.heap_fill = 0xA5
    constructor.write(constructor.TEXT, b"A\0")
    constructor.r[3:5] = [constructor.CTX + 0x510, constructor.TEXT]
    constructor.pc, constructor.lr = 0x6D9F8, native_pagination_smoke.STOP
    constructor.execute_until(0x6DACC)
    span = constructor.r[29]
    require(constructor.heap[span] == native["runtime_text"]["span_allocation"]
            and constructor.read(span + patch.SPAN_ALPHA - 1, 257) == bytes(257),
            "native constructor failed to clear owned opacity storage and its predecessor")
    bounds = []
    for length in (1023, 1024, 65535):
        text = b"A" * length
        synthetic = bytes(16) + b"\x0a" + struct.pack("<H", length) + text + b"\x02"
        model = RuntimeCPU(source, image, native, b"A", synthetic, 19)
        model.write(model.VM + 0x574, b"M" * 0x200)
        model.write(model.VM + patch.VM_SIZE, b"VM-END")
        decoded = model.decode_literal()
        require(decoded["text"] == text and decoded["next_byte"] == 2
                and model.read(model.VM + 0x574, 0x200) == b"M" * 0x200
                and model.read(model.VM + patch.VM_SIZE, 6) == b"VM-END",
                "u16 literal boundary changed bytecode, VM locals or allocation end")
        bounds.append(length)
    edges = checkpoint_edges(source, image, native, payload, offset, long_text, trace)
    skipped = RuntimeCPU(source, image, native, b"A", payload, offset, dialogue=True, height=628)
    skipped.decode_literal()
    skipped.run()
    fast = skipped.skip_pages()
    held = RuntimeCPU(source, image, native, b"A", payload, offset, dialogue=True, height=628)
    held.decode_literal()
    held.run()
    settled = held.skip_pages(settle_opacity=True)
    return {"kind": "encoded native literal, opacity, bounded save trace and paging replay",
            "source_sha256": project.digest(source), "image_sha256": project.digest(image),
            "original_vm_literal_bytes": before_literal["copied_bytes"],
            "corrected_vm_literal_bytes": after_literal["copied_bytes"],
            "full_literal_vm_terminator_preserved": True,
            "global_date_story_flags_preserved": True, "vm_locals_preserved": True,
            "checkpoint_storage_bytes": len(trace), "raw_text_bytes": len(long_text),
            "checkpoint_full_text_replayed": True, "native_opacity_glyphs_checked": len(current),
            "opacity_alias_boundary_indices": [31, 32, 35, 36, 63, 79, 255],
            "native_opacity_constructor_predecessor_zeroed": True,
            "u16_literal_boundary_lengths": bounds, "checkpoint_edges": edges,
            "native_fast_skip": fast, "native_held_pages": settled,
            "pagination": pagination, "runtime_accepted": False,
            "limitations": ["Finite software instruction replay, not native FP, full VM, GPU or emulator execution.",
                            "Heap ownership, LZMA decoding, span construction and backlog submission are explicit modeled boundaries.",
                            "The save slot layout remains fixed; tagged reference entries require the corrected reader and the same staged scenario payloads.",
                            "Existing corrupted saves are not repaired; fresh diagnostic progression is required."]}
