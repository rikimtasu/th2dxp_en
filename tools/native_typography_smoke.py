"""Execute native word wrapping and glyph vertex endpoints; never GPU/RPCS3.

The font constructor, glyph lookup, queue producer and vertex conversion run
encoded instructions. GPU buffer reservation is a bounded synthetic boundary.
"""
from __future__ import annotations

import struct

import capstone
import native_layout_smoke
import native_pagination_smoke
import native_runtime_text_smoke
from native_scanner_model import MASK, signed
import project
import save_preview_smoke


def require(condition, message):
    if not condition:
        raise ValueError("Typography replay: " + message)


class GlyphCPU(save_preview_smoke.PreviewCPU):
    VERTICES = 0xE60000

    def __init__(self, source, image, native):
        super().__init__(source, image, native)
        decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        decoder.skipdata = True
        self.code.update({ins.address: (ins.mnemonic, ins.op_str)
                          for ins in decoder.disasm(self.read(0x1B47C, 0x220), 0x1B47C)})

    def step(self):
        mnemonic, operands = self.code[self.pc]
        if mnemonic == "mfctr":
            self.r[int(operands[1:])] = self.ctr
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        if mnemonic == ".byte":
            word = self.get(self.pc, 4)
            if word >> 26 == 31 and (word >> 1) & 1023 == 551:
                dest, ra, rb = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
                location = ((self.r[ra] if ra else 0) + self.r[rb]) & MASK
                count = location & 15
                self.v[dest] = bytes(16 - count) + self.read(location - count, count)
                self.pc += 4
                self.steps += 1
                return
        if mnemonic in ("mtctr", "bdnz", "vsraw", "vor", "stvehx", "vsplth"):
            self.executed.add(self.pc)
            args = operands.split(", ")
            next_pc = self.pc + 4
            if mnemonic == "mtctr":
                self.ctr = self.number(operands)
            elif mnemonic == "bdnz":
                self.ctr = (self.ctr - 1) & MASK
                if self.ctr:
                    next_pc = self.number(operands)
            elif mnemonic == "stvehx":
                location = self.indexed(args[1], args[2])
                lane = location & 14
                self.write(location & -2, self.v[int(args[0][1:])][lane:lane + 2])
            elif mnemonic == "vsplth":
                dest, value = int(args[0][1:]), int(args[1][1:])
                lane = int(args[2], 0) * 2
                self.v[dest] = self.v[value][lane:lane + 2] * 8
            else:
                dest, a, b = [int(value[1:]) for value in args]
                values = [(signed(x, 32) >> (y & 31)) & 0xFFFFFFFF if mnemonic == "vsraw" else x | y
                          for x, y in zip(self.vu(a), self.vu(b))]
                self.setv(dest, values)
            self.pc = next_pc
            self.steps += 1
            return
        super().step()

    def glyphs(self, text, scale=1.0):
        self.write(self.TEXT, text + b"\0")
        self.put(self.FONT + 0x14, 0, 4)
        self.put(self.STACK + 0x70, 0, 8)
        self.r[3:9] = [self.FONT, 0, 0, 0, self.TEXT, 0xFFFFFFFF]
        self.f[1:4] = [1.0, scale, scale]
        self.invoke(0x1BE28, stop=0xDEAD00)
        count = self.get(self.FONT + 0x14, 4)
        records = [struct.unpack(">10HIf", self.read(self.QUEUE + index * 28, 28)) for index in range(count)]
        self.r[3], self.r[30], self.r[5], self.r[6] = self.VERTICES, self.FONT, count, self.QUEUE
        self.pc = 0x1B47C
        self.execute_until(0x1B69C)
        vertices = [[struct.unpack(">hhIHH", self.read(self.VERTICES + index * 48 + corner * 12, 12))
                     for corner in range(4)] for index in range(count)]
        return records, vertices


def word_rows(result):
    rows = []
    for span in result["spans"]:
        position = (span["x"], span["y"])
        if rows and rows[-1][0][1] == position[1]:
            rows[-1][1].extend(bytes.fromhex(span["text_hex"]))
        else:
            rows.append((position, bytearray.fromhex(span["text_hex"])))
    return [(position, bytes(text)) for position, text in rows]


