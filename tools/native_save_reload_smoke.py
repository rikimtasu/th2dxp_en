"""Replay actual saved bytes through the encoded native chunk reader and history.

The EDGE codec itself and semaphore operations are external boundaries. The
native decoder prologue, source-pointer dereference, ALONE-size byte loop,
chunk alignment/continuation, return path, saved-entry iterator, scanner and
owned history writer execute their real encoded instructions.
"""
from __future__ import annotations

import lzma
import struct

import capstone
import native_history_smoke
import native_runtime_text_smoke
import native_runtime_text_patch
import project
import scenario_source

SAVE_SHA256 = "58e70b8be51854fc072054536a96324eb1b653e9533668c37beeb20fba060b56"
FAILED_ELF_SHA256 = "66786e6314959ef59e01e4bdfde87cab98a8c6b50ce65bc544f0dc6a8a32a108"
SAVE_HEADER, SAVE_STRIDE, SAVE_SLOTS = 0x2440, 0x3FC0, 100
STATE_OFFSET, CAPTION_OFFSET = 0x7C, 0x1080


def require(condition, message):
    if not condition:
        raise ValueError("Native save reload replay: " + message)


class NativeReaderCPU(native_history_smoke.HistoryCPU):
    """Use the source decoder rather than a Python substitute for its ABI."""

    def __init__(self, source, image, native, payload):
        super().__init__(source, image, native, payload, b"A")
        decoder = capstone.Cs(capstone.CS_ARCH_PPC,
                              capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        for begin, end in ((0x28D28, 0x2903C), (0x5CB3C, 0x5CB60)):
            self.code.update({ins.address: (ins.mnemonic, ins.op_str)
                              for ins in decoder.disasm(self.read(begin, end - begin), begin)})
        self.reader = None
        self.reader_calls = []
        self.scanner_checkpoints = []
        self.put(self.CTX + 0x28, 0, 1)
        self.put(self.CTX + 0x530, self.CTX + 0x900, 4)

    def begin_reader(self):
        require(self.reader is None, "nested native decoder call")
        destination, size, pointer, slot = self.r[3:7]
        self.reader = {"destination": destination, "size": size,
                       "pointer": pointer, "slot": slot, "chunks": [], "decoded": 0}

    def native_call(self, address, *arguments):
        # Edge fixtures enter the decoder directly; the injected saved-literal
        # caller reaches the same state through call(0x28D28).
        if address != 0x28D28:
            return super().native_call(address, *arguments)
        self.r[1] = self.STACK
        self.r[3:3 + len(arguments)] = arguments
        self.begin_reader()
        self.pc, self.lr = address, 0xDEAD00
        self.execute_until(0xDEAD00)

    def call(self, target):
        if target == 0x28D28:
            self.begin_reader()
            self.lr = self.pc + 4
            return target
        if target in (0xE7840, 0xE7860):
            # The native reader owns its decoder lock; synchronization is not
            # emulated. Do not fix or reinterpret any of its input registers.
            self.r[3], self.lr = 0, self.pc + 4
            return self.pc + 4
        if target == 0x6DF90:
            self.scanned.append(self.string(self.r[4]))
            self.scanner_checkpoints.append(self.r[8])
            return native_runtime_text_smoke.RuntimeCPU.call(self, target)
        if target == 0x69B38:
            self.backlog_submissions.append(self.string(self.r[3]))
        if target == 0xD0E18 and self.reader is not None and self.pc == 0x28DE8:
            self.check_output(self.r[3], self.r[5])
            self.reader["decoded"] += self.r[5]
        return super().call(target)

    def check_output(self, destination, size):
        reader = self.reader
        require(reader["destination"] <= destination
                and destination + size <= reader["destination"] + reader["size"]
                and self.heap.get(reader["destination"]) == reader["size"],
                "native chunk exceeds its exact owned output allocation")

    def step(self):
        if self.pc == 0x28D9C:
            # This is the actual faulting lwz r25,0(r26). In the negative
            # control its normal mapped-memory read faults at5DAA/20A3.
            pointer = self.r[26]
            prefix = self.get(pointer, 4)
            reader = self.reader
            require(reader["pointer"] <= pointer
                    and pointer + 4 + (prefix & 0x3FFFFFFF)
                    <= reader["pointer"] + reader["slot"],
                    "native chunk source exceeds its compressed slot")
            reader["chunks"].append({"pointer": pointer, "prefix": hex(prefix)})
        if self.pc == 0x28E48:
            # The ALONE size and compressed-payload boundaries were computed
            # by28DF8..28E44, including the native little-endian byte loop.
            header, compressed = self.r[29], self.r[25]
            size, compressed_size, destination = self.r[21], self.r[22], self.r[27]
            require(compressed == header + 13 and 0 < size <= scenario_source.CHUNK_SIZE,
                    "encoded ALONE header boundaries differ")
            stream = self.read(header, 13 + compressed_size)
            require(struct.unpack_from("<Q", stream, 5)[0] == size,
                    "encoded ALONE output size differs from its source bytes")
            require(stream[:5] == b"\x5d\x00\x20\x00\x00",
                    "EDGE codec boundary properties differ from the native 8192-byte dictionary")
            # Match ui_archive.validate_native_chunks: EDGE stops at usize,
            # not EOS. A range-coder flush is not another native output byte.
            decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
                "id": lzma.FILTER_LZMA1, "dict_size": 8192, "lc": 3, "lp": 0, "pb": 2,
            }])
            decoded = decoder.decompress(stream[13:], max_length=size)
            require(len(decoded) == size, "EDGE codec boundary output size differs")
            self.check_output(destination, size)
            self.write(destination, decoded)
            self.reader["decoded"] += size
            self.reader["chunks"][-1].update(output_bytes=size, properties=stream[:5].hex())
            self.executed.add(self.pc)
            self.pc = 0x28FBC
            self.steps += 1
            return
        if self.pc == 0x28FEC:
            reader = self.reader
            consumed = self.r[26] - reader["pointer"]
            require(reader["decoded"] == reader["size"] == self.r[31],
                    "native decoder return/output extent differs")
            require(0 < consumed <= reader["slot"]
                    and not any(self.read(reader["pointer"] + consumed, reader["slot"] - consumed)),
                    "native final chunk alignment/trailing slot bytes differ")
            reader["consumed_slot_bytes"] = consumed
            self.reader_calls.append(reader)
            self.reader = None
            self.decoder_calls += 1
        super().step()

    def restore_slot(self, saved, index):
        base = SAVE_HEADER + index * SAVE_STRIDE
        state = saved[base + STATE_OFFSET:base + CAPTION_OFFSET]
        self.write(self.STATE, state)
        self.flag_snapshot = self.read(0x667628, 144)
        checkpoint = self.get(self.STATE + 0x20, 4)
        used = self.get(self.STATE + 0x128, 4)
        trace = self.read(self.STATE + 0x12C, used)
        self.r[31], self.r[29] = self.ENGINE, 0
        # Execute the real caller's saved-counter capture/clear, used-length
        # test and branch to the injected reader. Stop at its original join.
        self.pc = 0x5CB3C
        self.execute_until(0x5CC30)
        require(self.r[27] == checkpoint, "saved raw checkpoint register changed")
        require(self.get(self.STATE + 0x128, 4) == used
                and self.read(self.STATE + 0x12C, used) == trace,
                "reload rewrote serialized trace bytes or used length")
        expected_state = bytearray(state)
        struct.pack_into(">I", expected_state, 0x20, 0)
        require(self.read(self.STATE, len(state)) == expected_state,
                "reload changed saved VM, branch, date, control or stale-tail state")
        self.assert_flags()
        return checkpoint, used, trace


