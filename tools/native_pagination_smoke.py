"""Execute encoded pagination, native wait/accounting, unlink and clear paths.

Glyph completion, allocation/free and flower drawing are explicit synthetic
boundaries. This is finite software CPU/FP evidence, not GPU/emulator proof.
"""
from __future__ import annotations

import capstone

import project
from native_scanner_model import Scanner

STOP = 0xDEAD00


def require(condition, message):
    if not condition:
        raise ValueError("Encoded pagination smoke: " + message)


class Replay(Scanner):
    def __init__(self, source, text, *, image, patch_report, **options):
        super().__init__(source, text, image=image, patch_report=patch_report, **options)
        self.MAX_STEPS = 4000000
        self.freed = set()
        self.flowers = []
        decoder = capstone.Cs(capstone.CS_ARCH_PPC,
                              capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        decoder.skipdata = True
        for begin, end in ((0x42FC8, 0x43080), (0x6DE5C, 0x6DF7C),
                           (0x6F884, 0x6FA54), (0x704D8, 0x7071C)):
            for instruction in decoder.disasm(self.read(begin, end - begin), begin):
                self.code[instruction.address] = (instruction.mnemonic, instruction.op_str)

    def call(self, target):
        if target == 0x63DA0:
            address = self.r[3]
            owned = {int(span["address"], 0) for span in self.spans}
            owned.update(self.get(int(span["address"], 0) + 0x30, 4) for span in self.spans)
            require(address in owned and address not in self.freed,
                    "free is outside owned allocations or repeats an allocation")
            self.freed.add(address)
            self.lr = self.pc + 4
            self.r[3] = 0
            return self.pc + 4
        if target == 0x55C18:
            self.flowers.append([self.scalar(self.r[4] + off) for off in (0, 4)])
            self.lr = self.pc + 4
            return self.pc + 4
        if target == 0x5A2A0:
            self.f[1] = 1.0
            self.lr = self.pc + 4
            return self.pc + 4
        if target == 0x455C4:
            # Source vector scratch cleanup; no glyph or queue mutation.
            self.lr = self.pc + 4
            return self.pc + 4
        return super().call(target)

    def invoke(self, address, stop=STOP):
        self.r[3] = self.CTX
        self.pc, self.lr = address, stop
        self.execute_until(stop)

    def queue(self):
        result, node = [], self.get(self.CTX + 0x510, 4)
        while node:
            require(node not in result and node not in self.freed, "queue cycle or freed node")
            result.append(node)
            node = self.get(node + 0x14, 4)
        require(len(result) == self.get(self.CTX + 0x518, 4), "native list count differs")
        require((result[-1] if result else 0) == self.get(self.CTX + 0x514, 4), "native tail differs")
        for index, node in enumerate(result):
            require(self.get(node + 0x10, 4) == (result[index - 1] if index else 0),
                    "native previous link differs")
        return result

    def complete_glyphs(self, node):
        # Enter the actual native completion/wait/accounting block after the
        # explicitly modeled glyph-completion boundary; no semantic PC patches.
        self.put(node + 0x18, 2, 4)
        self.setfloat(node + 0x14B8, self.scalar(node + 0x14BC))
        self.r[30], self.r[31] = node, self.CTX
        # Source70070/80 and703D0 define these live renderer registers;
        # source6FDC4 defines its flower-position scratch vector.
        self.r[24], self.r[25], self.r[28] = 0, 1, self.r[1] + 0x80
        self.f[31] = 0.0
        self.pc, self.lr = 0x704D8, STOP
        self.execute_until(0x70710)
        require(self.get(node + 0x18, 4) == 3, "native completion did not finish span")


def paginate(model):
    initial = model.queue()
    expected_bytes = b"".join(model.string(model.get(node + 0x30, 4)) for node in initial)
    expected_progress = sum(model.get(node + 0x14C8, 4) for node in initial)
    progress_address = model.get(model.CTX + 0xF4, 4)
    baseline_progress = model.get(progress_address, 4)
    seen, visible, pages = set(), bytearray(), [[]]
    automatic_waits = original_waits = 0
    while len(seen) < len(initial):
        node = next((node for node in model.queue() if node not in seen), None)
        require(node is not None, "unread span was removed")
        y = model.scalar(node + 0x68) - model.scalar(model.CTX + 0x38)
        cell = (model.scalar(model.CTX + 0x98) * model.scalar(node + 0x88)
                * model.scalar(model.CTX + 0x88))
        require(y >= 0 and y + cell <= model.scalar(model.CTX + 0x48),
                "page exposes a row outside the configured vertical extent")
        visible.extend(model.string(model.get(node + 0x30, 4)))
        pages[-1].append({"y": y, "height": cell, "source_span": hex(node)})
        seen.add(node)
        boundary = model.get(model.CTX + 0x550, 4)
        before_progress = model.get(progress_address, 4)
        model.complete_glyphs(node)
        require(model.get(progress_address, 4) - before_progress == model.get(node + 0x14C8, 4),
                "native byte accounting differs from original span consumption")
        if model.get(model.CTX + 0x22, 1):
            pending = model.queue()
            require(all(model.get(later + 0x18, 4) == 1 for later in pending
                        if later not in seen), "unread spans activated before advance")
            model.invoke(0x6F884)
            if node == boundary:
                automatic_waits += 1
                pages.append([])
                require(node in model.freed, "automatic advance did not retire the completed prefix")
                require(all(later not in model.freed for later in pending if later not in seen),
                        "automatic advance freed unread content")
                require(model.get(progress_address, 4) == before_progress + model.get(node + 0x14C8, 4),
                        "automatic advance changed raw VM progress")
            else:
                original_waits += 1
                require(node not in model.freed, "ordinary source wait was converted to a page clear")
    require(bytes(visible) == expected_bytes, "visible bytes were lost, duplicated or reordered")
    require(model.get(progress_address, 4) - baseline_progress == expected_progress,
            "total original raw byte accounting changed")
    require(not model.get(model.CTX + 0x550, 4), "automatic boundary remains after final page")
    if not pages[-1]:
        pages.pop()
    return {"pages": pages, "page_count": len(pages), "automatic_waits": automatic_waits,
            "original_waits": original_waits, "visible_bytes_sha256": project.digest(visible),
            "visible_bytes_preserved": True, "raw_vm_progress": expected_progress,
            "native_unlink_free_verified": True, "steps": model.steps}


def smoke(image, native, long_text):
    source = project.source_bytes()
    require(project.digest(image) == native["output_sha256"], "image/report identity differs")
    require(len(long_text) == 1286 and long_text.endswith(b"[HEND]"), "actual unshortened height fixture differs")
    fixtures = [
        ("actual_long_three_rows", long_text, 144, 12),
        ("actual_long_source_default_extent", long_text, 628, 3),
        ("exact_vertical_edge", b"A\\nB\\nC", 144, 1),
        ("first_overflow_row", b"A\\nB\\nC\\nD", 144, 2),
        ("late_larger_font_moves_whole_row", b"A\\nB\\nC<F 40>D<F 20>", 144, 2),
        ("source_wait_before_automatic_boundary", b"A\\kB\\nC\\nD\\nE", 144, 2),
        ("mixed_cp932", "あいうえお\\nAB\\nかきくけこ\\nCD".encode("cp932"), 144, 2),
    ]
    cases = []
    for name, text, height, expected_pages in fixtures:
        model = Replay(source, text, image=image, patch_report=native,
                       width=984, height=height, dialogue=True)
        scanned = model.run()
        require(bool(scanned["return_control_seen"]) == (expected_pages > 1 or b"\\k" in text),
                name + ": scanner did not block at the required native wait")
        result = paginate(model)
        require(result["page_count"] == expected_pages, name + ": page boundaries differ")
        cases.append({"name": name, **result})
    # A whole-queue native clear must release hidden/unread nodes too and reset
    # the extra context field, not leave stale ownership after cancellation.
    clear = Replay(source, b"A\\nB\\nC\\nD", image=image, patch_report=native,
                   height=144, dialogue=True)
    clear.run()
    allocations = set(clear.queue())
    allocations.update(clear.get(node + 0x30, 4) for node in clear.queue())
    require(clear.get(clear.CTX + 0x550, 4) != 0, "clear fixture has no pending page")
    clear.invoke(0x6DE5C)
    require(not clear.queue() and clear.freed == allocations, "native clear leaked unread allocations")
    require(clear.get(clear.CTX + 0x550, 4) == 0, "native clear retained a dangling boundary")
    # Backlog-like/non-dialogue contexts retain full original queues, with no
    # new user-input protocol. They are deliberately not bounded to one page.
    backlog = Replay(source, b"A\\nB\\nC\\nD", image=image, patch_report=native,
                     height=144, dialogue=False)
    backlog.run()
    require(backlog.get(backlog.CTX + 0x550, 4) == 0,
            "backlog/no-flower context acquired an automatic page wait")
    # Source5CB40 saves the raw checkpoint, then5CB44 zeros live accounting;
    # scanner(R5=1,R8=checkpoint) and6F8F0 reconstruct the consumed prefix.
    restored = Replay(source, b"A\\nB\\nC\\nD\\nE", image=image,
                      patch_report=native, height=144, dialogue=True)
    restored.r[5], restored.r[8] = 1, 12
    restored.run()
    restored.invoke(0x6F8F0)
    remaining = restored.queue()
    require(b"".join(restored.string(restored.get(node + 0x30, 4)) for node in remaining) == b"DE",
            "save reconstruction did not resume on the saved page")
    require(restored.scalar(remaining[0] + 0x68) == 0,
            "save reconstruction retained earlier-page Y")
    progress = restored.get(restored.CTX + 0xF4, 4)
    require(restored.get(progress, 4) == 9,
            "retired restored pages did not retain original raw accounting")
    restored.complete_glyphs(remaining[0])
    require(restored.get(progress, 4) == 12,
            "restored current-page consumption differs from the saved checkpoint")
    restored.invoke(0x6F884)
    restored.complete_glyphs(remaining[1])
    require(restored.get(progress, 4) == 13,
            "unread restored text was lost or counted twice")
    return {"kind": "encoded native pagination/wait/unlink/clear software replay",
            "source_sha256": project.digest(source), "image_sha256": project.digest(image),
            "case_count": len(cases), "cases": cases,
            "whole_queue_clear_frees_unread_spans": True,
            "backlog_protocol_unchanged": True, "runtime_accepted": False,
            "saved_raw_checkpoint_restores_correct_page": True,
            "native_fp_gpu_vm_executed": False, "elf_written": False,
            "limitations": [
                "Finite software PPC/FP replay; no emulator, GPU, native FP or complete VM execution.",
                "Span construction/glyph completion, allocation/free, speed option and flower drawing are synthetic boundaries.",
                "Actual source wait/accounting, doubly linked unlink, prefix retirement and unread-span rebasing instructions execute unchanged or as injected.",
                "Source constructor extent628 is supported; other live option/viewport combinations require attributed runtime evidence.",
                "A single row intrinsically taller than the viewport cannot be made to fit without changing its requested scale; the helper avoids an infinite page loop rather than truncating it."]}
