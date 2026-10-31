"""Bounded source/encoded PPC scanner replay, not native FP, VM or GPU proof.

The scanner, angle handler and injected helpers execute their decoded bytes.
Only EXTERNAL_BOUNDARIES are synthetic calls. PT_LOAD file bytes are loaded at
p_vaddr; p_memsz-p_filesz is zero, never copied from trailing ELF metadata.
"""
from __future__ import annotations

from fractions import Fraction
import struct

import capstone

MASK = (1 << 64) - 1
EXTERNAL_BOUNDARIES = {
    "0x42f40": "CP932 lead-byte classifier",
    "0xd34a8": "bounded strlen",
    "0xd54dc": "bounded strcpy",
    "0xd0e18": "bounded memcpy",
    "0xd4668": "strtoul for finite valid command operands",
    "0xd3b8c": "strtod for finite valid command operands",
    "0x78d8c": "synthetic user option zero",
    "0x6dafc": "synthetic span constructor, captured arguments and source-layout fields; no drawing",
}


def signed(n, bits=64):
    n &= (1 << bits) - 1
    return n - (1 << bits) if n >> (bits - 1) else n


def f32(x):
    return struct.unpack(">f", struct.pack(">f", x))[0]


def fused(a, b, c):
    """Round a finite exact product+sum to binary32, nearest even."""
    value = Fraction(a) * Fraction(b) + Fraction(c)
    if not value:
        return 0.0
    negative = value < 0
    value = abs(value)
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if value < Fraction(2) ** exponent:
        exponent -= 1
    shift = max(exponent, -126) - 23
    scaled = value / Fraction(2) ** shift
    q, r = divmod(scaled.numerator, scaled.denominator)
    if 2 * r > scaled.denominator or (2 * r == scaled.denominator and q & 1):
        q += 1
    return (-1 if negative else 1) * float(q * Fraction(2) ** shift)


def load_segments(image):
    if image[:6] != b"\x7fELF\x02\x02":
        raise ValueError("Expected big-endian ELF64")
    phoff = struct.unpack_from(">Q", image, 0x20)[0]
    phsize, phcount = struct.unpack_from(">HH", image, 0x36)
    if phsize != 56 or phoff + phsize * phcount > len(image):
        raise ValueError("Invalid ELF program headers")
    segments = []
    for index in range(phcount):
        kind, flags, off, va, _, filesz, memsz, _ = struct.unpack_from(">IIQQQQQQ", image, phoff + index * phsize)
        if kind != 1 or not memsz:
            continue
        if filesz > memsz or off + filesz > len(image):
            raise ValueError("PT_LOAD exceeds file or memory extent")
        segments.append((va, memsz, image[off:off + filesz], flags))
    return segments


def source_font_facts(source):
    """Read pinned constructor-call immediates and the source range descriptors."""
    def immediate(va, reg):
        word = struct.unpack_from(">I", source, va - 0x10000)[0]
        if word >> 26 != 14 or (word >> 21) & 31 != reg or (word >> 16) & 31:
            raise ValueError(f"Constructor fact changed at {va:#x}")
        return signed(word, 16)
    # All four 1D504 setups, including the fourth following the older excerpt.
    decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    calls, values = [], {}
    for ins in decoder.disasm(source[0x117f0 - 0x10000:0x11b00 - 0x10000], 0x117f0):
        if ins.mnemonic == "li":
            register, value = ins.op_str.split(", ")
            values[int(register[1:])] = immediate(ins.address, int(register[1:]))
        if ins.mnemonic == "bl" and int(ins.op_str, 0) == 0x1D504:
            if not all(reg in values for reg in (4, 5, 6, 7, 8)):
                raise ValueError("Incomplete font constructor arguments")
            calls.append({"call_va": hex(ins.address), "fields": {
                0x80: values[5], 0x84: values[6], 0x88: values[4],
                0x8C: values[7], 0x90: values[8]}})
            values = {}
    if len(calls) != 4:
        raise ValueError(f"Expected four source font setups, got {len(calls)}")
    ranges = []
    for off in range(0xDA430, 0xDA430 + 98 * 8, 8):
        first, last = struct.unpack_from(">II", source, off)
        if not first:
            break
        low = struct.unpack_from(">H", source, first - 0x10000)[0]
        high = struct.unpack_from(">H", source, last - 0x10000)[0]
        if low > high:
            raise ValueError("Invalid source font range")
        ranges.append((low, high))
    if not ranges:
        raise ValueError("Missing source font ranges")
    return calls, ranges


