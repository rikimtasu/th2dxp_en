"""Execute relocated UI constants and original-font draw paths; never GPU/RPCS3.

Only the existing bounded font allocator and original synthetic CPU objects are
modeled. Literal loads, pointer selection, copied-label bypasses, font dispatch
and every glyph queue record execute their actual encoded instructions.
"""
from __future__ import annotations

import struct

import capstone
import native_layout_patch
from native_scanner_model import signed
import native_ui_patch
import project
import save_preview_smoke
from native_typography_smoke import GlyphCPU


def require(condition, message):
    if not condition:
        raise ValueError("Native UI replay: " + message)


def decode_site(cpu, image, pc):
    decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    decoded = list(decoder.disasm(image[pc - 0x10000:pc - 0x10000 + 4], pc))
    require(len(decoded) == 1 and decoded[0].size == 4, "incomplete native site decode")
    cpu.code[pc] = decoded[0].mnemonic, decoded[0].op_str


def seed(cpu, iteration):
    cpu.r = [0x12340000 + register * 0x100 + iteration for register in range(32)]
    cpu.r[1] = cpu.STACK
    cpu.f = [float(register) / 8 for register in range(32)]
    cpu.v = [bytes([register]) * 16 for register in range(32)]
    cpu.cr = [bool((bit + iteration) % 2) for bit in range(32)]
    cpu.lr, cpu.xer_ca, cpu.fpscr = 0xDEAD00, bool(iteration % 2), 0x1234
    cpu.steps, cpu.calls = 0, 0


def non_gpr_state(cpu):
    return cpu.f[:], cpu.v[:], cpu.cr[:], cpu.lr, cpu.xer_ca, cpu.fpscr


def draw(cpu, image, native, text, *, site=0x8E80C, scale=0.5, proportional=True, x=20, y=10):
    """Replay a raw option-value call, never the positioned dialogue consumer."""
    word = struct.unpack_from(">I", cpu.source, 0x11804 - 0x10000)[0]
    require(word >> 26 == 14 and (word >> 21) & 31 == 6 and not (word >> 16) & 31,
            "source main-font queue capacity instruction changed")
    capacity = signed(word, 16)
    require(capacity == 2048, "unexpected source main-font queue capacity")
    cpu.put(cpu.FONT + 0x94, capacity, 4)
    cpu.put(cpu.FONT + 0x7C, 0x257038 if proportional else 0, 4)
    cpu.write(cpu.TEXT, text + b"\0")
    cpu.put(cpu.FONT + 0x14, 0, 4)
    cpu.r[1] = cpu.STACK
    cpu.put(cpu.STACK + 0x70, 0, 8)
    cpu.r[3:9] = [cpu.FONT, x, y, 0, cpu.TEXT, 0xFFFFFFFF]
    cpu.f[1:4] = [1.0, scale, scale]
    cpu.steps, cpu.calls = 0, 0
    decode_site(cpu, image, site)
    cpu.invoke(site, stop=site + 4)
    count = cpu.get(cpu.FONT + 0x14, 4)
    require(count < capacity, "UI fixture exhausts the source main-font glyph queue")
    expected, at = 0, 0
    while at < len(text):
        byte = text[at]
        at += 2 if 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC else 1
        expected += byte != 10
    require(count == expected, "native draw lost a complete UI character")
    return [struct.unpack(">10HIf", cpu.read(cpu.QUEUE + index * 28, 28)) for index in range(count)]

