"""Finite source/encoded save-caption CPU replay; no native/GPU/save acceptance.

No files are written. All text construction, glyph mapping, placement and
vertex-record construction execute decoded ELF instructions. The only modeled
external calls are a bounded allocator and the source's literal %s snprintf.
Unsupported instructions, calls, memory access and nonfinite FP fail loudly.
"""
from __future__ import annotations

import math
import struct

import capstone
import project
from native_layout_smoke import SourceMetrics
from native_scanner_model import Scanner, f32, fused, signed

SOURCE_SHA256 = "8d8bc60d2b02d12f509a9a3ee9c126876ac8524d4f02c7871206aca9bd66e828"
INPUT_SHA256 = "d7d9c1decc82b9fa05d5bc3f317c6d0741363c7c53cca5bff22940782b017d86"
CPU_RANGES = ((0x1AF60, 0x1B1DC), (0x1BCB8, 0x1BE24),
              (0x1BE28, 0x1C170), (0x1C178, 0x1C5B0),
              (0x1C5B8, 0x1C8B0), (0x1D504, 0x1D51C),
              (0x1D538, 0x1D658), (0x1D7DC, 0x1D7E4), (0x11810, 0x11840),
              (0xA0E7C, 0xA0F1C))
BOUNDARIES = {"0x24580": "bounded synthetic aligned allocation for source font ranges",
              "0xd5b30": "bounded snprintf, only literal source %s with one string argument"}


def require(condition, message):
    if not condition:
        raise ValueError("Encoded save-preview smoke: " + message)


def address(value):
    return int(value, 0) if isinstance(value, str) else value


def execution_ranges(executed):
    """Exact contiguous sets of executed instruction addresses, end exclusive."""
    ranges = []
    for pc in sorted(executed):
        if ranges and address(ranges[-1]["end"]) == pc:
            ranges[-1]["end"] = hex(pc + 4)
        else:
            ranges.append({"begin": hex(pc), "end": hex(pc + 4)})
    return ranges


def units(text):
    """Independent finite fixture decoder; rejects rather than repairs input."""
    text.decode("cp932", errors="strict")
    result, offset = [], 0
    while offset < len(text):
        byte = text[offset]
        count = 2 if 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC else 1
        require(offset + count <= len(text), "fixture ends in a CP932 lead byte")
        require(count == 2 or 0x20 <= byte <= 0x7E, "fixture outside the source UI's supported printable subset")
        result.append(text[offset:offset + count])
        offset += count
    return result