class Scanner:
    """Execute real decoded instructions in explicitly bounded synthetic RAM."""
    CTX, TEXT, FONTS, RANGES = 0xB00000, 0xB10000, 0xB20000, 0xB21000
    STRINGS, SPANS, SPAN_END, STACK = 0xB30000, 0xB40000, 0xBE0000, 0xBF0000
    SPAN_SIZE = 0x14D0
    MAX_STEPS, MAX_CALLS = 300000, 10000

    def __init__(self, source, text, *, image=None, patch_report=None, x=0, y=0,
                 width=984, height=168, scale=1, position_scale=1, terminal_patch=True,
                 substitutions=None, existing_span=False, selected_font=0,
                 auxiliary_defaults=None, fallback_initialized=False,
                 fallback_width=None, dialogue=False):
        self.source = source
        self.image = source if image is None else image
        self.mem = bytearray(self.STACK + 0x10000)
        self.mapped = []
        for va, size, data, flags in load_segments(self.image):
            if va + size > self.CTX:
                raise ValueError("ELF mapping overlaps synthetic objects")
            if any(va < end and begin < va + size for begin, end in self.mapped):
                raise ValueError("Overlapping PT_LOAD mappings")
            self.mapped.append((va, va + size))
            self.mem[va:va + len(data)] = data
        self.mapped.append((self.CTX, len(self.mem)))
        self.r, self.f = [0] * 32, [0.0] * 32
        self.xer_ca = False
        self.ctr = 0
        # FPSCR is opaque save/restore state; exception/status arithmetic and
        # non-default rounding modes are outside this finite software model.
        self.fpscr = 0
        self.v = [bytes(16) for _ in range(32)]
        self.cr, self.lr, self.pc = [False] * 32, 0x6F17C, 0x6DF90
        self.r[1] = self.STACK
        self.r[3], self.r[4] = self.CTX, self.TEXT
        self.spans, self.events, self.steps, self.calls = [], [], 0, 0
        self.executed = set()
        self.cache_writes = []
        self.next_string = self.STRINGS
        if len(text) >= 0x3000:
            raise ValueError("Synthetic input overlaps substitution storage")
        self.write(self.TEXT, text + b"\0")
        self.put(self.CTX + 0x28, int(not dialogue), 1)
        if dialogue:
            self.put(self.CTX + 0x530, self.CTX + 0x900, 4)
        self.put(self.CTX + 0xF4, self.CTX + 0x804, 4)
        for off, value in {0x44: width, 0x48: height, 0x54: x, 0x58: y, 0x84: position_scale,
                           0x88: 1, 0x94: 48, 0x98: 48, 0xA4: scale,
                           0xA8: scale}.items():
            self.setfloat(self.CTX + off, value)
        self.put(self.CTX + 0xF0, self.CTX + 0x800, 4)
        self.put(self.CTX + 0xFC, self.TEXT + 0x8000, 4)
        self.put(self.CTX + 0x100, self.TEXT + 0x4000, 4)
        self.put(self.CTX + 0xDC, selected_font, 4)
        self.font_facts, ranges = source_font_facts(source)
        for index, (low, high) in enumerate(ranges):
            self.write(self.RANGES + 4 * index, struct.pack(">HH", low, high))
        self.write(self.RANGES + 4 * len(ranges), bytes(4))
        self.put(self.CTX + 0x10C, self.FONTS, 4)
        defaults = auxiliary_defaults or {}
        for index, fact in enumerate(self.font_facts):
            font = self.FONTS + 0x100 + index * 0x100
            self.put(self.FONTS + index * 4, font, 4)
            self.put(font, self.RANGES, 4)
            self.put(font + 0x7C, 0x257038 if index == 0 else 0, 4)
            for off, value in fact["fields"].items():
                self.put(font + off, defaults.get(index, {}).get(off, value), 4)
        self.put(0x657EB0, int(fallback_initialized), 1)
        if fallback_width is not None:
            self.put(0x26157D, fallback_width, 1)
        if existing_span:
            self.put(self.CTX + 0x510, self.SPANS, 4)
        for off, value in (substitutions or {}).items():
            if not 0 <= off < 0x4000 or len(value) >= 0x1000:
                raise ValueError("Synthetic substitution exceeds storage")
            self.write(self.TEXT + 0x4000 + off, value + b"\0")
        # The baseline terminal restoration is bytes, not a semantic PC override.
        if image is None and terminal_patch:
            self.write(0x6E64C, bytes.fromhex("4082fccc"))
        decoder = capstone.Cs(capstone.CS_ARCH_PPC,
                              capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        decoder.skipdata = True
        self.code = {}
        ranges_to_decode = [(0x6DF90, 0x6F17C), (0x6D4F8, 0x6D9F4),
                            (0x1D538, 0x1D658), (0x70534, 0x7054C),
                            (0x70630, 0x7064C), (0x706CC, 0x706E4),
                            (0x6F988, 0x6F9C8)]
        if patch_report is not None:
            extension = patch_report["rx_extension"]
            begin, size = extension["va_begin"], extension["size"]
            if isinstance(begin, str):
                begin = int(begin, 0)
            ranges_to_decode.append((begin, begin + size))
            ranges_to_decode.extend((row["virtual_address"], row["virtual_address"] + row["size"])
                                    for row in patch_report.get("supplemental_code", []))
        for start, end in ranges_to_decode:
            blob = self.read(start, end - start)
            instructions = list(decoder.disasm(blob, start))
            if sum(ins.size for ins in instructions) != len(blob) or any(ins.size != 4 for ins in instructions):
                raise ValueError(f"Incomplete PPC decode at {start:#x}")
            for ins in instructions:
                self.code[ins.address] = (ins.mnemonic, ins.op_str)

    def read(self, address, count):
        if count < 0 or not any(begin <= address and address + count <= end
                                for begin, end in self.mapped):
            raise ValueError(f"Model RAM bound at {self.pc:#x}: {address:#x}+{count}")
        return bytes(self.mem[address:address + count])

    def write(self, address, data):
        self.read(address, len(data))
        self.mem[address:address + len(data)] = data

    def get(self, address, size):
        return int.from_bytes(self.read(address, size), "big")

    def put(self, address, value, size):
        self.write(address, (value & ((1 << (8 * size)) - 1)).to_bytes(size, "big"))

    def scalar(self, address):
        return struct.unpack(">f", self.read(address, 4))[0]

    def setfloat(self, address, value):
        self.write(address, struct.pack(">f", value))

    def string(self, address):
        for count in range(0x10000):
            if not self.get(address + count, 1):
                return self.read(address, count)
        raise ValueError("Synthetic string exceeds bounded scan")

    def number(self, token):
        return self.r[int(token[1:])] if token.startswith("r") else int(token, 0)

    def address(self, operand):
        displacement, register = operand.rstrip(")").split("(")
        return (int(displacement, 0) + (0 if register == "r0" else self.number(register))) & MASK

    def indexed(self, ra, rb):
        return ((0 if ra == "r0" else self.number(ra)) + self.number(rb)) & MASK

    def bit(self, name):
        if name in ("lt", "gt", "eq", "so"):
            return ("lt", "gt", "eq", "so").index(name)
        if name.isdecimal():
            return int(name)
        return int(name[2:-2]) * 4 + ("lt", "gt", "eq", "so").index(name[-2:])

    def compare(self, field, a, b):
        self.cr[field * 4:field * 4 + 4] = [a < b, a > b, a == b, False]

    def vf(self, register):
        return struct.unpack(">4f", self.v[register])

    def vu(self, register):
        return struct.unpack(">4I", self.v[register])

    def setv(self, register, values, floating=False):
        self.v[register] = struct.pack(">4f" if floating else ">4I", *values)

    def snapshot(self, label):
        return {"event": label, "pc": hex(self.pc), "offset": self.get(self.r[1] + 0x4B0, 8),
                "r15_start": self.r[15], "r21_controls": self.r[21],
                "consumption": self.r[25], "flush": self.r[24],
                "newline": self.r[17], "wait": self.r[19], "page": self.r[16],
                "scalar_x": self.f[31], "vector_x": self.vf(24)[0],
                "vector_total": self.vu(23)[0], "vector_angle_exclusion": self.vu(25)[0],
                "vector_control_exclusion": self.vu(27)[0],
                "context_cursor": [self.scalar(self.CTX + off) for off in (0x54, 0x58)],
                "context_scale": [self.scalar(self.CTX + off) for off in (0xA4, 0xA8)],
                "selected_font_index": self.get(self.CTX + 0xDC, 4),
                "r3_byte_length": signed(self.r[3], 32),
                "scalar_measured_count": self.f[25], "vector_count_lane0": self.vf(31)[0]}

    def call(self, target):
        self.calls += 1
        if self.calls > self.MAX_CALLS:
            raise ValueError("Model call limit exceeded")
        self.lr = self.pc + 4
        if target in self.code:
            return target
        if target == 0x42F40:
            byte = self.r[3] & 255
            self.r[3] = int(0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC)
        elif target == 0xD34A8:
            self.r[3] = len(self.string(self.r[3]))
        elif target == 0xD54DC:
            self.write(self.r[3], self.string(self.r[4]) + b"\0")
        elif target == 0xD0E18:
            self.write(self.r[3], self.read(self.r[4], self.r[5]))
        elif target == 0xD4668:
            self.r[3] = int(self.string(self.r[3]), self.r[5])
        elif target == 0xD3B8C:
            self.f[1] = float(self.string(self.r[3]))
        elif target == 0x78D8C:
            self.put(self.r[4], 0, 1)
        elif target == 0x6DAFC:
            self.construct_span()
        else:
            raise ValueError(f"Unmodeled external boundary {target:#x} at {self.pc:#x}")
        return self.pc + 4

    def construct_span(self):
        base, length = self.r[1], signed(self.r[7], 32)
        address = self.SPANS + (len(self.spans) + 1) * self.SPAN_SIZE
        if address + self.SPAN_SIZE > self.SPAN_END or not 0 <= length < 0x3000:
            raise ValueError(f"Synthetic span allocation bound: {len(self.spans)} nodes, "
                             f"next {address:#x}, submitted length {length}")
        payload = self.read(self.r[4], length)
        constructor_strlen = len(payload.partition(b"\0")[0])
        span = {"address": hex(address), "text_hex": payload.hex(),
                "length": length, "constructor_strlen": constructor_strlen,
                "x": self.f[1], "y": self.f[2],
                "newline": self.r[8], "wait": self.r[9], "page": self.r[10],
                "end": self.get(base + 0x70, 8),
                "scale_x": self.scalar(self.CTX + 0xA4),
                "scale_y": self.scalar(self.CTX + 0xA8),
                "selected_font_index": self.get(self.CTX + 0xDC, 4)}
        self.write(address, bytes(self.SPAN_SIZE))
        for off, value in ((0x1C, span["wait"]), (0x1E, span["newline"]),
                           (0x1F, span["page"]), (0x20, span["end"])):
            self.put(address + off, value, 1)
        self.put(address + 0x24, span["selected_font_index"], 4)
        self.put(address + 0x28, self.FONTS, 4)
        self.put(address + 0x2C, constructor_strlen, 4)
        string_address = self.next_string
        self.next_string += constructor_strlen + 1
        if self.next_string > self.SPANS:
            raise ValueError("Synthetic span strings exceed their separate bounded arena")
        self.write(string_address, payload[:constructor_strlen] + b"\0")
        self.put(address + 0x30, string_address, 4)
        # Source43214 appends to the doubly linked owner list at context510.
        owner = self.CTX + 0x510
        previous = self.get(owner + 4, 4)
        self.put(address + 0xC, owner, 4)
        self.put(address + 0x10, previous, 4)
        if previous:
            self.put(previous + 0x14, address, 4)
        else:
            self.put(owner, address, 4)
        self.put(owner + 4, address, 4)
        self.put(owner + 8, self.get(owner + 8, 4) + 1, 4)
        self.setfloat(address + 0x64, fused(span["x"], self.scalar(self.CTX + 0x84), self.scalar(self.CTX + 0x34)))
        self.setfloat(address + 0x68, fused(span["y"], self.scalar(self.CTX + 0x88), self.scalar(self.CTX + 0x38)))
        self.setfloat(address + 0x84, span["scale_x"])
        self.setfloat(address + 0x88, span["scale_y"])
        # Source 6DA6C/78 stores strlen at+2C; 6DD00/18 splats it,
        # 6DD98 converts unsigned words to float and 6DDA0 stores+14BC.
        # Submitted length can exceed strlen for native unknown-star syntax.
        self.setfloat(address + 0x14BC, float(constructor_strlen))
        self.put(address + 0x14C8, length + 2 * bool(span["wait"]) + 2 * bool(span["newline"]), 4)
        self.setfloat(address + 0x14CC, -12345.0)
        self.spans.append(span)
        self.r[3] = address
        self.put(address + 0x18, 1, 4)

    def step(self):
        if self.pc not in self.code:
            raise ValueError(f"Execution outside decoded code at {self.pc:#x}")
        if self.steps >= self.MAX_STEPS:
            raise ValueError(f"Instruction limit at {self.pc:#x}")
        self.executed.add(self.pc)
        mnemonic, operands = self.code[self.pc]
        p = operands.split(", ") if operands else []
        next_pc = self.pc + 4
        ri = lambda s: int(s[1:])
        n = self.number
        labels = {0x6E1C4: "dispatch", 0x6E9D8: "join", 0x6EC14: "after_bounds",
                  0x6F03C: "commit", 0x6E5CC: "before_angle_handler",
                  0x6E5D0: "after_angle_handler", 0x6EC50: "submission_gate"}
        if self.pc in labels:
            self.events.append(self.snapshot(labels[self.pc]))
        if mnemonic == "nop":
            pass
        elif mnemonic in ("li", "lis"):
            self.r[ri(p[0])] = (n(p[1]) << (16 if mnemonic == "lis" else 0)) & MASK
        elif mnemonic in ("ori", "or", "xori", "xor", "add", "addc", "addic", "addi", "subf", "subfc", "neg", "addze"):
            a = 0 if mnemonic == "addi" and p[1] == "r0" else n(p[1])
            b = n(p[2]) if len(p) > 2 else 0
            value = {"ori": lambda: a | b, "or": lambda: a | b,
                     "xori": lambda: a ^ b, "xor": lambda: a ^ b,
                     "add": lambda: a + b, "addc": lambda: a + b,
                     "addic": lambda: a + b, "addi": lambda: a + b,
                     "subf": lambda: b - a, "subfc": lambda: b - a,
                     "neg": lambda: -a, "addze": lambda: a + int(self.xer_ca)}[mnemonic]()
            if mnemonic in ("addc", "addic", "addze"):
                # PPC64 CA is the carry out of the full 64-bit unsigned sum.
                operand = int(self.xer_ca) if mnemonic == "addze" else b & MASK
                self.xer_ca = a + operand > MASK
            elif mnemonic == "subfc":
                self.xer_ca = (b & MASK) >= (a & MASK)
            self.r[ri(p[0])] = value & MASK
        elif mnemonic == "subfic":
            # rD = SIMM - rA; CA reports no borrow out of the 32-bit difference.
            a, immediate = n(p[1]), n(p[2])
            self.xer_ca = (a & 0xFFFFFFFF) <= (immediate & 0xFFFFFFFF)
            self.r[ri(p[0])] = (immediate - a) & MASK
        elif mnemonic in ("mr", "mflr", "mtlr", "mfcr", "mtcrf"):
            if mnemonic == "mr": self.r[ri(p[0])] = n(p[1])
            elif mnemonic == "mflr": self.r[ri(p[0])] = self.lr
            elif mnemonic == "mtlr": self.lr = n(p[0])
            elif mnemonic == "mfcr": self.r[ri(p[0])] = sum(int(bit) << (31 - i) for i, bit in enumerate(self.cr))
            else:
                mask, value = n(p[0]), n(p[1])
                for field in range(8):
                    if mask & (1 << (7 - field)):
                        for bit in range(field * 4, field * 4 + 4):
                            self.cr[bit] = bool(value & (1 << (31 - bit)))
        elif mnemonic in ("extsw", "extsh", "extsb", "clrldi", "clrlwi", "sldi", "slwi", "srwi", "srawi"):
            a = n(p[1]); shift = n(p[2]) if len(p) > 2 else 0
            if mnemonic.startswith("exts"):
                value = signed(a, {"extsw": 32, "extsh": 16, "extsb": 8}[mnemonic])
            elif mnemonic in ("clrldi", "clrlwi"):
                value = a & ((1 << ((64 if mnemonic == "clrldi" else 32) - shift)) - 1)
            elif mnemonic in ("sldi", "slwi"): value = a << shift
            elif mnemonic == "srwi": value = (a & 0xFFFFFFFF) >> shift
            else:
                value = signed(a, 32) >> shift
                self.xer_ca = signed(a, 32) < 0 and bool((a & 0xFFFFFFFF) & ((1 << shift) - 1))
            self.r[ri(p[0])] = value & (0xFFFFFFFF if mnemonic == "slwi" else MASK)
        elif mnemonic in ("rlwinm", "rlwimi"):
            a, shift, begin, end = n(p[1]) & 0xFFFFFFFF, n(p[2]), n(p[3]), n(p[4])
            rotated = ((a << shift) | (a >> ((32 - shift) % 32))) & 0xFFFFFFFF
            mask = sum(1 << (31 - i) for i in range(32)
                       if (begin <= i <= end if begin <= end else i >= begin or i <= end))
            self.r[ri(p[0])] = (rotated & mask) | ((n(p[0]) & ~mask) if mnemonic == "rlwimi" else 0)
        elif mnemonic == "mulhw":
            self.r[ri(p[0])] = signed((signed(n(p[1]), 32) * signed(n(p[2]), 32)) >> 32, 32) & MASK
        elif mnemonic in ("mullw", "divw"):
            a, b = signed(n(p[1]), 32), signed(n(p[2]), 32)
            if mnemonic == "mullw":
                value = a * b
            else:
                if not b or (a == -(1 << 31) and b == -1):
                    raise ValueError(f"Undefined signed division at {self.pc:#x}")
                value = (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1)
            self.r[ri(p[0])] = signed(value, 32) & MASK
        elif mnemonic in ("std", "stw", "sth", "stb", "stdu", "stbx", "stfiwx", "stfd", "stfs"):
            address = self.indexed(p[1], p[2]) if mnemonic in ("stbx", "stfiwx") else self.address(p[1])
            if mnemonic == "stfs": self.setfloat(address, self.f[ri(p[0])])
            elif mnemonic == "stfd":
                value = self.f[ri(p[0])]
                self.write(address, value.to_bytes(8, "big") if isinstance(value, int) else struct.pack(">d", value))
            elif mnemonic == "stfiwx": self.put(address, int(self.f[ri(p[0])]), 4)
            else: self.put(address, n(p[0]), {"std": 8, "stdu": 8, "stw": 4, "sth": 2, "stb": 1, "stbx": 1}[mnemonic])
            if mnemonic == "stdu": self.r[ri(p[1].split("(")[1].rstrip(")"))] = address
        elif mnemonic in ("ld", "lwz", "lhz", "lbz", "lbzx", "lhzx", "lwzx", "lfs", "lfd", "lfsx"):
            address = self.indexed(p[1], p[2]) if mnemonic.endswith("x") else self.address(p[1])
            if mnemonic in ("lfs", "lfsx"): self.f[ri(p[0])] = self.scalar(address)
            elif mnemonic == "lfd": self.f[ri(p[0])] = struct.unpack(">d", self.read(address, 8))[0]
            else: self.r[ri(p[0])] = self.get(address, {"ld": 8, "lwz": 4, "lhz": 2, "lbz": 1, "lbzx": 1, "lhzx": 2, "lwzx": 4}[mnemonic])
        elif mnemonic in ("cmpwi", "cmpw", "cmplw", "cmplwi"):
            field = int(p.pop(0)[2:]) if p[0].startswith("cr") else 0
            a, b = n(p[0]), n(p[1])
            unsigned = mnemonic in ("cmplw", "cmplwi")
            self.compare(field, a & 0xFFFFFFFF if unsigned else signed(a, 32),
                         b & 0xFFFFFFFF if unsigned else signed(b, 32))
        elif mnemonic in ("cror", "crnor", "crnand", "crorc"):
            a, b = self.cr[self.bit(p[1])], self.cr[self.bit(p[2])]
            self.cr[self.bit(p[0])] = {"cror": a or b, "crnor": not(a or b),
                                      "crnand": not(a and b), "crorc": a or not b}[mnemonic]
        elif mnemonic in ("b", "bl", "blr", "beq", "bne", "bgt", "bge", "blt", "ble"):
            if mnemonic == "bl": next_pc = self.call(n(p[0]))
            elif mnemonic == "blr": next_pc = self.lr
            elif mnemonic == "b": next_pc = n(p[0])
            else:
                field = int(p[0][2:]) if len(p) > 1 else 0
                lt, gt, eq, _ = self.cr[field * 4:field * 4 + 4]
                if {"beq": eq, "bne": not eq, "bgt": gt, "bge": not lt, "blt": lt, "ble": not gt}[mnemonic]:
                    next_pc = n(p[-1])
        elif mnemonic in ("mffs", "mtfsf"):
            if mnemonic == "mffs":
                self.f[ri(p[0])] = self.fpscr
            else:
                mask, value = n(p[0]), self.f[ri(p[1])]
                bits = value if isinstance(value, int) else int.from_bytes(struct.pack(">d", value), "big")
                for field in range(8):
                    if mask & (1 << (7 - field)):
                        field_mask = 15 << (28 - 4 * field)
                        self.fpscr = (self.fpscr & ~field_mask) | (bits & field_mask)
        elif mnemonic in ("fmr", "frsp", "fmuls", "fadds", "fsubs", "fdivs", "fmadds", "fnmsubs", "fmsubs", "fcfid", "fctiwz", "fcmpu", "fadd", "fsub", "fmul", "fdiv", "fsel"):
            if mnemonic == "fcmpu": self.compare(int(p[0][2:]), self.f[ri(p[1])], self.f[ri(p[2])])
            else:
                a = self.f[ri(p[1])]
                b = self.f[ri(p[2])] if len(p) > 2 else 0
                c = self.f[ri(p[3])] if len(p) > 3 else 0
                value = {"fmr": lambda: a, "frsp": lambda: f32(a),
                         "fmuls": lambda: fused(a,b,0), "fadds": lambda: fused(a,1,b),
                         "fsubs": lambda: fused(a,1,-b), "fdivs": lambda: f32(a/b),
                         "fmadds": lambda: fused(a,b,c), "fnmsubs": lambda: fused(-a,b,c),
                         "fmsubs": lambda: fused(a,b,-c),
                         "fadd": lambda: a+b, "fsub": lambda: a-b,
                         "fmul": lambda: a*b, "fdiv": lambda: a/b,
                         "fsel": lambda: b if a >= 0 else c,
                         "fcfid": lambda: float(signed(int.from_bytes(struct.pack(">d", a), "big"))),
                         "fctiwz": lambda: int(a) & MASK}[mnemonic]()
                self.f[ri(p[0])] = value
        elif mnemonic in ("stvx", "lvx", "stvewx", "lvewx"):
            address = self.indexed(p[1], p[2])
            if mnemonic == "stvx": self.write(address & ~15, self.v[ri(p[0])])
            elif mnemonic == "lvx": self.v[ri(p[0])] = self.read(address & ~15, 16)
            else:
                lane = address & 12
                if mnemonic == "stvewx":
                    data = self.v[ri(p[0])][lane:lane + 4]
                    self.write(address & ~3, data)
                    if self.SPANS <= address < self.SPAN_END:
                        self.cache_writes.append({"pc": hex(self.pc), "address": hex(address & ~3), "bytes": data.hex()})
                else:
                    data = bytearray(self.v[ri(p[0])])
                    data[lane:lane + 4] = self.read(address & ~3, 4)
                    self.v[ri(p[0])] = bytes(data)
        elif mnemonic == ".byte":
            word = self.get(self.pc, 4)
            op, dest, ra, rb, xo = word >> 26, (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31, (word >> 1) & 1023
            address = ((self.r[ra] if ra else 0) + self.r[rb]) & MASK
            if op != 31 or xo != 519:
                raise ValueError(f"Unmodeled instruction {word:08x} at {self.pc:#x}")
            count = 16 - (address & 15)
            self.v[dest] = self.read(address, count) + bytes(16 - count)
        elif mnemonic in ("vspltisw", "vspltw", "vsldoi", "vadduwm", "vsubuwm", "vslw", "vcfsx", "vmaddfp", "vnmsubfp", "vsubfp", "vaddfp", "vctsxs", "vcmpeqfp.", "vcmpgefp."):
            dest = ri(p[0]); a = ri(p[1]) if p[1].startswith("v") else 0
            b = ri(p[2]) if len(p) > 2 and p[2].startswith("v") else 0
            if mnemonic == "vspltisw": self.setv(dest, [n(p[1]) & 0xFFFFFFFF] * 4)
            elif mnemonic == "vspltw": self.setv(dest, [self.vu(a)[n(p[2])]] * 4)
            elif mnemonic == "vsldoi":
                shift = n(p[3]); self.v[dest] = (self.v[a] + self.v[b])[shift:shift + 16]
            elif mnemonic in ("vadduwm", "vsubuwm", "vslw"):
                fn = {"vadduwm": lambda x,y: x+y, "vsubuwm": lambda x,y: x-y, "vslw": lambda x,y: x << (y & 31)}[mnemonic]
                self.setv(dest, [fn(x,y) & 0xFFFFFFFF for x,y in zip(self.vu(a),self.vu(b))])
            elif mnemonic == "vcfsx": self.setv(dest, [f32(signed(x,32) / 2**n(p[2])) for x in self.vu(a)], True)
            elif mnemonic == "vctsxs": self.setv(dest, [max(-2**31,min(2**31-1,int(x * 2**n(p[2])))) & 0xFFFFFFFF for x in self.vf(a)])
            elif mnemonic in ("vmaddfp", "vnmsubfp"):
                c = ri(p[3]); self.setv(dest, [fused(x,y,z) if mnemonic == "vmaddfp" else fused(-x,y,z) for x,y,z in zip(self.vf(a),self.vf(b),self.vf(c))], True)
            elif mnemonic in ("vsubfp", "vaddfp"):
                self.setv(dest, [fused(x,1,-y if mnemonic == "vsubfp" else y) for x,y in zip(self.vf(a),self.vf(b))], True)
            else:
                values = [x == y if mnemonic == "vcmpeqfp." else x >= y for x,y in zip(self.vf(a),self.vf(b))]
                self.setv(dest, [0xFFFFFFFF if x else 0 for x in values])
                self.cr[24:28] = [all(values),False,not any(values),False]
        else:
            raise ValueError(f"Unmodeled instruction {mnemonic} {operands} at {self.pc:#x}")
        self.pc = next_pc
        self.steps += 1

    def execute_until(self, stop):
        while self.pc != stop:
            self.step()

    def run(self):
        self.execute_until(0x6F17C)
        for span in self.spans:
            address = int(span["address"], 0)
            span["design_pixel_width"] = self.scalar(address + 0x14CC)
            span["original_byte_progress"] = self.scalar(address + 0x14BC)
        return {"input_hex": self.string(self.TEXT).hex(), "steps": self.steps,
                "spans": self.spans, "events": self.events, "cache_writes": self.cache_writes,
                "final_cursor": [self.scalar(self.CTX + off) for off in (0x54, 0x58)],
                "selected_font_index": self.get(self.CTX + 0xDC, 4),
                "return_control_seen": self.r[3]}