class DialogueCPU(GlyphCPU):
    """Execute source producer's per-character body with explicit live inputs."""

    def __init__(self, source, image, native):
        super().__init__(source, image, native)
        decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        decoder.skipdata = True
        for begin, end in ((0x59338, 0x594C4), (0x598DC, 0x59AD4)):
            self.code.update({ins.address: (ins.mnemonic, ins.op_str)
                              for ins in decoder.disasm(self.read(begin, end - begin), begin)})

    def step(self):
        mnemonic, operands = self.code[self.pc]
        if mnemonic in ("vsrw", "vcfux"):
            args = operands.split(", ")
            dest, a = [int(value[1:]) for value in args[:2]]
            if mnemonic == "vsrw":
                b = int(args[2][1:])
                self.setv(dest, [x >> (y & 31) for x, y in zip(self.vu(a), self.vu(b))])
            else:
                self.setv(dest, [x / 2 ** int(args[2], 0) for x in self.vu(a)], True)
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        super().step()

    def dialogue(self, text, scale):
        units = save_preview_smoke.units(text)
        self.write(self.TEXT, text + b"\0")
        self.put(self.CTX, self.FONT, 4)
        self.put(self.CTX + 0x138, self.TEXT, 4)
        for off, value in ((0x58, 1.0), (0xC4, scale), (0xC8, scale), (0xBC, 1.0)):
            self.setfloat(self.CTX + off, value)
        for off in (0xFA, 0xFC):
            self.put(self.CTX + off, 48, 2)
        pen, offset = 100.0, 0
        for index, unit in enumerate(units):
            self.r[1] = self.STACK
            self.r[3], self.r[4] = self.TEXT, 0
            self.r[18], self.r[20], self.r[21] = 1, 0, 0
            self.r[22], self.r[23], self.r[24] = self.CTX, 0, 100
            self.r[25:32] = [len(unit), self.SPANS + index * 20, 0xFFFFFFFF, offset, 100, 0, self.CTX]
            self.setv(2, [10.0] * 4, True)
            self.setv(3, [0.0] * 4, True)
            self.setv(9, [struct.unpack_from(">f", self.source, 0x594D8 - 0x10000)[0]] * 4, True)
            self.setv(26, [0xFFFFFFF0] * 4)
            self.setv(27, [(10 << 16) | 10] * 4)
            self.setv(30, [pen] * 4, True)
            self.setv(31, [0xFFFFFFFF] * 4)
            self.pc = 0x598DC
            if len(unit) == 2:
                self.r[3], self.pc = 0, 0x598F0
            self.execute_until(0x59AD0)
            pen = self.vf(31)[0]
            offset += len(unit)
        self.put(self.SPANS + len(units) * 20 + 12, 0, 1)
        self.put(self.FONT + 0x14, 0, 4)
        self.put(self.FONT + 0x94, 2048, 4)
        self.r[1] = self.STACK
        self.r[3:5] = [self.CTX, self.SPANS]
        self.invoke(0x59338)
        count = self.get(self.FONT + 0x14, 4)
        require(count == len(units), "composed dialogue lost a producer record")
        records = [struct.unpack(">10HIf", self.read(self.QUEUE + index * 28, 28)) for index in range(count)]
        self.r[3], self.r[30], self.r[5], self.r[6] = self.VERTICES, self.FONT, count, self.QUEUE
        self.pc = 0x1B47C
        self.execute_until(0x1B69C)
        vertices = [[struct.unpack(">hhIHH", self.read(self.VERTICES + index * 48 + corner * 12, 12))
                     for corner in range(4)] for index in range(count)]
        return units, records, vertices


def centered_help(cpu, text, scale=None, *, center=640, y=180, bounds=(0, 1280), bottom=720,
                  color=0xFFFFFFFF):
    """Execute 1C8B8's centered line body after its native tokenization boundary."""
    decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    cpu.code.update({ins.address: (ins.mnemonic, ins.op_str)
                     for ins in decoder.disasm(cpu.read(0x1C9F0, 0x48), 0x1C9F0)})
    cpu.put(cpu.FONT + 0x14, 0, 4)
    cpu.put(cpu.FONT + 0x94, 2048, 4)
    if scale is None:
        scale = struct.unpack_from(">f", cpu.source, 0x87FB4 - 0x10000)[0]
    line_pitch = int(save_preview_smoke.f32(cpu.get(cpu.FONT + 0x90, 4) * scale))
    lines = [line for line in text.split(b"\n") if line]
    widths = []
    for index, line in enumerate(lines):
        cpu.write(cpu.TEXT, line + b"\0")
        cpu.r[1], cpu.r[31] = cpu.STACK, cpu.STACK
        cpu.r[23:26] = [center, y + index * line_pitch, 0]
        cpu.r[27:31] = [cpu.TEXT, cpu.FONT, 0, color]
        cpu.f[27:32] = [float(center), 0.5, 1.0, scale, scale]
        cpu.pc = 0x1C9F0
        cpu.execute_until(0x1CA00)
        widths.append(cpu.f[1])
        cpu.execute_until(0x1CA38)
    count = cpu.get(cpu.FONT + 0x14, 4)
    require(count == sum(len(save_preview_smoke.units(line)) for line in lines),
            "native centered help lost a complete printable character")
    records = [struct.unpack(">10HIf", cpu.read(cpu.QUEUE + index * 28, 28)) for index in range(count)]
    require(all(bounds[0] <= signed(record[2], 16) < signed(record[4], 16) + 1 <= bounds[1]
                and signed(record[5], 16) + 1 <= bottom for record in records),
            "native centered help extends outside its actual native panel")
    return records, widths