class PreviewCPU(Scanner):
    """Reuse instruction semantics, not Scanner's synthetic span constructor."""
    # Growth's appended RW segment ends below E00000, unlike the older
    # dialogue model's B00000 arena. Never omit or overlay PT_LOAD mappings.
    CTX, TEXT, FONTS, RANGES = 0xE00000, 0xE10000, 0xE20000, 0xE21000
    SPANS, SPAN_END, STACK = 0xE40000, 0xEE0000, 0xEF0000
    FONT, MANAGER, QUEUE = 0xE25000, 0xE26000, 0xE50000
    TEXTURE, DESCRIPTOR, ALLOCATION = 0xE27000, 0xE28000, 0xE90000
    STOP = 0xA0F1C

    def __init__(self, source, image, report=None):
        super().__init__(source, b"", image=image, terminal_patch=False)
        self.code = {}
        self.allocations, self.format_calls = [], []
        self.allocate_next = self.ALLOCATION
        self.placement_submissions = []
        decoder = capstone.Cs(capstone.CS_ARCH_PPC,
                              capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        decoder.skipdata = True
        ranges = list(CPU_RANGES)
        if report is not None:
            extension = report["rx_extension"]
            begin = address(extension["va_begin"])
            ranges.append((begin, begin + extension["size"]))
            ranges.extend((row["virtual_address"], row["virtual_address"] + row["size"])
                          for row in report.get("supplemental_code", []))
        for begin, end in ranges:
            blob = self.read(begin, end - begin)
            decoded = list(decoder.disasm(blob, begin))
            require(sum(ins.size for ins in decoded) == len(blob) and all(ins.size == 4 for ins in decoded),
                    f"incomplete UI decode at {begin:#x}")
            self.code.update({ins.address: (ins.mnemonic, ins.op_str) for ins in decoded})
        # A warmed shared font library avoids its GPU/resource initialization.
        # PT_LOAD BSS remains zero; only these documented synthetic objects differ.
        self.put(0x657EA8, 1, 4)
        self.r[3:6] = [self.FONT, 0, 0]
        self.invoke(0x1AF60)
        require(self.get(self.FONT, 4) == self.ALLOCATION, "source font constructor did not allocate its range map")
        self.put(self.MANAGER + 0x50, self.FONT, 4)
        self.r[31] = self.MANAGER
        self.invoke(0x11810, stop=0x11840)
        require(self.get(self.FONT + 0x7C, 4) == 0x257038, "source main-font metric setter did not execute")
        # The GPU-owned texture handle and CPU queue are bounded synthetic RAM.
        # 1BCB8 itself executes: it constructs every actual 28-byte queue record.
        self.put(self.FONT + 8, self.TEXTURE, 4)
        self.put(self.TEXTURE, self.DESCRIPTOR, 4)
        self.put(self.DESCRIPTOR + 0x16, 0x600, 2)
        self.put(self.FONT + 0x10, self.QUEUE, 4)
        self.put(self.FONT + 0x94, 256, 4)
        self.put(0x257028, self.MANAGER, 4)
        self.constructor_executed = set(self.executed)
        self.constructor_steps = self.steps

    def invoke(self, begin, stop=None):
        stop = self.STOP if stop is None else stop
        self.pc, self.lr = begin, stop
        self.execute_until(stop)

    def call(self, target):
        if target in self.code:
            if target == 0x1BCB8:
                self.placement_submissions.append({
                    "pc": hex(self.pc), "font": hex(self.r[3]),
                    "x": signed(self.r[4], 16), "y": signed(self.r[5], 16),
                    "glyph_index": self.r[7] & 0xFFFF,
                    "cell_width": signed(self.r[9], 32),
                    "cell_height": signed(self.r[10], 32)})
            return super().call(target)
        self.calls += 1
        require(self.calls <= self.MAX_CALLS, "UI external call limit")
        self.lr = self.pc + 4
        if target == 0x24580:
            size, alignment = self.r[3], self.r[4]
            require(0 < size <= 0x1000 and alignment in (4, 8, 16), "allocator ABI outside finite fixture")
            pointer = (self.allocate_next + alignment - 1) & -alignment
            require(pointer + size < self.ALLOCATION + 0x10000, "synthetic allocation exhausted")
            self.write(pointer, bytes(size))
            self.allocations.append({"address": hex(pointer), "size": size, "alignment": alignment})
            self.allocate_next = pointer + size
            self.r[3] = pointer
        elif target == 0xD5B30:
            dest, capacity, fmt, arg = self.r[3:7]
            require(self.string(fmt) == b"%s" and 0 < capacity <= 0x100,
                    "unsupported snprintf format/capacity")
            payload = self.string(arg)
            self.write(dest, payload[:capacity - 1] + b"\0")
            self.format_calls.append({"destination": hex(dest), "capacity": capacity,
                                      "format_hex": self.string(fmt).hex(), "input_hex": payload.hex()})
            self.r[3] = len(payload)
        else:
            raise ValueError(f"Unmodeled save UI external boundary {target:#x} at {self.pc:#x}")
        return self.pc + 4

    def write(self, location, data):
        if getattr(self, "caption_active", False):
            allowed = ((self.STACK - 0x1000, self.STACK + 0x200),
                       (self.FONT + 0x14, self.FONT + 0x18),
                       (self.QUEUE, self.QUEUE + 256 * 28))
            require(any(begin <= location and location + len(data) <= end for begin, end in allowed),
                    f"caption write outside stack/vertex/count ABI at {self.pc:#x}: {location:#x}+{len(data)}")
        super().write(location, data)

    def step(self):
        if self.pc == 0xA0EA8:
            self.boundary_state = (self.r[:], self.f[:], self.cr[:], self.lr,
                                   self.xer_ca, self.fpscr, self.v[:])
        if not all(isinstance(value, int) or math.isfinite(value) for value in self.f):
            raise ValueError(f"Nonfinite FP outside model at {self.pc:#x}")
        super().step()
        if self.pc == 0xA0EAC:
            require((self.r, self.f, self.cr, self.lr, self.xer_ca, self.fpscr, self.v) ==
                    self.boundary_state, "display-bound helper clobbered caller CPU state")

    def caption(self, payload):
        require(len(payload) < 0x1000, "caption fixture exceeds synthetic slot")
        self.write(self.CTX + 0x1080, payload + b"\0")
        preserved = self.read(self.CTX, 0x2100)
        self.r[20], self.r[27], self.r[28], self.r[30] = 0, self.CTX, 0xFFFFFFFF, 100
        self.f[31] = 1.0
        self.put(self.FONT + 0x14, 0, 4)
        self.caption_active = True
        self.invoke(0xA0E7C)
        self.caption_active = False
        require(self.read(self.CTX, 0x2100) == preserved, "UI changed serialized-caption stand-in bytes")
        caption = self.string(self.STACK + 0x118)
        count = self.get(self.FONT + 0x14, 4)
        require(count <= 256, "source CPU queue exceeded synthetic capacity")
        records = []
        for index in range(count):
            pointer = self.QUEUE + index * 28
            raw = self.read(pointer, 28)
            fields = struct.unpack(">10HIf", raw)
            records.append({"layer": fields[0], "atlas_page": fields[1],
                            "x": signed(fields[2], 16), "y": signed(fields[3], 16),
                            "right_inclusive": signed(fields[4], 16),
                            "bottom_inclusive": signed(fields[5], 16),
                            "u": fields[6], "v": fields[7],
                            "u_right_inclusive": fields[8], "v_bottom_inclusive": fields[9],
                            "color": fields[10], "depth": fields[11]})
        return {"input_hex": payload.hex(), "visible_caption_hex": caption.hex(),
                "source_slot_bytes_preserved": True, "queue_records": records,
                "placement_submissions": self.placement_submissions,
                "steps": self.steps, "constructor_steps": self.constructor_steps,
                "executed_ranges": execution_ranges(self.executed),
                "constructor_executed_ranges": execution_ranges(self.constructor_executed),
                "allocator_calls": self.allocations, "formatter_calls": self.format_calls}


class SourceUI:
    """Independent algebra over pinned source data, never helper outputs."""
    def __init__(self, source):
        self.source = source
        self.metrics = SourceMetrics(source)
        self.scale = struct.unpack_from(">f", source, 0xA0468 - 0x10000)[0]
        fields = self.metrics.facts[0]["fields"]
        self.cell, self.default = fields[0x88], fields[0x8C]
        self.cell_pixels = self.round(self.cell)
        self.fixed_advance = self.round(self.default)
        self.ellipsis = source[0x106828 - 0x10000:0x10682A - 0x10000]
        require(self.ellipsis == b"\x81\x63", "source caption ellipsis literal changed")

    def round(self, value):
        return int(fused(float(value), self.scale, 0.5))

    def glyph(self, unit):
        if len(unit) == 1:
            code = struct.unpack_from(">H", self.source, 0x2514B0 + 2 * (unit[0] - 0x20))[0]
        else:
            code = int.from_bytes(unit, "big")
        index = 0
        for first, last in self.metrics.ranges:
            if first <= code <= last:
                index += code - first
                break
            index += last - first + 1
        else:
            index = 0
        pair = tuple(self.source[0x247038 + 2 * index:0x24703A + 2 * index])
        require(len(pair) == 2, "glyph index exceeds source metrics")
        return index, pair

    def geometry(self, text, *, proportional_ascii):
        result = []
        for origin in (420, 421):
            pen = origin
            for unit in units(text):
                index, (left, right) = self.glyph(unit)
                if len(unit) == 1 and proportional_ascii:
                    x = pen - self.round(left)
                    advance = self.round(left + right + self.cell - self.default) - self.round(left)
                else:
                    x = pen
                    advance = self.fixed_advance
                    if len(unit) == 2 and index in (0x1B29, 0x1B2D):
                        advance = self.cell_pixels
                result.append({"x": x, "y": 154, "glyph_index": index,
                               "cell_width": self.cell_pixels, "cell_height": self.cell_pixels,
                               "metric_ink_left": x + self.round(left),
                               "metric_ink_right_exclusive": x + self.round(left + right),
                               "advance": advance})
                pen += advance
        return result


def compare_geometry(result, expected, name):
    submissions = result["placement_submissions"]
    require(len(submissions) == len(expected), f"{name}: glyph submission count differs")
    for observed, wanted in zip(submissions, expected):
        require(all(observed[key] == wanted[key] for key in
                    ("x", "y", "glyph_index", "cell_width", "cell_height")),
                f"{name}: CPU placement differs from independent source-data geometry: {observed} != {wanted}")
    records = result["queue_records"]
    require(len(records) == len(expected), f"{name}: source vertex builder lost a glyph")
    for observed, wanted in zip(records, expected):
        index, cell = wanted["glyph_index"], wanted["cell_width"]
        right = wanted["x"] + cell - 1
        u = (index % 32) * 48
        u_right = u + 47
        if index in (0x1B29, 0x1B2D, 0x1B2F, 0x1C, 0x1B30):
            right += 1
        if index in (0x1B29, 0x1B2D, 0x1B2F):
            u_right += 1
        if index in (0x1C, 0x1B30):
            u += 8
            u_right -= 8
        require((observed["x"], observed["y"], observed["right_inclusive"],
                 observed["bottom_inclusive"], observed["atlas_page"], observed["u"],
                 observed["v"], observed["u_right_inclusive"], observed["v_bottom_inclusive"]) ==
                (wanted["x"], wanted["y"], right, wanted["y"] + cell - 1,
                 index // 1024, u, ((index % 1024) // 32) * 48,
                 u_right, ((index % 1024) // 32) * 48 + 47),
                f"{name}: actual 1BCB8 vertex record differs from independent source geometry")
    result["independent_source_glyph_sum"] = sum(item["advance"] for item in expected[:len(expected) // 2])
    result["independent_metric_ink_bounds"] = (
        [min(item["metric_ink_left"] for item in expected),
         max(item["metric_ink_right_exclusive"] for item in expected)] if expected else None)
    result["independent_cell_quad_bounds"] = (
        [min(item["x"] for item in records),
         max(item["right_inclusive"] + 1 for item in records)] if records else None)


def measurement_probe(source, image, report, text, oracle, *, extra_tracking=0, entry=0x1C5B8):
    """Execute the original full measurement loop; no semantic metric boundary."""
    cpu = PreviewCPU(source, image, report)
    cpu.write(cpu.TEXT, text + b"\0")
    cpu.r[3], cpu.r[4], cpu.f[1] = cpu.FONT, cpu.TEXT, oracle.scale
    before = set(cpu.executed)
    cpu.invoke(entry)
    expected = sum(oracle.round(left + right + oracle.cell - oracle.default + extra_tracking) - oracle.round(left)
                   for _, (left, right) in (oracle.glyph(unit) for unit in units(text)))
    require(cpu.f[1] == float(expected), "real 1C5B8 measurement differs from independent glyph sum")
    relocation = entry - 0x1C5B8
    require(0x1C61C + relocation in cpu.executed and 0x1C888 + relocation in cpu.executed,
            "real source measurement loop/return not covered")
    return {"input_hex": text.hex(), "measured": cpu.f[1], "independent_source_sum": expected,
            "executed_ranges": execution_ranges(cpu.executed - before),
            "scope": "native proportional measurement for all glyphs; caption clone retains fixed Japanese geometry"}


def source_right_edge(source):
    """Source slot nine-slice inner and outer X edges, not screenshot pixels."""
    def immediate(va, register):
        word = struct.unpack_from(">I", source, va - 0x10000)[0]
        require(word >> 26 == 14 and (word >> 21) & 31 == register and not (word >> 16) & 31,
                f"source slot-bound instruction changed at {va:#x}")
        return signed(word, 16)
    inner = immediate(0xA0720, 6)
    outer = immediate(0xA0728, 7)
    require((inner, outer) == (1010, 1030), "source slot X bounds changed")
    return inner, {"inner_right": inner, "outer_right": outer,
                   "source_inner_instruction": "0xa0720: li r6,0x3f2",
                   "source_outer_instruction": "0xa0728: li r7,0x406",
                   "source_scope": "slot border destination coordinates; conservative inner-edge caption bound",
                   "caption_origins": [420, 421], "conservative_width_from_shadow": inner - 421}


def exact_edge_fixture(oracle, right_edge):
    """Finite source-metric search for a <=32-byte caption touching the edge."""
    _, (left, _) = oracle.glyph(b"W")
    target = right_edge - 421 - oracle.cell_pixels + oracle.round(left)
    options = [(bytes([byte]), oracle.geometry(bytes([byte]), proportional_ascii=True)[0]["advance"])
               for byte in b"Wi.lM "]
    prefixes = {0: b""}
    for _ in range(31):
        for total, prefix in list(prefixes.items()):
            if len(prefix) >= 31:
                continue
            for unit, advance in options:
                new = total + advance
                if new <= target and new not in prefixes:
                    prefixes[new] = prefix + unit
        if target in prefixes:
            text = prefixes[target] + b"W"
            geometry = oracle.geometry(text, proportional_ascii=True)
            require(max(item["x"] + item["cell_width"] for item in geometry) == right_edge,
                    "independent exact-edge fixture does not touch source bound")
            return text
    raise ValueError("No <=32-byte exact-edge source-font fixture")


def quad_right(oracle, text, *, proportional_ascii=True):
    expected = oracle.geometry(text, proportional_ascii=proportional_ascii)
    return max((item["x"] + item["cell_width"] +
                int(item["glyph_index"] in (0x1B29, 0x1B2D, 0x1B2F, 0x1C, 0x1B30))
                for item in expected), default=421)


def expected_display(oracle, original_excerpt, right_edge):
    """Independent longest whole-CP932 prefix plus native ellipsis glyph."""
    text = original_excerpt
    try:
        text.decode("cp932", errors="strict")
    except UnicodeDecodeError:
        text = text[:-1]
        text.decode("cp932", errors="strict")
    if quad_right(oracle, text) <= right_edge:
        return text
    suffix = oracle.ellipsis
    body_units = units(text)
    for count in range(len(body_units), -1, -1):
        candidate = b"".join(body_units[:count]) + suffix
        if len(candidate) <= 32 and quad_right(oracle, candidate) <= right_edge:
            return candidate
    raise ValueError("Source ellipsis cannot fit save-preview bound")


def smoke(original: bytes, patched: bytes, report: dict) -> dict:
    """Replay supplied ELF bytes once per finite case; never emit/deploy an ELF."""
    source = project.source_bytes()
    require(project.digest(source) == SOURCE_SHA256, "pinned source identity differs")
    require(project.digest(original) == INPUT_SHA256 == report["input_sha256"], "reviewed original candidate identity differs")
    require(project.digest(patched) == report["output_sha256"], "encoded candidate/report identity differs")
    require(report["source_sha256"] == SOURCE_SHA256, "report names another source")
    for begin, end in CPU_RANGES:
        if begin == 0xA0E7C:
            continue
        expected = source[begin - 0x10000:end - 0x10000]
        require(original[begin - 0x10000:end - 0x10000] == expected and
                patched[begin - 0x10000:end - 0x10000] == expected,
                f"original font/UI CPU range changed at {begin:#x}")
    require({address(site["va"]) for site in report["source_sites"]} == {0xA0EA8, 0xA0EE4, 0xA0F14},
            "unexpected save-preview source-site set")
    for site in report["source_sites"]:
        offset = address(site["va"]) - 0x10000
        require(original[offset:offset + 4].hex() == site["input_before"] and
                patched[offset:offset + 4].hex() == site["after"],
                "source-site bytes do not match supplied report")
    for block in report["injected_blocks"]:
        offset = address(block["va"]) - 0x10000
        require(project.digest(patched[offset:offset + block["size"]]) == block["sha256"],
                "injected block bytes do not match supplied report")
    oracle = SourceUI(source)
    right_edge, bounds = source_right_edge(source)
    exact = exact_edge_fixture(oracle, right_edge)
    root = "I stick my hand out from the…".encode("cp932")
    fixtures = [("reported_caption", root), ("narrow_ascii_32", b"i" * 32),
                ("wide_ascii", b"W" * 16), ("wide_ascii_32", b"W" * 32),
                ("mixed_japanese_latin", "日本 iW 語…".encode("cp932")),
                ("mixed_32_overflow", "日".encode("cp932") * 7 + b"W" * 18),
                ("japanese_geometry", "日本語の記録…".encode("cp932")),
                ("japanese_32", "日".encode("cp932") * 16),
                ("native_punctuation_specials", bytes.fromhex("f043f047f049815cf04a")),
                ("mixed_special_32_overflow", b"W" * 20 + bytes.fromhex("f043f047") + b"W" * 8),
                ("empty", b""), ("short", b"I"), ("ellipsis", "…".encode("cp932")),
                ("ascii_ellipsis", b"Wait..."), ("exact_source_inner_edge", exact),
                ("over_source_inner_edge", exact + b"W"),
                ("hard_32_complete", b"A" * 32), ("hard_32_long", b"A" * 40),
                ("hard_32_split_pair", b"i" * 31 + "日".encode("cp932")),
                ("hard_32_complete_pair", b"i" * 30 + "日".encode("cp932")),
                ("c_string_terminator", b"OK\0not consumer visible")]
    cases = []
    for name, payload in fixtures:
        original_cpu = PreviewCPU(source, original)
        encoded_cpu = PreviewCPU(source, patched, report)
        before = original_cpu.caption(payload)
        after = encoded_cpu.caption(payload)
        original_caption = payload.partition(b"\0")[0][:32]
        try:
            original_caption.decode("cp932", errors="strict")
            split_pair = False
        except UnicodeDecodeError:
            require(name == "hard_32_split_pair", f"{name}: unexpected invalid source excerpt")
            split_pair = True
        require(bytes.fromhex(before["visible_caption_hex"]) == original_caption,
                f"{name}: original hard-32 consumer not reproduced")
        visible = bytes.fromhex(after["visible_caption_hex"])
        expected_caption = expected_display(oracle, original_caption, right_edge)
        require(visible == expected_caption, f"{name}: encoded display prefix/ellipsis differs from source-metric oracle")
        visible.decode("cp932", errors="strict")
        compare_geometry(after, oracle.geometry(visible, proportional_ascii=True), name + " encoded")
        if not split_pair:
            compare_geometry(before, oracle.geometry(original_caption, proportional_ascii=False), name + " original")
        if name in ("japanese_geometry", "japanese_32", "ellipsis", "empty"):
            require(before["queue_records"] == after["queue_records"] and visible == original_caption,
                    f"{name}: Japanese/empty native bytes or geometry changed")
        before_bound = before.get("independent_cell_quad_bounds")
        after_bound = after["independent_cell_quad_bounds"]
        require(after_bound is None or after_bound[1] <= right_edge,
                f"{name}: encoded caption's actual CPU quads exceed source inner edge")
        require(after["independent_metric_ink_bounds"] is None or
                after["independent_metric_ink_bounds"][1] <= right_edge,
                f"{name}: source-metric ink envelope exceeds source inner edge")
        if name == "reported_caption":
            require(before_bound[1] > right_edge and after_bound[1] <= right_edge,
                    "reported wide-spaced source overflow -> in-bounds encoded caption not reproduced")
        if name == "exact_source_inner_edge":
            require(after_bound[1] == right_edge and visible == original_caption,
                    "encoded exact-edge caption clipped or does not touch source inner bound")
        if name in ("wide_ascii_32", "mixed_32_overflow", "mixed_special_32_overflow", "over_source_inner_edge"):
            require(visible.endswith("…".encode("cp932")) and visible != original_caption,
                    f"{name}: overflowing excerpt was not whole-character ellipsized")
        require(0xA0E98 in encoded_cpu.executed and 0xA0EE4 in encoded_cpu.executed and
                0xA0F14 in encoded_cpu.executed, f"{name}: real caption format/draw sites not covered")
        if visible:
            require(0x1BCB8 in encoded_cpu.executed, f"{name}: real glyph vertex constructor not covered")
        cases.append({"name": name, "original": before, "encoded": after,
                      "expected_display_hex": expected_caption.hex(),
                      "valid_consumer_cp932": True, "original_hard32_split_pair": split_pair,
                      "encoded_inside_conservative_inner_edge": True,
                      "source_slot_bytes_unchanged": True})
    measurements = [measurement_probe(source, image, patch, text, oracle)
                    for image, patch in ((original, None), (patched, report))
                    for text in (b"iW .", "日本 iW 語…".encode("cp932"), b"")]
    root_case = cases[0]
    return {"status": "pass", "evidence_kind": "explicitly finite decoded PPC64 software model",
            "source_sha256": SOURCE_SHA256, "original_sha256": INPUT_SHA256,
            "encoded_sha256": project.digest(patched), "source_bounds": bounds,
            "synthetic_arena": ["0xe00000", "0xf00000"],
            "external_boundaries": BOUNDARIES, "cases": cases, "source_measurement_probes": measurements,
            "root_before": {"fixed_latin_advance": oracle.fixed_advance,
                            "caption_cell_bounds": root_case["original"]["independent_cell_quad_bounds"],
                            "overflow": True},
            "root_after": {"caption_cell_bounds": root_case["encoded"]["independent_cell_quad_bounds"],
                           "independent_glyph_sum": root_case["encoded"]["independent_source_glyph_sum"],
                           "inside_source_inner_edge": True},
            "limitations": [
                "Finite software PPC/FP execution, not native FP, GPU rasterization, game UI or save-format acceptance.",
                "FPSCR save/restore is opaque state; native FP exception/status flags and non-default rounding are not acceptance evidence.",
                "Synthetic warmed shared-font resource state, texture descriptor kind0x600 and bounded CPU queue; GPU loading/submission is not executed.",
                "Metric-derived ink envelopes and actual CPU quad bounds, not decoded texture-alpha raster ink.",
                "The slot/list outer draw and GPU clipping do not execute; source caption constructor, placement loop and glyph-record constructor do.",
                "Only the existing display excerpt is ellipsized on whole CP932 characters; dialogue/backlog and serialized save bytes are not modified."],
            "native_runtime_accepted": False, "production_cutover": False}
