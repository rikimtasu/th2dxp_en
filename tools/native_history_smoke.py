"""Execute native history storage/reading; scanner/libc/allocator are boundaries."""
from __future__ import annotations

import capstone
import native_pagination_smoke
import native_runtime_text_smoke
import project


def require(condition, message):
    if not condition:
        raise ValueError("Native history replay: " + message)


class HistoryCPU(native_runtime_text_smoke.RuntimeCPU):
    def __init__(self, source, image, native, payload, text):
        super().__init__(source, image, native, text, payload, payload.find(text),
                         dialogue=False, height=628)
        decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        decoder.skipdata = True
        for begin, end in ((0x698B8, 0x6AA68), (0x6B9A8, 0x6BA84)):
            self.code.update({ins.address: (ins.mnemonic, ins.op_str)
                              for ins in decoder.disasm(self.read(begin, end - begin), begin)})
        self.scanned = []
        self.primitive_writes = []
        self.context_clear_calls = 0
        self.owned_history = bool(native.get("history"))

    def step(self):
        mnemonic, operands = self.code[self.pc]
        if mnemonic == "stwx":
            value, base, index = operands.split(", ")
            self.put(self.indexed(base, index), self.number(value), 4)
            self.executed.add(self.pc)
            self.pc += 4
            self.steps += 1
            return
        super().step()

    def call(self, target):
        if target in (0x458B8, 0x45930):
            if target == 0x458B8:
                self.r[3] = (self.r[3] + 15) & ~15
            return super().call(0x63D70 if target == 0x458B8 else 0x63DA0)
        if target == 0x69B38:
            return native_pagination_smoke.Replay.call(self, target)
        if target in (0xD54DC, 0xD0E18, 0xD83A4):
            size = len(self.string(self.r[4])) + 1 if target == 0xD54DC else self.r[5]
            self.primitive_writes.append((self.r[3], size))
            if self.owned_history:
                require(any(pointer <= self.r[3] and self.r[3] + size <= pointer + extent
                            for pointer, extent in self.heap.items()), "libc write exceeds owned history allocation")
        if target == 0x6DF90:
            self.scanned.append(self.string(self.r[4]))
            self.lr = self.pc + 4
            return self.pc + 4
        if target == 0x6DE5C:
            self.context_clear_calls += 1
            self.lr = self.pc + 4
            return self.pc + 4
        if target == 0x455AC:
            for index in range(4):
                self.setfloat(self.r[3] + index * 4, self.f[index + 1])
            self.lr = self.pc + 4
            return self.pc + 4
        return super().call(target)

    def native_call(self, address, *arguments):
        self.r[1] = self.STACK
        self.r[3:3 + len(arguments)] = arguments
        self.pc, self.lr = address, 0xDEAD00
        self.execute_until(0xDEAD00)

    def initialize(self):
        self.native_call(0x698B8)
        self.arena = self.get(0x64FD80, 4)

    def append(self, text):
        self.write(self.TEXT, text + b"\0")
        self.native_call(0x69B38, self.TEXT, 7, 9)

    def used(self):
        return self.get(self.arena + 0x14CE4, 4)

    def writer(self):
        return self.get(self.arena + 0x14CE0, 4)

    def contents(self, record=None):
        record = self.writer() if record is None else record
        pointer = self.get(record + 0xC, 4) if self.owned_history else record + 0xC
        used = self.get(record, 4) & 0x7FFFFFFF
        return self.read(pointer, used)