def smoke(source, image, native, previous_image, previous_native, payload, offset, long_text):
    cases = []
    fixtures = [
        ("reported_words", b"One follow English.", 260, {}),
        ("contractions_and_hyphens", b"We aren't shortening full-length words.", 430, {}),
        ("curly_quotes", "We aren’t shortening English.".encode("cp932"), 430, {}),
        ("overlong_token", b"One ABCDEFGHIJKLMNOPQRSTUVWXYZ done.", 260, {}),
        ("repeated_spaces", b"One   follow  English.", 260, {}),
        ("scaled_words", b"One follow English.", 440, {"scale": 1.5}),
        ("transformed_words", b"One follow English.", 260, {"position_scale": 0.75}),
        ("explicit_wait_and_newline", b"One follow\\k English.\\nNext page.", 260, {}),
        ("font_controls", b"One <F 30>follow<F 20> English.", 430, {}),
        ("japanese_unchanged", "あいうえおかきくけこ".encode("cp932"), 260, {}),
        ("mixed_cp932", "日本語 English words 日本語".encode("cp932"), 430, {}),
    ]
    metrics = native_layout_smoke.SourceMetrics(image)
    for name, text, width, options in fixtures:
        before = native_runtime_text_smoke.RuntimeCPU(source, previous_image, previous_native, text,
                                                      payload, offset, width=width, dialogue=True, height=628, **options)
        after = native_runtime_text_smoke.RuntimeCPU(source, image, native, text, payload, offset,
                                                     width=width, dialogue=True, height=628, **options)
        try:
            old = before.run()
        except ValueError as error:
            raise ValueError(name + ": retained input replay: " + str(error)) from error
        try:
            new = after.run()
        except ValueError as error:
            raise ValueError(name + ": corrected replay: " + str(error)) from error
        require(native_layout_smoke.byte_attributes(old) == native_layout_smoke.byte_attributes(new),
                name + ": text/font/scale changed")
        require(native_layout_smoke.control_records(old) == native_layout_smoke.control_records(new),
                name + ": native controls changed")
        rows = word_rows(new)
        if name == "reported_words":
            require(not any(b"follow" in row for _, row in word_rows(old)),
                    "retained native wrapping no longer reproduces the split")
        if name == "japanese_unchanged":
            require(native_layout_smoke.byte_records(old) == native_layout_smoke.byte_records(new)
                    and old["final_cursor"] == new["final_cursor"], "Japanese native wrapping changed")
        if name in ("reported_words", "contractions_and_hyphens", "curly_quotes",
                    "repeated_spaces", "mixed_cp932", "scaled_words", "transformed_words"):
            actual = b"".join(text for _, text in rows)
            cursor = 0
            boundaries = set()
            for _, row in rows[:-1]:
                cursor += len(row)
                boundaries.add(cursor)
            for token in actual.split(b" "):
                if not token or any(byte in (0x3C, 0x5C, 0x2A) for byte in token):
                    continue
                if any(ord(char) > 127 and char not in "‘’“”" for char in token.decode("cp932")):
                    continue
                begin = actual.find(token)
                factor = options.get("scale", 1) * options.get("position_scale", 1)
                if (metrics.width(token) + 48) * factor < width:
                    require(not any(begin < edge < begin + len(token) for edge in boundaries), name + ": fitting word split")
        after.assert_flags()
        paged = native_pagination_smoke.paginate(after)
        cases.append({"name": name, "rows": [text.hex() for _, text in rows],
                      "raw_vm_progress": paged["raw_vm_progress"], "bytes_and_controls_preserved": True})
    long_cpu = native_runtime_text_smoke.RuntimeCPU(source, image, native, b"A", payload, offset,
                                                   dialogue=True, height=628)
    decoded = long_cpu.decode_literal()
    require(decoded["text"] == long_text and decoded["next_byte"] == 2, "actual paragraph literal/terminator changed")
    long_result = long_cpu.run()
    rows = word_rows(long_result)
    require(b"".join(text for _, text in rows) == long_text, "actual paragraph lost bytes")
    cursor = 0
    for _, row in rows[:-1]:
        cursor += len(row)
        require(long_text[cursor - 1:cursor] == b" " or long_text[cursor:cursor + 1] == b" ",
                "actual paragraph broke a fitting word")
    long_skip = long_cpu.skip_pages(settle_opacity=True)
    glyph_cases = []
    for scale in (1.0, 0.625, 1.5):
        text = "gjpqyAあ".encode("cp932")
        old = GlyphCPU(source, previous_image, previous_native)
        new = GlyphCPU(source, image, native)
        old_records, old_vertices = old.glyphs(text, scale)
        records, vertices = new.glyphs(text, scale)
        require(records == old_records, "glyph queue/font/placement protocol changed")
        for record, before, after in zip(records, old_vertices, vertices):
            require(min(vertex[0] for vertex in after) == min(vertex[0] for vertex in before)
                    and min(vertex[1] for vertex in after) == min(vertex[1] for vertex in before)
                    and [vertex[2] for vertex in after] == [vertex[2] for vertex in before],
                    "cell correction moved its origin or changed colors")
            require(max(vertex[0] for vertex in after) == record[4] + 1
                    and max(vertex[1] for vertex in after) == record[5] + 1,
                    "requested full screen cell is not covered")
            require(max(vertex[3] for vertex in before) == record[8]
                    and max(vertex[4] for vertex in before) == record[9], "old inclusive UV shrink was not reproduced")
            require(max(vertex[3] for vertex in after) == record[8] + 1
                    and max(vertex[4] for vertex in after) == record[9] + 1,
                    "full final atlas row/column is not covered")
        glyph_cases.append({"scale": scale, "glyphs": len(records), "screen_cell_and_texel_extents_complete": True,
                            "full_texel_edges_covered": True})
    return {"source_sha256": project.digest(source), "image_sha256": project.digest(image),
            "word_cases": cases, "actual_paragraph_rows": len(rows), "actual_paragraph_skip": long_skip,
            "glyph_cases": glyph_cases, "runtime_accepted": False,
            "limitations": ["Finite encoded PPC/FP replay, not native GPU/RPCS3 execution.",
                            "GPU buffer reservation, texture resources and scanner span allocation are modeled boundaries.",
                            "Native controls delimit lookahead runs; overlong tokens retain character fallback.",
                            "No font, scenario text, raw checkpoint or installed files changed."]}