def slot_entries(saved, index, image):
    """Read only the used trace, never the stale references in its fixed tail."""
    base = SAVE_HEADER + index * SAVE_STRIDE + STATE_OFFSET
    used = struct.unpack_from(">I", saved, base + 0x128)[0]
    require(used <= native_runtime_text_patch.TRACE_CAPACITY and used % 4 == 0,
            "fixture trace extent is invalid")
    trace = saved[base + 0x12C:base + 0x12C + used]
    headers = project.codec().read_elf_program_headers(image)
    texts, references, cursor = [], [], 0
    while cursor < used:
        tag = struct.unpack_from(">I", trace, cursor)[0]
        if tag == native_runtime_text_patch.TRACE_TAG:
            require(cursor + 8 <= used, "fixture contains partial reference")
            reference = struct.unpack_from(">I", trace, cursor + 4)[0]
            program, offset = reference >> 21, reference & 0x1FFFFF
            require(program < native_runtime_text_patch.SCENARIO_COUNT, "fixture program exceeds table")
            _, pointer, size, slot = struct.unpack_from(">IIII", image, scenario_source.TABLE_START + program * 16)
            payload, _ = scenario_source.read_chunks(
                image, project.codec().vaddr_to_fileoff(pointer, headers), slot, size)
            require(3 <= offset < size and payload[offset - 3] == 10,
                    "fixture no longer names the same-build literal")
            length = struct.unpack_from("<H", payload, offset - 2)[0]
            require(offset + length < size, "fixture literal exceeds its native payload")
            texts.append(payload[offset:offset + length])
            references.append((program, offset, payload))
            cursor += 8
        else:
            end = trace.find(b"\0", cursor)
            require(end >= cursor, "fixture inline string lacks terminator")
            texts.append(trace[cursor:end])
            cursor = (end + 4) & ~3
        require(cursor <= used, "fixture entry exceeds used length")
    return trace, texts, references


