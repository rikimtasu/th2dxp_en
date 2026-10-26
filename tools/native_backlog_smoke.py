"""Execute backlog construction, reveal, cached glyph generation and traversal.

Font/resource objects and heap/libc are finite fixtures. Native span constructor,
scanner, renderer and glyph producer/consumer instructions execute unchanged.
GPU submission, parent-window decoration and controller polling are boundaries.
"""
from __future__ import annotations

import struct
import math

import capstone
import native_history_smoke
import native_pagination_smoke
import native_runtime_text_smoke
from native_scanner_model import MASK, signed
import project
import save_preview_smoke


def require(condition, message):
    if not condition:
        raise ValueError("Backlog rendering replay: " + message)


class BacklogCPU(native_history_smoke.HistoryCPU):
    PARENT = 0xE08000

    def __init__(self, source, image, native, payload, text, *, parent_progress=None):
        super().__init__(source, image, native, payload, text)
        self.MAX_STEPS = 80000000
        self.MAX_CALLS = 1000000
        decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        decoder.skipdata = True
        ranges = ((0x43214, 0x432A4), (0x42F70, 0x42FA0), (0x455F8, 0x4563C),
                  (0x6DAFC, 0x6DE5C), (0x59338, 0x59B70), (0x6FAD0, 0x6FCDC),
                  (0x70998, 0x70A6C), (0x1B370, 0x1B37C))
        for begin, end in ranges:
            self.code.update({ins.address: (ins.mnemonic, ins.op_str)
                              for ins in decoder.disasm(self.read(begin, end - begin), begin)})
        self.constructors, self.generated, self.submitted = [], [], []
        self.nodes_seen = set()
        self.metric_cache = {}
        self.viewport_entries = native.get("backlog_view", {}).get("entries", {})
        self.viewport_glyphs = []
        if self.viewport_entries:
            # 64014 constructs mode1; 70C38..70D08 initialize this geometry.
            geometry = struct.unpack_from(">9f", source, 0x70AD0 - 0x10000)
            self.setfloat(self.CTX + 0x34, geometry[0])
            self.setfloat(self.CTX + 0x38, geometry[1])
            self.setfloat(self.CTX + 0x88, geometry[7])
            self.put(self.ENGINE + 0x2B4, self.CTX, 4)
        # Source70AF8 receives parent=normal and mode=1 for the real backlog.
        self.put(self.CTX + 0x1C, self.PARENT, 4)
        self.put(self.CTX + 0x28, 1, 1)
        self.put(self.CTX + 0x29, 1, 1)
        self.put(self.CTX + 0x26, 1, 1)
        self.put(self.CTX + 0x530, 0, 4)
        self.setfloat(self.CTX + 0x44, 984)
        self.setfloat(self.CTX + 0x48, 628)
        self.setfloat(self.CTX + 0x30, 1)
        for offset in (0x64, 0x74):
            for lane in range(4):
                self.setfloat(self.CTX + offset + lane * 4, 1)
        self.setfloat(self.FONTS + 0xBC, 1)
        self.setfloat(self.FONTS + 0xC4, 1)
        self.setfloat(self.FONTS + 0xC8, 1)
        self.put(self.FONTS + 0x5C, 0x80, 4)
        if parent_progress is not None:
            node = self.SPANS
            self.put(self.PARENT + 0x510, node, 4)
            self.put(self.PARENT + 0x514, node, 4)
            self.put(self.PARENT + 0x518, 1, 4)
            self.setfloat(node + 0x14B8, parent_progress)
            self.setfloat(node + 0x14BC, parent_progress)
        self.parent_snapshot = self.read(self.PARENT, 0x560), self.read(self.SPANS, 0x15E0)
        self.raw_checkpoint_snapshot = self.read(self.STATE + 0x20, 4)
        # Reuse the source-constructed shared font/range/texture fixture; glyph
        # lookups, cached records and per-character fixed-cell submission run.
        font = save_preview_smoke.PreviewCPU(source, image, native)
        for address, size in ((font.ALLOCATION, font.allocate_next - font.ALLOCATION),
                              (font.MANAGER, 0x100), (font.TEXTURE, 0x100),
                              (font.DESCRIPTOR, 0x100)):
            self.write(address, font.read(address, size))
        self.write(font.FONT, font.read(font.FONT, 0x100))
        self.put(font.FONT + 0x94, 2048, 4)
        for index in range(4):
            self.put(self.FONTS + index * 4, font.FONT, 4)
        self.put(0x257028, font.MANAGER, 4)
        self.put(0x657EA8, 1, 4)
        self.queue_font, self.queue_buffer = font.FONT, font.QUEUE
        for begin, end in save_preview_smoke.CPU_RANGES:
            self.code.update({ins.address: (ins.mnemonic, ins.op_str)
                              for ins in decoder.disasm(self.read(begin, end - begin), begin)})

    def step(self):
        mnemonic, operands = self.code[self.pc]
        if self.pc in (0x6EE78, 0x6EEC0) and self.r[3] and self.r[3] not in self.nodes_seen:
            node = self.r[3]
            self.nodes_seen.add(node)
            self.constructors.append({"node": node, "text": self.string(self.get(node + 0x30, 4)).hex(),
                                      "progress": self.scalar(node + 0x14B8),
                                      "total": self.scalar(node + 0x14BC)})
        if mnemonic in ("vmaddfp", "vnmsubfp"):
            arguments = [int(value.strip()[1:]) for value in operands.split(",")]
            destination, a, b, c = arguments
            triples = list(zip(self.vf(a), self.vf(b), self.vf(c)))
            if any(not math.isfinite(value) for triple in triples for value in triple):
                # Real unaligned loads also fetch adjacent integer alpha words.
                # IEEE propagation is required even for lanes discarded later.
                from native_scanner_model import fused
                values = [(fused(x, y, z) if mnemonic == "vmaddfp" else fused(-x, y, z))
                          if all(math.isfinite(v) for v in (x, y, z))
                          else ((x * y + z) if mnemonic == "vmaddfp" else (-x * y + z))
                          for x, y, z in triples]
                self.setv(destination, values, True)
                self.executed.add(self.pc)
                self.pc += 4
                self.steps += 1
                return
        if mnemonic in ("vctsxs", "vctuxs"):
            destination, value, scale = operands.split(", ")
            values = self.vf(int(value[1:]))
            if any(not math.isfinite(v) for v in values):
                require(math.isfinite(values[0]), "non-finite live glyph geometry")
                following = next(self.code[pc] for pc in range(self.pc + 4, self.pc + 68, 4)
                                 if pc in self.code and self.code[pc][0].startswith("v"))
                require(following == ("vspltw", f"{destination}, {destination}, 0"),
                        "non-finite vector lane is not immediately discarded")
                low, high = (0, 0xFFFFFFFF) if mnemonic == "vctuxs" else (-2**31, 2**31 - 1)
                result = [max(low, min(high, int(values[0] * 2**int(scale, 0)))) & 0xFFFFFFFF, 0, 0, 0]
                self.setv(int(destination[1:]), result)
                self.executed.add(self.pc)
                self.pc += 4
                self.steps += 1
                return
        if mnemonic == ".byte":
            word = self.get(self.pc, 4)
            if word >> 26 == 31 and (word >> 1) & 1023 == 551:
                destination, ra, rb = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
                address = ((self.r[ra] if ra else 0) + self.r[rb]) & MASK
                count = address & 15
                self.v[destination] = bytes(16 - count) + self.read(address - count, count)
                self.executed.add(self.pc)
                self.pc += 4
                self.steps += 1
                return
        if mnemonic == "rldicr":
            destination, value, shift, end = operands.split(", ")
            amount, last = int(shift, 0), int(end, 0)
            number = self.number(value) & MASK
            rotated = ((number << amount) | (number >> ((64 - amount) % 64))) & MASK
            self.r[int(destination[1:])] = rotated & ((MASK << (63 - last)) & MASK)
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        if mnemonic in ("vor", "vxor", "vmulouh", "vmsumshm", "vsraw"):
            args = [int(value.strip()[1:]) for value in operands.split(",")]
            dest, a, b = args[:3]
            if mnemonic == "vxor":
                self.setv(dest, [x ^ y for x, y in zip(self.vu(a), self.vu(b))])
            elif mnemonic == "vor":
                self.setv(dest, [x | y for x, y in zip(self.vu(a), self.vu(b))])
            elif mnemonic == "vsraw":
                self.setv(dest, [(signed(x, 32) >> (y & 31)) & 0xFFFFFFFF
                                 for x, y in zip(self.vu(a), self.vu(b))])
            else:
                left, right = struct.unpack(">8H", self.v[a]), struct.unpack(">8H", self.v[b])
                if mnemonic == "vmulouh":
                    values = [left[index] * right[index] for index in (1, 3, 5, 7)]
                else:
                    accumulator = self.vu(args[3])
                    values = [signed(left[index], 16) * signed(right[index], 16)
                              + signed(left[index + 1], 16) * signed(right[index + 1], 16)
                              + accumulator[index // 2] for index in (0, 2, 4, 6)]
                self.setv(dest, [value & 0xFFFFFFFF for value in values])
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        super().step()

    def call(self, target):
        if target == int(self.viewport_entries.get("draw_backlog_viewport", "0"), 0):
            self.submitted.append(self.r[29])
        if self.viewport_entries and target in (0x1BE28, 0x1B9D8):
            self.viewport_glyphs.append({"address": self.r[7] - 12,
                                         "text": self.read(self.r[7], 2).partition(b"\0")[0],
                                         "x": signed(self.r[4], 32), "y": signed(self.r[5], 32),
                                         "rgba": self.r[8] & 0xFFFFFFFF,
                                         "alpha": self.r[8] & 255})
        if target == 0x1D538:
            key = (self.r[3], self.read(self.r[4], 2))
            caller = self.pc
            if key not in self.metric_cache:
                self.pc, self.lr = target, caller + 4
                self.execute_until(caller + 4)
                self.metric_cache[key] = self.r[3]
                self.pc = caller
            else:
                self.r[3] = self.metric_cache[key]
            self.lr = caller + 4
            return caller + 4
        actual = (0x69B38, 0x6DAFC, 0x594E8, 0x59338, 0x6DF90, 0x6DE5C,
                  0x42F70, 0x43214, 0x455F8)
        if target in actual:
            if target == 0x594E8:
                self.generated.append(self.r[30])
            if target == 0x59338:
                self.submitted.append(self.r[4] - 0x94)
            return native_pagination_smoke.Replay.call(self, target)
        if target in (0xD54DC, 0xD0E18, 0xD83A4):
            return native_runtime_text_smoke.RuntimeCPU.call(self, target)
        if target in (0x59E98, 0x70850):
            self.lr = self.pc + 4
            return self.pc + 4
        return super().call(target)

    def settle(self, *, isolate_updates=False):
        nodes = self.queue()
        if isolate_updates:
            # An isolated per-span update avoids replaying already generated
            # prefix glyphs on every synthetic frame. It never changes reveal
            # progress/state. Restore the complete list before native drawing.
            head = self.get(self.CTX + 0x510, 4)
            for node in nodes:
                following = self.get(node + 0x14, 4)
                self.put(self.CTX + 0x510, node, 4)
                self.put(node + 0x14, 0, 4)
                for _ in range(3):
                    self.native_call(0x6FD48, self.CTX, 0, 0, 0)
                    if _ >= 1 and self.get(node + 0x18, 4) == 3:
                        break
                self.put(node + 0x14, following, 4)
            self.put(self.CTX + 0x510, head, 4)
        else:
            for _ in range(len(nodes) + 3):
                self.native_call(0x6FD48, self.CTX, 0, 0, 0)
                if all(self.get(node + 0x18, 4) == 3 for node in nodes):
                    # Completion is followed by a native opacity-fade update.
                    self.native_call(0x6FD48, self.CTX, 0, 0, 0)
                    break
        if self.viewport_entries:
            self.native_call(0x1B370, self.queue_font)
        self.native_call(0x70998, self.CTX)
        rows = []
        for node in self.queue():
            glyphs, visible, index = bytearray(), bytearray(), 0
            while self.get(node + 0x94 + index * 20 + 0xC, 1):
                require(index < 256, "cached glyphs exceed the native span capacity")
                record = self.read(node + 0x94 + index * 20, 20)
                if record[11] != 0 or record[12] == 0x20:
                    visible.extend(record[12:14].partition(b"\0")[0])
                glyphs.extend(record[12:14].partition(b"\0")[0])
                index += 1
            rows.append({"text": self.string(self.get(node + 0x30, 4)), "glyphs": bytes(glyphs),
                         "visible_glyphs": bytes(visible),
                         "state": self.get(node + 0x18, 4), "progress": self.scalar(node + 0x14B8),
                         "total": self.scalar(node + 0x14BC), "node": node})
        require(self.parent_snapshot == (self.read(self.PARENT, 0x560), self.read(self.SPANS, 0x15E0)),
                "backlog changed the parent gameplay queue/progress")
        require(self.raw_checkpoint_snapshot == self.read(self.STATE + 0x20, 4),
                "backlog changed gameplay raw checkpoint progress")
        self.assert_flags()
        return rows


def smoke(source, image, native, payload, paragraph):
    old_image = bytearray(image)
    old_image[0x5A284:0x5A288] = source[0x5A284:0x5A288]
    cases = []
    # Cover inheritance branches with the short fixture; repeat the expensive
    # whole-paragraph path only for the retired/partial-parent case.
    for name, text, parents in (
        ("greeting", b'[N01] "Oh, Taka-kun! You\'re here... aren\'t you?"', (None, 7, 32)),
        ("paragraph", paragraph, (32,)),
    ):
        for parent in parents:
            observations = []
            for corrected in (False, True):
                cpu = BacklogCPU(source, image if corrected else bytes(old_image), native, payload,
                                  text, parent_progress=parent)
                cpu.initialize()
                cpu.append(text)
                cpu.native_call(0x69FE8, cpu.CTX, 0)
                rows = cpu.settle(isolate_updates=name == "paragraph")
                view_proof = None
                if corrected and cpu.viewport_entries:
                    from native_backlog_view_smoke import reachable_views
                    view_proof = reachable_views(cpu)
                actual = b"".join(row["glyphs"] for row in rows if row["node"] in cpu.submitted)
                visible = b"".join(row["visible_glyphs"] for row in rows if row["node"] in cpu.submitted)
                if corrected:
                    if view_proof is not None:
                        require(view_proof["complete_text"] == text and view_proof["opaque_text"] == text
                                and view_proof["glyph_count"] == len(save_preview_smoke.units(text)),
                                "complete glyph text/opacity did not reach native viewport queues")
                    else:
                        require(cpu.get(cpu.queue_font + 0x14, 4) == len(save_preview_smoke.units(text)),
                                "complete glyph text did not reach the native backend queue")
                    require(actual == text and visible == text and all(row["state"] == 3 for row in rows),
                            "complete recorded backlog text did not reach native glyph submission")
                else:
                    require(actual != text and any(row["state"] != 3 for row in rows),
                            "old ordinal inheritance did not reproduce incomplete rendering")
                observations.append({"corrected": corrected, "submitted_bytes": len(actual),
                                     "nonzero_opacity_bytes": len(visible),
                                     "complete_states": sum(row["state"] == 3 for row in rows),
                                     "spans": len(rows), "constructor_progress": cpu.constructors,
                                     "viewport_offsets": view_proof["offsets"] if view_proof else None,
                                     "all_parent_state_unchanged": True})
            cases.append({"case": name, "parent_progress": parent, "observations": observations})
    return {"image_sha256": project.digest(image), "cases": cases, "runtime_accepted": False,
            "native_viewport_navigation": bool(native.get("backlog_view")),
            "scope": "Encoded scanner69FE8/6DF90, native6DAFC constructor,6FD48 updates,594E8 cached glyphs,70998/59338 traversal and1BE28 queue submission.",
            "limitations": ["Finite shared-font/resource and allocator/libc fixtures; not native FP/GPU/full VM.",
                            "At least two updates retain native first-frame opacity fade-in; nonzero cached alpha is checked, not final opacity or GPU pixels.",
                            "Parent-window decoration and controller polling are explicit boundaries.",
                            "With backlog_view enabled, complete-text/opacity coverage accumulates actual native glyph submissions across source-control viewport offsets, not one offscreen frame; source geometry includes1.3 vertical placement scale.",
                            "Long-paragraph updates isolate each span temporarily; the complete list is restored for native draw traversal. Short cases run the full frame loop.",
                            "Font lookup ABI results are memoized after actual native execution; unused non-finite VMX lanes are discarded only at a verified finite-lane-0 splat. No FPSCR/VSCR proof.",
                            "Latest recorded entry is fully revealed in backlog, not ordinally synchronized with partial gameplay typewriter progress."]}