def smoke(source, image, native, payload, text):
    def fixture(corrected=True):
        report = native if corrected else {key: value for key, value in native.items()
                                                   if key not in ("history", "supplemental_code")}
        if not corrected:
            report["rx_extension"] = {"va_begin": 0x698B8, "size": 0}
        cpu = HistoryCPU(source, image if corrected else source, report, payload, text)
        cpu.initialize()
        return cpu

    old = fixture(False)
    old.append(text)
    old.native_call(0x69FE8, old.CTX, 0)
    corrupted = old.get(0x666DC0, 4)
    require(corrupted == 0x2E204164 and corrupted + 0x14 == 0x2E204178,
            "original encoded backlog copy does not reproduce the logged corruption")
    try:
        old.native_call(0x6B9A8)
    except ValueError as error:
        require("0x2e204178" in str(error), "original object-list traversal failed at a different address")
    else:
        raise ValueError("Native history replay: original corrupted object list did not fault")

    cases = []
    for length in (0, 827, 828, 1023, 1024, 1025, len(text), 65535):
        cpu = fixture()
        value = text if length == len(text) else b"g" * length
        sentinel = b"OBJECT-LIST-INTACT"
        cpu.write(0x666DC0, sentinel)
        cpu.append(value)
        expected = b"\xff" * 4 + value + b"\0"
        expected += bytes((-len(expected)) % 4)
        require(cpu.contents() == expected, "complete text/metadata/alignment differs")
        owned_before = set(cpu.heap)
        cpu.native_call(0x69FE8, cpu.CTX, 0)
        require(cpu.scanned == [value], "backlog open loses or changes complete text")
        require(set(cpu.heap) == owned_before, "backlog scratch leaks after synchronous scan")
        require(cpu.read(0x666DC0, len(sentinel)) == sentinel, "backlog corrupts global object list")
        if length == 65535:
            cpu.append(value)
            require(cpu.contents().count(value + b"\0") == 2,
                    "aggregate record growth truncates a full literal or following append")
        cases.append({"bytes": length, "used": cpu.used(),
                      "capacity": cpu.get(cpu.writer() + 0x10, 4), "full_backlog_text": True})
        cpu.native_call(0x69A30)
        require(not cpu.heap and cpu.get(0x64FD80, 4) == 0, "history destruction leaks owned payloads")

    metadata = fixture()
    metadata.append(b"a" * 827)
    metadata.native_call(0x69ABC, 321, 0, 1)
    metadata.append(b"TAIL")
    require(metadata.contents().endswith(b"\x80\0\x01A" + b"TAIL\0\0\0\0"),
            "explicit metadata crossing inline capacity lost its following text")
    metadata.native_call(0x69A30)
    require(not metadata.heap, "metadata growth leaks on destroy")

    restored = fixture()
    offset = payload.find(text)
    trace = (0xFF544852).to_bytes(4, "big") + offset.to_bytes(4, "big")
    restored.replay_saved(trace * 2)
    require(restored.scanned == [text, text] and restored.contents().count(text + b"\0") == 2,
            "actual saved-reference replay loses full native history text")
    restored.native_call(0x69A30)
    require(not restored.heap, "saved-reference history leaks on destroy")

    ring = fixture()
    for index in range(205):
        value = (str(index) + ":").encode() + text
        ring.append(value)
        require(value + b"\0" in ring.contents(), "ring slot reuse loses its full message")
        ring.native_call(0x69D0C)
        require(ring.used() == 0 and ring.get(ring.arena + 0x14CEC, 4) == min(index + 1, 100),
                "native finalization/count changed")
        require(ring.arena + 0x10 <= ring.writer() <= ring.arena + 0x1498C,
                "native writer escaped its original 100-slot ring")
    ring.native_call(0x6AA20)
    ring.arena = ring.get(0x64FD80, 4)
    require(len(ring.heap) == 1 and ring.used() == 0, "reset leaks overflow or retains old text")
    ring.append(text)
    ring.native_call(0x6AA20)
    ring.arena = ring.get(0x64FD80, 4)
    require(len(ring.heap) == 1 and ring.used() == 0, "repeated reset leaks history")
    ring.native_call(0x69A30)
    require(not ring.heap, "wrapped overflow records leak on destroy")
    return {"image_sha256": project.digest(image), "original_failure_reproduced": True,
            "original_corrupted_list_head": hex(corrupted), "original_fatal_read": hex(corrupted + 0x14),
            "whole_string_cases": cases, "ring_appends": 205, "ring_wraps": 2,
            "owned_writes_checked": True, "all_history_allocations_released": True,
            "explicit_metadata_growth": True, "saved_reference_appends": 2, "reset_cycles": 2,
            "runtime_accepted": False,
            "limitations": ["Encoded finite CPU replay, not a game/GPU run.",
                            "Allocation/libc primitives, scanner submission and unrelated context clear/vector scratch are explicit modeled boundaries."]}