def reader_edges(source, image, native, payload):
    cases = []
    kit = project.codec()
    for size in (1, 32768, 65535):
        expected = bytes((index * 17 + 31) & 255 for index in range(size))
        if size == 1:
            encoded = struct.pack(">I", 0x40000001) + expected + bytes(3)
        else:
            encoded = scenario_source.pack(expected, kit)
        cpu = NativeReaderCPU(source, image, native, payload)
        cpu.write(cpu.PROGRAM, encoded)
        cpu.r[3] = size
        cpu.call(0x63D70)
        destination = cpu.r[3]
        cpu.write(destination + size, b"OUTPUT-END")
        cpu.native_call(0x28D28, destination, size, cpu.PROGRAM, len(encoded))
        require(cpu.r[3] == size and cpu.read(destination, size) == expected
                and cpu.read(destination + size, 10) == b"OUTPUT-END",
                "native chunk edge changed output bytes, return size or allocation end")
        require(0x28D9C in cpu.executed and 0x28FD0 in cpu.executed,
                "native source-pointer/continuation instructions were bypassed")
        cases.append({"uncompressed_bytes": size, "slot_bytes": len(encoded),
                      "native_chunks": len(cpu.reader_calls[0]["chunks"]),
                      "raw_chunk": size == 1, "exact_output_bound_preserved": True})
    return cases