def dialogue_smoke(source, image, native):
    require(image[0x49488:0x4948C] == source[0x49488:0x4948C],
            "positioned dialogue consumer is still retargeted")
    broken = bytearray(image)
    caption = next(int(block["va"], 0) for block in native["injected_blocks"]
                   if block["name"] == "caption_fixed_renderer_with_latin_metrics")
    broken[0x49488:0x4948C] = bytes(native_layout_patch._assembler().asm(
        f"bl {caption:#x}", addr=0x59488)[0])
    cases = []
    metrics = save_preview_smoke.SourceMetrics(image)
    for text in (b"ic ro fo", b"I stick my hand out from the futon and switch off the alarm clock.",
                 "ic日本語 ro gjpqy".encode("cp932")):
        for scale in (1.0, 0.625, 1.5):
            units, records, vertices = DialogueCPU(source, image, native).dialogue(text, scale)
            _, old_records, _ = DialogueCPU(source, bytes(broken), native).dialogue(text, scale)
            ink = []
            for unit, record, old_record, quad in zip(units, records, old_records, vertices):
                if len(unit) == 1:
                    bearing, width = metrics.main_pair(unit[0])
                    ink.append({"text_hex": unit.hex(), "correct_left": signed(record[2], 16) + bearing * scale,
                                "old_left": signed(old_record[2], 16) + bearing * scale, "ink_width": width * scale})
                require(max(vertex[0] for vertex in quad) == record[4] + 1
                        and max(vertex[1] for vertex in quad) == record[5] + 1
                        and max(vertex[4] for vertex in quad) == record[9] + 1,
                        "composed dialogue lost endpoint/descender coverage")
            if text == b"ic ro fo" and scale == 1.0:
                gap = ink[1]["correct_left"] - ink[0]["correct_left"] - ink[0]["ink_width"]
                old_gap = ink[1]["old_left"] - ink[0]["old_left"] - ink[0]["ink_width"]
                expected_gap = metrics.width(units[0]) - metrics.main_pair(units[0][0])[1]
                require(gap == expected_gap, "positioned dialogue applies its bearing more than once")
                require(old_gap != gap, "double-bearing negative control no longer distinguishes the regression")
            cases.append({"text_hex": text.hex(), "scale": scale, "glyphs": len(records),
                          "final_ink": ink, "descender_endpoints_complete": True})
    return {"cases": cases, "producer_slice": ["0x598dc", "0x59ad0"],
            "consumer": "0x59338", "queue": "0x1bcb8", "vertices": ["0x1b47c", "0x1b69c"],
            "limitations": ["Producer prologue live inputs and line-tokenization boundary are synthetic.",
                            "Control parsing and word wrapping remain in native_typography_smoke."]}

class SpriteCPU(save_preview_smoke.PreviewCPU):
    """Bound only GUI-context/atlas handles and the existing 78-byte memcpy."""
    RENDERER, VTABLE, OPD = 0xE30000, 0xE30100, 0xE30200
    MODEL, ATLAS, RECORD = 0xE31000, 0xE32000, 0xE33000

    def __init__(self, source, image, native):
        super().__init__(source, image, native)
        decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        for begin, end in ((0x7BA68, 0x7BAD0), (0x9BCFC, 0x9BD08), (0x9BFD0, 0x9C26C)):
            self.code.update({ins.address: (ins.mnemonic, ins.op_str)
                              for ins in decoder.disasm(self.read(begin, end - begin), begin)})
        for at, value in ((self.RENDERER, self.VTABLE), (self.VTABLE + 16, self.OPD),
                          (self.OPD, 0xDEAD80), (self.OPD + 4, 0),
                          (self.MODEL + 4, self.ATLAS)):
            self.put(at, value, 4)
        self.boundaries = []

    def call(self, target):
        if target not in (0x380F8, 0x288A8, 0xD0E18):
            return super().call(target)
        self.calls += 1
        self.lr = self.pc + 4
        if target == 0x380F8:
            self.r[3] = self.RENDERER
        elif target == 0x288A8:
            require(self.r[3:5] == [self.ATLAS, 0], "sprite lookup leaves the source-bound Extra record0")
            self.r[3] = self.RECORD
        else:
            dest, source, size = self.r[3:6]
            require(source == 0x65112E and size == 78, "footer memcpy leaves the exact native 13-cell table")
            self.write(dest, self.read(source, size))
        self.boundaries.append({"pc": hex(self.pc), "target": hex(target)})
        return self.lr

    def step(self):
        if self.code[self.pc][0] == "mtctr":
            self.ctr = self.number(self.code[self.pc][1])
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        super().step()


class SelectorCPU(SpriteCPU):
    """Execute 8F730's live selector body; bound only GUI and line tokenization."""

    def __init__(self, source, image, native):
        super().__init__(source, image, native)
        decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        self.code.update({ins.address: (ins.mnemonic, ins.op_str)
                          for ins in decoder.disasm(self.read(0x8F79C, 0x624), 0x8F79C)})
        self.put(self.VTABLE + 24, self.OPD, 4)
        self.drawer = save_preview_smoke.PreviewCPU(source, image, native)
        self.metrics = save_preview_smoke.SourceMetrics(image)
        self.text_calls, self.sprite_calls = [], []

    def call(self, target):
        if target == 0x78820:
            require(self.r[3] == 43, "selector requested an unexpected atlas")
            self.r[3], self.lr = self.ATLAS, self.pc + 4
            return self.lr
        if target != 0x1C8B8:
            return super().call(target)
        require(self.r[3] == self.FONT and self.f[1] == 1.0 and self.f[2] == self.f[3],
                "selector changed its original font, opacity or glyph proportions")
        text, scale = self.string(self.r[7]), self.f[2]
        require(b"\n" not in text and all(32 <= byte <= 126 for byte in text),
                "two-state fixture leaves its reviewed single-line printable values")
        records, widths = centered_help(
            self.drawer, text, scale, center=signed(self.r[4], 16),
            y=signed(self.r[5], 16), color=self.r[8] & 0xFFFFFFFF)
        require(all(record[10] == self.r[8] & 0xFFFFFFFF for record in records),
                "encoded centered renderer lost its selection/highlight color")
        # A queued 48px cell includes transparent bearing/tail pixels. Compare
        # actual metric ink, not those empty cells, against text and arrow quads.
        ink = []
        for byte, record in zip(text, records):
            a, b = self.metrics.main_pair(byte)
            left = signed(record[2], 16) + int(save_preview_smoke.fused(a, scale, 0.5))
            right = signed(record[2], 16) + int(save_preview_smoke.fused(a + b, scale, 0.5))
            if byte != 32 and b:
                ink.append((left, right))
        require(ink and len(widths) == 1, "selector lost its complete measured value")
        self.text_calls.append({
            "site": hex(self.pc), "text_hex": text.hex(),
            "center": signed(self.r[4], 16), "y": signed(self.r[5], 16),
            "scale": scale, "color": self.r[8] & 0xFFFFFFFF,
            "measured_width": widths[0], "ink": [min(a for a, _ in ink), max(b for _, b in ink)],
            "glyphs": len(records),
        })
        self.lr = self.pc + 4
        return self.lr

    def step(self):
        if self.code[self.pc][0] == "bdnzctrl":
            require(self.ctr == 0xDEAD80, "selector leaves its synthetic renderer boundary")
            if self.pc == 0x8F8FC:
                quad = [signed(self.r[reg], 16) for reg in (4, 5, 6, 7)]
            else:
                x, y, width, height = [signed(self.r[reg], 16) for reg in (4, 5, 6, 7)]
                # Native vtable109B70+18 -> OPD1208A8 -> 26818 converts
                # sprite center/size to corners (26834..268B4).
                quad = [x - width // 2, y - height // 2,
                        x + width - width // 2, y + height - height // 2]
            self.sprite_calls.append({
                "site": hex(self.pc), "quad": quad,
                "color": self.get(self.r[1] + 0x78, 8),
                "mode": self.get(self.r[1] + 0x90, 8),
            })
            self.executed.add(self.pc)
            self.lr = self.pc + 4
            self.pc += 4
            self.steps += 1
            return
        super().step()


def option_selector_smoke(source, image, native):
    """Actual two-state callers, all table instances/states and arrow pulse phases."""
    layout = native_ui_patch.OPTION_SELECTOR_GEOMETRY
    cpu = SelectorCPU(source, image, native)
    cases = []
    # Table kind1 is the real two-state widget; use relocated pointer fields,
    # including preserved OFF/ON, rather than injecting English stand-in values.
    for table, count in ((0x652640, 10), (0x652780, 8)):
        for index in range(count):
            row = table + index * 32
            if cpu.get(row, 4) != 1:
                continue
            require(cpu.get(row + 20, 4) == 2, "selector table is no longer two-state")
            values = [cpu.get(row + off, 4) for off in (24, 28)]
            texts = [cpu.string(pointer) for pointer in values]
            for selected in (0, 1):
                for active, timer in ((False, 0), (True, 0), (True, 31), (True, 32)):
                    seed(cpu, selected)
                    cpu.text_calls, cpu.sprite_calls = [], []
                    x = layout["row_origin_x"]
                    y = layout["first_row_y"] + index * layout["row_pitch"]
                    cpu.r[27], cpu.r[29], cpu.r[31] = x, y, cpu.MODEL
                    for offset, value, size in ((0x14, int(active), 1), (0x18, selected, 4),
                                                (0x20, timer, 4), (0x24, values[0], 4),
                                                (0x28, values[1], 4)):
                        cpu.put(cpu.MODEL + offset, value, size)
                    cpu.pc = 0x8F79C
                    cpu.execute_until(0x8FDC0)
                    calls = cpu.text_calls
                    require(len(calls) == (6 if active else 2),
                            "selector did not draw both complete value/shadow pairs")
                    require(all(call["text_hex"] == texts[selected].hex() for call in calls[:2])
                            and [call["center"] for call in calls[:2]] ==
                            [x + layout["collapsed_center"], x + layout["collapsed_center"] + 1]
                            and all(call["scale"] == 0.5 for call in calls[:2])
                            and all(call["color"] == (0x742244FF if active else 0x808080FF)
                                    for call in calls[:2]),
                            "collapsed selector changed its value, scale, highlight or fitted center")
                    collapsed = [min(call["ink"][0] for call in calls[:2]),
                                 max(call["ink"][1] for call in calls[:2])]
                    require(x + 316 <= collapsed[0] < collapsed[1] <= x + 463,
                            "collapsed full value leaves its actual row value cell")
                    label = cpu.string(cpu.get(row + 12, 4))
                    label_records = draw(cpu.drawer, image, native, label, x=x + 66, y=y + 5)
                    label_right = max(signed(record[4], 16) + 2 for record in label_records)
                    require(label_right + 8 <= collapsed[0],
                            "complete option label overlaps its selected full-word value")
                    arrows = []
                    if active:
                        panel = [x + 475, y - 15, x + 1099, y + 49]
                        require(cpu.sprite_calls[0]["quad"] == panel,
                                "expanded selector panel does not use its encoded bounds")
                        envelopes = []
                        for option in (0, 1):
                            pair = calls[2 + option * 2:4 + option * 2]
                            require(all(call["text_hex"] == texts[option].hex() for call in pair)
                                    and [call["center"] for call in pair] ==
                                    [x + layout["centers"][option], x + layout["centers"][option] + 1]
                                    and all(call["scale"] == struct.unpack_from(">f", source, 0x7F728)[0]
                                            for call in pair),
                                    "expanded selector changed full words, original scale or shadow offset")
                            color = 0x808080FF if option == selected else 0x303030FF
                            require(all(call["color"] == color for call in pair),
                                    "expanded selector lost its selection-dependent highlight")
                            envelopes.append([min(call["ink"][0] for call in pair),
                                              max(call["ink"][1] for call in pair)])
                        gap = layout["minimum_clearance"]
                        require(envelopes[0][1] + gap <= envelopes[1][0],
                                "complete dynamic option words overlap")
                        arrows = [sprite for sprite in cpu.sprite_calls if sprite["site"] in
                                  ("0x8fc64", "0x8fcc4", "0x8fd54", "0x8fdac")]
                        require(len(arrows) == (4 if timer < 32 else 2),
                                "selector changed its native arrow/pulse phase predicate")
                        center = x + layout["centers"][selected]
                        half = int(save_preview_smoke.f32(calls[2 + selected * 2]["measured_width"] * 0.5))
                        for arrow in arrows:
                            left, top, right, bottom = arrow["quad"]
                            is_left = arrow["site"] in ("0x8fc64", "0x8fd54")
                            margin = layout["arrow_center_margin"]
                            expected_center = center - half - margin if is_left else center + half + margin
                            width = 48 if arrow["site"] in ("0x8fd54", "0x8fdac") else 32
                            pulse = width == 48
                            shade = 128 - timer * 4 if pulse else 128
                            require(arrow["color"] == (shade << 24 | shade << 16 | shade << 8 | 255)
                                    and arrow["mode"] == (2 if pulse else 0),
                                    "selector changed its source arrow/pulse color or blending mode")
                            require(left == expected_center - width // 2 and right - left == width,
                                    "selector arrows no longer follow the selected native measurement")
                            require(panel[0] <= left < right <= panel[2]
                                    and panel[1] <= top < bottom <= panel[3],
                                    "selector arrow or pulse leaves its actual panel")
                            require(all(right + gap <= a or b + gap <= left for a, b in envelopes),
                                    "selector arrow/pulse overlaps a complete option word")
                        require(all(panel[0] <= a < b <= panel[2] for a, b in envelopes)
                                and 0 <= panel[0] < panel[2] <= 1280
                                and 0 <= panel[1] < panel[3] <= 720,
                                "selector text/panel leaves its native bounds")
                    else:
                        require(not cpu.sprite_calls and cpu.get(cpu.MODEL + 0x20, 4) == 0,
                                "inactive selector draws arrows or changes its native timer reset")
                        envelopes = []
                    require(cpu.get(cpu.MODEL + 0x18, 4) == selected
                            and [cpu.get(cpu.MODEL + off, 4) for off in (0x24, 0x28)] == values,
                            "geometry correction changes option state or writable value pointers")
                    cases.append({"table": hex(table), "index": index, "selected": selected,
                                  "active": active, "timer": timer, "collapsed_ink": collapsed,
                                  "expanded_ink": envelopes, "text_calls": calls, "arrows": arrows})
    require(len(cases) == 32, "actual two-state selector table/state coverage is incomplete")
    return {"cases": cases, "caller_slice": ["0x8f79c", "0x8fdc0"],
            "native_measurement": "0x1c5b8", "native_centered_line": ["0x1c9f0", "0x1ca38"],
            "sprite_corner_conversion": ["0x26818", "0x268b8"],
            "candidate_metric_pointer": "0x257038", "runtime_accepted": False,
            "limitations": ["GUI/atlas handles and renderer submission are synthetic boundaries.",
                            "Single-line tokenization is bounded; centered measurement/draw and caller branches execute encoded code.",
                            "Arrow bounds conservatively include the full transparent sprite and pulse rectangles."]}


def geometry_smoke(source, image, native):
    cpu = SpriteCPU(source, image, native)
    seed(cpu, 0)
    cpu.r[4], cpu.f[1] = cpu.MODEL, 1.0
    cpu.invoke(0x7BA68, stop=0x7BAD0)
    copied = cpu.read(cpu.r[1] + 0xD8, 78)
    captions = []
    for index, entry in enumerate(native["ui_graphic_layout"]["legend_entries"]):
        x, y, width = struct.unpack_from(">3H", copied, index * 6)
        require([x, y, x + width, y + 20] == entry["staged_source_crop"],
                "actual native footer copy does not select its complete readable caption")
        captions.append({"id": entry["id"], "source_rect": [x, y, x + width, y + 20]})
    seed(cpu, 0)
    cpu.r[23] = 0x9BA70
    cpu.pc = 0x9BCFC
    cpu.execute_until(0x9BD08)
    name_scale = cpu.f[26]
    require(name_scale == struct.unpack_from(">f", source, 0x9BA88 - 0x10000)[0],
            "music names do not reuse the original readable character-caption preset")
    rectangles = []
    for index, (begin, stop) in enumerate(((0x9BFD0, 0x9C064), (0x9C130, 0x9C1A0))):
        seed(cpu, index)
        cpu.r[17], cpu.r[19], cpu.r[24], cpu.r[25] = 0x656A30, 0, 205, 227
        cpu.r[26], cpu.r[27], cpu.r[28], cpu.r[31] = 249, 0xFFFFFFFF, 200, cpu.MODEL
        cpu.f[28] = 1.0
        cpu.pc = begin
        cpu.execute_until(stop)
        destination = [signed(cpu.r[reg], 16) for reg in (4, 5, 6, 7)]
        source_rect = [signed(cpu.r[reg], 16) for reg in (8, 9, 10)] + [cpu.get(cpu.r[1] + 0x70, 8)]
        group = native["ui_graphic_layout"]["credit_groups"][index]
        require(source_rect == group["staged_source_crop"]
                and destination == [group["destination_x"][0], 205, group["destination_x"][1], 249],
                "encoded music role quad differs from its paired readable atlas bank")
        require(destination[2] - destination[0] == source_rect[2] - source_rect[0]
                and destination[3] - destination[1] == source_rect[3] - source_rect[1],
                "native sprite geometry condenses the readable credit headings")
        rectangles.append({"source": source_rect, "destination": destination, "native_stop": hex(stop)})
    music_rows = project.load(project.ROOT / "work/ui/music-credit-reference.json")["native_rows"]
    music_geometry = []
    drawer = save_preview_smoke.PreviewCPU(source, image, native)
    for row in music_rows:
        table = row["source_file_offset"] + 0x10000
        title = drawer.string(drawer.get(table + 20, 4))
        title_records = draw(drawer, image, native, title, site=0x9BF0C, x=343, y=210)
        title_right = max(signed(record[4], 16) + 1 for record in title_records)
        limit = native["ui_graphic_layout"]["credit_groups"][0 if row["vocal"] else 1]["destination_x"][0]
        require(title_right + 8 <= limit, "complete full-size music title overlaps a readable credit column")
        names = []
        for group_index, fields in ((0, (32, 36)), (1, (24, 28))):
            group = native["ui_graphic_layout"]["credit_groups"][group_index]
            if group_index == 0 and not row["vocal"]:
                continue
            for field in fields:
                text = drawer.string(drawer.get(table + field, 4))
                records = draw(drawer, image, native, text, site=0x9C098 if group_index == 0 else 0x9C1D4,
                               scale=name_scale, x=group["artist_x"] + 1, y=205)
                right = max(signed(record[4], 16) + 1 for record in records)
                next_column = native["ui_graphic_layout"]["credit_groups"][1]["destination_x"][0] if group_index == 0 else 1280
                require(right + 8 <= next_column, "complete credited name overlaps another column or viewport edge")
                names.append({"field": field, "text_hex": text.hex(), "right_edge": right,
                              "next_column": next_column, "font_scale": name_scale})
        music_geometry.append({"native_index": row["index"], "title_right": title_right,
                               "credit_column_left": limit, "title_font_pixels": 24, "names": names})
    return {"native_caption_cells": captions, "native_music_role_quads": rectangles,
            "native_music_rows": music_geometry, "artist_font_scale": name_scale,
            "synthetic_boundaries": cpu.boundaries, "runtime_accepted": False}


def smoke(source, image, native):
    require(native_layout_patch.native_code_matches(image, image, native), "incomplete native UI correction")
    document = project.load(native_ui_patch.TRANSLATIONS)
    translated = {row["offset"]: row for row in document["records"] if row["status"] == "translated"}
    targets = {row["source_file_offset"]: row for row in native["ui_strings"]["records"]}
    old = save_preview_smoke.PreviewCPU(source, source)
    new = save_preview_smoke.PreviewCPU(source, image, native)
    literal_cases = []
    for offset, row in targets.items():
        require(new.string(row["virtual_address"]) == translated[offset]["translated"].encode(row["encoding"]),
                "mapped native UI string differs from reviewed complete translation")
        for reference in row["code_references"]:
            pc, register = reference["site"], reference["register"]
            word = struct.unpack_from(">I", source, pc - 0x10000)[0]
            decode_site(old, source, pc)
            decode_site(new, image, pc)
            for initial_carry in (0, 1):
                for cpu in (old, new):
                    seed(cpu, initial_carry)
                    if word >> 26 == 12:
                        cpu.r[(word >> 16) & 31] = offset + 0x10000 - signed(word, 16)
                    elif word >> 26 == 24:
                        require(not word & 0xFFFF, "unexpected non-copy ori literal reference")
                        cpu.r[(word >> 21) & 31] = offset + 0x10000
                    else:
                        raise ValueError("Native UI replay: unexpected literal opcode")
                    cpu.pc = pc
                    cpu.execute_until(pc + 4)
                require(old.r[register] == offset + 0x10000, "source literal reference is not its inventoried constant")
                expected = old.r[:]
                expected[register] = row["virtual_address"]
                require(new.r == expected and non_gpr_state(new) == non_gpr_state(old),
                        "UI literal relocation clobbered non-destination state")
            literal_cases.append({"site": hex(pc), "target": hex(row["virtual_address"]),
                                  "source_text": hex(offset), "both_initial_carries": True})
        for field in row["data_references"]:
            at = int(field, 0)
            require(struct.unpack_from(">I", image, at)[0] == row["virtual_address"],
                    "initialized native UI table retains an old or incorrect pointer")
    copy_cases = []
    for case in native["ui_consumers"]["fixed_copy_bypasses"]:
        pc = int(case["site"], 0)
        decode_site(new, image, pc)
        if "source_text" in case:
            seed(new, 0)
            stack = new.STACK + 0x80
            before = b"\xA5" * 0x240
            new.write(stack, before)
            new.r[case["register"]] = stack
            new.r[3:6] = [stack, targets[int(case["source_text"], 0)]["virtual_address"], 39]
            new.pc = pc
            new.execute_until(pc + 4)
            pointer = new.r[case["register"]]
            require(pointer == targets[int(case["source_text"], 0)]["virtual_address"]
                    and new.read(stack, len(before)) == before and new.lr == pc + 4,
                    "name-label fixed-copy bypass lost text, wrote a stack array, or broke BL return")
            copy_cases.append(dict(case, complete_bytes=len(new.string(pointer))))
        else:
            decode_site(old, source, pc)
            for mode in (0, 1):
                for cpu in (old, new):
                    seed(cpu, mode)
                    cpu.cr[2] = mode == 0
                    cpu.r[3] = 0x91
                    cpu.pc = pc
                    cpu.execute_until(pc + 4)
                expected = old.r[:]
                offset = 0xF75B4 if mode == 0 else 0xF76A4
                expected[31] = targets[offset]["virtual_address"]
                require(new.r == expected and non_gpr_state(new) == non_gpr_state(old),
                        "name-help mode/pulse selection or unrelated caller state changed")
                copy_cases.append(dict(case, mode=mode, complete_bytes=len(new.string(new.r[31]))))
    drawer = save_preview_smoke.PreviewCPU(source, image, native)
    glyph_cases = []
    # These are raw UI strings: do not submit them to dialogue's single-record
    # 59488 call. Name help uses its actual centered measurement/drawing pair.
    for offset, row in translated.items():
        text = row["translated"].encode(row["encoding"])
        if offset in (0xF75B4, 0xF76A4):
            records, measured = centered_help(drawer, text)
        elif offset in {0xF7978, 0xF79A0, 0xF79E0, 0xF7A18, 0xF7A58, 0xF7AE8,
                        0xF7B18, 0xF7B48, 0xF7B80, 0xF7C10, 0xF7C80}:
            scale = struct.unpack_from(">f", source, 0x907F4 - 0x10000)[0]
            records, measured = centered_help(drawer, text, scale, center=393, y=534,
                                              bounds=(160, 624), bottom=620)
        else:
            records, measured = draw(drawer, image, native, text), None
        glyph_cases.append({"source_text": hex(offset), "glyphs": len(records),
                            "rows": len({record[3] for record in records}),
                            "queue_sha256": project.digest(b"".join(struct.pack(">10HIf", *record) for record in records)),
                            "complete_text_bytes": len(text), "centered_line_widths": measured})
    controls = []
    for label, text, metric in (("japanese_unchanged", "日本語".encode("cp932"), True),
                                ("other_font_unchanged", b"Wi 123", False)):
        before = draw(old, source, {}, text, proportional=metric)
        after = draw(drawer, image, native, text, proportional=metric)
        require(before == after, label + ": option dispatch changed retained geometry")
        controls.append({"case": label, "queue_records_identical": True})
    for pc in (0x8E80C, 0x8E840):
        require(draw(drawer, image, native, b"Whole Page", site=pc) ==
                draw(drawer, image, native, b"Whole Page"),
                "raw option values disagree")
    option_panels = []
    for table, count in ((0x652640, 10), (0x652780, 8)):
        for index in range(count):
            pointer = drawer.get(table + index * 32 + 12, 4)
            label = drawer.string(pointer)
            records = draw(drawer, image, native, label, scale=0.5, x=66, y=5)
            right = max(record[4] + 1 for record in records)
            require(right + 8 <= 382, "complete option label overlaps its slider/value")
            option_panels.append({"table": hex(table), "index": index, "right": right,
                                  "slider_origin": 382, "clearance": 382 - right})
    dialogue = dialogue_smoke(source, image, native)
    geometry = geometry_smoke(source, image, native)
    selectors = option_selector_smoke(source, image, native)
    return {"image_sha256": project.digest(image), "native_literal_loads": literal_cases,
            "verified_table_pointer_fields": sum(len(row["data_references"]) for row in targets.values()),
            "verified_geometry_words": sum(row["purpose"] == "ui_legend_caption_geometry" for row in native["data_patches"]),
            "native_widget_geometry": geometry,
            "name_label_help_consumers": copy_cases, "original_font_ui_draws": glyph_cases,
            "composed_dialogue_glyphs": dialogue, "native_option_panels": option_panels,
            "native_option_selectors": selectors,
            "retained_geometry": controls, "source_main_font_queue_capacity": 2048,
            "raw_option_proportional_verified": True, "runtime_accepted": False,
            "limitations": ["Bounded encoded CPU execution, not GPU text rendering or a game run.",
                            "Desktop previews do not establish in-game sprite scaling, OS-dialog layout or loader acceptance.",
                            "No installed files, personal saves or original font assets are modified."]}