def smoke(source, image, native, failed_image, failed_native, saved_bytes):
    """Require a parent-preserved, byte-exact authorized SAVEDATA snapshot."""
    require(project.digest(saved_bytes) == SAVE_SHA256
            and len(saved_bytes) == SAVE_HEADER + SAVE_SLOTS * SAVE_STRIDE,
            "authorized saved-byte fixture identity/100-slot extent changed")
    require(project.digest(failed_image) == FAILED_ELF_SHA256,
            "failed same-build ELF fixture changed")
    require(native.get("save_reload") and native.get("history", {}).get("ring_slots") == 100,
            "corrected native reload and original history slot count required")
    cases = []
    for index, fatal, first_reference in ((4, 0x5DAA, (0, 0x21A)),
                                          (9, 0x20A3, (6, 0x19A5))):
        trace, expected, references = slot_entries(saved_bytes, index, failed_image)
        require(references[0][:2] == first_reference, "saved bytes no longer bind the logged fatal caller")
        # Both artifacts retain exactly the same scenario payloads at these
        # offsets. Never migrate a reference across edited payload bytes.
        new_trace, new_expected, _ = slot_entries(saved_bytes, index, image)
        require(new_trace == trace and new_expected == expected,
                "corrected candidate changed genuine saved-reference meanings")
        before = NativeReaderCPU(source, failed_image, failed_native, references[0][2])
        before.initialize()
        try:
            before.restore_slot(saved_bytes, index)
        except ValueError as error:
            require(before.pc == 0x28D9C and before.r[26] == fatal
                    and f"{fatal:#x}+4" in str(error),
                    "failed artifact did not reproduce the exact native pointer fault")
        else:
            raise ValueError("Native save reload replay: failed artifact unexpectedly accepted its saved reference")
        cpu = NativeReaderCPU(source, image, native, references[0][2])
        cpu.initialize()
        checkpoint, used, restored_trace = cpu.restore_slot(saved_bytes, index)
        require(cpu.scanned == expected and cpu.backlog_submissions == expected,
                "saved literal/control bytes were lost, changed or reordered")
        require(all(value + b"\0" in cpu.contents() for value in expected),
                "actual owned history writer lost a saved string/control")
        require(not cpu.reader and cpu.decoder_calls == 1 and len(cpu.heap) == 1,
                "same-program saved references did not share/free the decoder")
        require(cpu.get(cpu.STATE + 0x20, 4) == 0,
                "source caller's raw-progress reset was bypassed")
        cpu.native_call(0x69A30)
        require(not cpu.heap, "saved-reference replay leaked history/decoder allocation")
        cases.append({"save_slot": index + 1, "slot_file_offset": hex(SAVE_HEADER + index * SAVE_STRIDE),
                      "used_trace_bytes": used, "trace_hex": restored_trace.hex(),
                      "saved_raw_checkpoint": checkpoint, "scanner_checkpoints": cpu.scanner_checkpoints,
                      "reference_program": first_reference[0], "reference_offset": hex(first_reference[1]),
                      "logged_fault_block": "0x28d90", "faulting_load": "0x28d9c",
                      "failed_read": hex(fatal), "failed_before_reproduced": True,
                      "same_build_literal_sha256": [project.digest(value) for value in expected],
                      "saved_entries_submitted": len(expected), "decoder_calls": cpu.decoder_calls,
                      "stale_tail_excluded": True, "date_story_branch_flags_preserved": True,
                      "complete_native_history_preserved": True})
    require(cases[-1]["used_trace_bytes"] == 16 and cases[-1]["saved_entries_submitted"] == 2,
            "latest slot's genuine used16-byte/stale-tail exclusion changed")
    return {"source_sha256": project.digest(source), "image_sha256": project.digest(image),
            "failed_elf_sha256": FAILED_ELF_SHA256, "savedata_sha256": SAVE_SHA256,
            "savedata_bytes": len(saved_bytes), "save_slot_bytes": SAVE_STRIDE,
            "save_slot_count": SAVE_SLOTS, "saved_cases": cases,
            "native_reader_edges": reader_edges(source, image, native, references[0][2]),
            "runtime_accepted": False,
            "limitations": ["Finite encoded PPC replay, not RPCS3, GPU or complete VM execution.",
                            "EDGE LZMA codec and decoder semaphores are explicit external boundaries.",
                            "Existing scanner span construction/libc/allocation boundaries remain modeled.",
                            "Replay stops at source5CC30; subsequent VM/branch resumption and visible saved page require manual acceptance.",
                            "The byte-exact authorized save is evidence, not a cross-build migration input."]}
