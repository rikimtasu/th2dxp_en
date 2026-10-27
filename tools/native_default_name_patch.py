"""Rename the native default player name to Kouno Takaaki, in place.

The game stores six null-terminated default-name strings in one read-only
window (``0xF73D8..0xF7400``) — given name, its kana reading, family name, its
kana reading, a short nickname and the katakana nickname. Inventoried code
references materialise those addresses with ``lis rX,0x10`` plus
``addic/addi rY,rX,0x73xx``; a dozen further sites copy an already-loaded
register with ``ori rZ,rY,0``.

The six Latin replacements need 37 of the 40 available bytes, so they stay in
the window and every reference is repointed by rewriting only the low 16-bit
immediate of its load instruction. No helper is injected, no pointer table
moves, and no other byte of the executable changes. The initialisation code
copies with fixed ``strncpy`` lengths of 13 (five 16-byte fields) and 32 (the
sixth); those lengths are read back out of the executable, so a longer name is
rejected instead of silently truncated.

This is a language correction, not new gameplay: a save that still holds the
Japanese default compares unequal at ``0x8631C``/``0x8AB58`` and simply reads as
a custom name, the same path a player-typed name takes.
"""
from __future__ import annotations

import json

import native_layout_patch
import native_ui_patch
import project

GIVEN, SURNAME, NICKNAME = "Takaaki", "Kouno", "Taka"
#: ``(file_offset, source text, replacement)`` in native slot order.
SLOTS = ((0xF73D8, "貴明", GIVEN),
         (0xF73DD, "たかあき", GIVEN),
         (0xF73E6, "河野", SURNAME),
         (0xF73EB, "こうの", SURNAME),
         (0xF73F2, "たか", NICKNAME),
         (0xF73F7, "タカ", NICKNAME))
WINDOW_END = 0xF7400
LIS, ADDIC, ADDI, ORI = 15, 12, 14, 24
LIS_RIGHT = 0x100000
TEXT_BASE = 0x10000  # read-only segment file offset -> virtual address
LOW_HALVES = {(offset + TEXT_BASE) - LIS_RIGHT: offset for offset, _, _ in SLOTS}


def _require(condition, message):
    if not condition:
        raise ValueError("Default name: " + message)


def _word(data, offset):
    return int.from_bytes(data[offset:offset + 4], "big")


def _signed(value):
    return value - 0x10000 if value & 0x8000 else value


def _lookback(source, offset, register):
    """Return the ``lis`` seed that set ``register`` before ``offset``, or None."""
    for back in range(1, 9):
        at = offset - 4 * back
        if at < 0x230:
            return None
        word = _word(source, at)
        if (word >> 21) & 31 != register:
            continue
        opcode = word >> 26
        if opcode == LIS and (word & 0xFFFF) == 0x10:
            return word
        if opcode in (LIS, ADDIC, ADDI, ORI):
            return None  # register rewritten without the reviewed high half
    return None


def sites(source):
    """Every instruction that materialises one of the six window addresses.

    The scan is deliberately raw and complete: it walks every aligned word of
    the executable, keeps only ``addic``/``addi`` whose immediate is a reviewed
    low half, and then requires a reviewed ``lis rX,0x10`` seed for that same
    register. Anything else is not an address of this window.
    """
    found = {}
    for at in range(0x230, len(source) - 4, 4):
        word = _word(source, at)
        if word >> 26 not in (ADDIC, ADDI):
            continue
        target = word & 0xFFFF
        if target not in LOW_HALVES:
            continue
        register = (word >> 16) & 31
        if (word >> 21) & 31 != register or _lookback(source, at, register) is None:
            continue
        if LIS_RIGHT + _signed(target) != LOW_HALVES[target] + TEXT_BASE:
            continue
        found[at] = {"register": register, "slot": target}
    return found


def copy_limits(source, immediate_sites):
    """Read the ``li r5,<n>`` length that follows each native name copy."""
    limits = {}
    for at, info in immediate_sites.items():
        for step in (1, 2, 3):
            word = _word(source, at + 4 * step)
            if word >> 26 in (ADDIC, ADDI) and (word >> 21) & 31 == 5 and (word >> 16) & 31 == 0:
                limits[info["slot"]] = word & 0xFFFF
                break
    return limits


def _plan(source, inventory):
    """Build the default-name manifest from bytes plus a reviewed text inventory.

    The immutable-source and inventory-pin checks live in :func:`substitute`;
    keeping them out of here lets the regression tests drive the same layout,
    site discovery and copy-length logic with a synthetic image.
    """
    records = {row["offset"]: row for row in inventory["records"]}
    start = SLOTS[0][0]
    before = source[start:WINDOW_END]
    cursor, after, slots, moved = start, bytearray(), [], {}
    for offset, text, replacement in SLOTS:
        expected = text.encode("cp932")
        row = records.get(offset)
        _require(row is not None and row["original"] == text,
                 f"inventory lost the native string at {offset:#x}")
        _require(source[offset:offset + len(expected) + 1] == expected + b"\0",
                 f"native string at {offset:#x} differs from its immutable bytes")
        encoded = replacement.encode("cp932")
        _require(encoded.isascii() and encoded.decode("cp932") == replacement,
                 f"{replacement!r} is not plain CP932 ASCII")
        moved[offset] = start + len(after)
        slots.append({"file_offset": hex(offset), "window_file_offset": hex(moved[offset]),
                      "text": replacement, "source_text": text,
                      "bytes": (encoded + b"\0").hex(), "length": len(encoded)})
        after.extend(encoded + b"\0")
        cursor += len(encoded) + 1
    _require(cursor <= WINDOW_END, "renamed strings no longer fit the native 40-byte window")
    source_end = SLOTS[-1][0] + len(SLOTS[-1][1].encode("cp932")) + 1
    _require(before[source_end - start:] == b"\0" * (WINDOW_END - source_end),
             "native name window carries data after the six strings")
    written = len(after)
    after.extend(b"\0" * (len(before) - len(after)))

    immediate = sites(source)
    listed = {reference["site"] - 0x10000 for offset in LOW_HALVES.values()
              for reference in records[offset]["code_references"]}
    _require(set(immediate) <= listed, "an unreviewed instruction loads a default-name address")
    expected_sites = {at for at in listed if _word(source, at) >> 26 in (ADDIC, ADDI)}
    _require(set(immediate) == expected_sites,
             "inventory lists a default-name load that is not a plain addic/addi immediate")

    limits = copy_limits(source, immediate)
    _require(len(limits) == len(SLOTS), "cannot read the six native copy lengths")
    for (offset, _, replacement), slot in zip(SLOTS, slots):
        _require(slot["length"] + 1 <= limits[(offset + TEXT_BASE) - LIS_RIGHT],
                 f"{replacement!r} exceeds the native "
                 f"{limits[(offset + TEXT_BASE) - LIS_RIGHT]}-byte copy at {offset:#x}")

    patches = []
    for at in sorted(immediate):
        info = immediate[at]
        word = _word(source, at)
        target = moved[LOW_HALVES[info["slot"]]]
        patches.append({"file_offset": hex(at), "virtual_address": hex(at + 0x10000),
                        "source_before": source[at:at + 4].hex(),
                        "after": ((word & 0xFFFF0000) | (target & 0xFFFF)).to_bytes(4, "big").hex(),
                        "register": info["register"],
                        "source_slot_offset": hex(LOW_HALVES[info["slot"]]),
                        "target_slot_offset": hex(target),
                        "purpose": "default player name relocation; low 16-bit immediate only"})
    _require(len(patches) == len(immediate), "immediate patch listing is incomplete")
    return {
        "source_sha256": project.digest(source),
        "inventory_sha256": project.digest(
            json.dumps(inventory, ensure_ascii=False, sort_keys=True).encode("utf-8")),
        "names": {"given": GIVEN, "family": SURNAME, "nickname": NICKNAME,
                  "display": f"{SURNAME} {GIVEN}", "order": "family name, given name"},
        "window": {"file_offset": hex(start), "file_end": hex(WINDOW_END),
                   "source_before": before.hex(), "after": after.hex(),
                   "source_size": len(before), "bytes_written": written,
                   "strncpy_limits": {hex(key): value for key, value in limits.items()}},
        "slots": slots, "patches": patches,
        "reference_sites": len(patches),
        "method": "in-place repack of the native 40-byte window; only low 16-bit "
                  "immediates of reviewed lis/addic|addi loads change",
        "helper_injected": False,
        "runtime_accepted": False,
    }


def substitute(source=None, *, inventory=None):
    """Return the default-name manifest without writing anything."""
    source = source if source is not None else project.source_bytes()
    _require(project.digest(source) == native_layout_patch.SOURCE_SHA256,
             "requires the immutable reviewed executable")
    if inventory is None:
        inventory = project.load(native_ui_patch.BINDINGS)
        _require(project.digest(native_ui_patch.BINDINGS.read_bytes()) == native_ui_patch.BINDINGS_SHA256,
                 "native text inventory differs from its reviewed pin")
    return _plan(source, inventory)


def apply(image, manifest=None, *, source=None):
    """Write the renamed window and repointed immediates into an assembled image."""
    source = source if source is not None else project.source_bytes()
    if manifest is None:
        manifest = substitute(source)
    _require(manifest["source_sha256"] == project.digest(source),
             "manifest identifies another source executable")
    result = bytearray(image)
    start = int(manifest["window"]["file_offset"], 0)
    before = bytes.fromhex(manifest["window"]["source_before"])
    _require(result[start:start + len(before)] == before,
             "native name window differs from the immutable original")
    result[start:start + len(before)] = bytes.fromhex(manifest["window"]["after"])
    for patch in manifest["patches"]:
        at = int(patch["file_offset"], 0)
        _require(result[at:at + 4] == bytes.fromhex(patch["source_before"]),
                 f"name load at {patch['virtual_address']} differs from the immutable original")
        result[at:at + 4] = bytes.fromhex(patch["after"])
    return bytes(result), manifest


def verify(image, manifest, *, source=None):
    """Prove the image carries exactly this name window and every repointed load."""
    source = source if source is not None else project.source_bytes()
    _require(manifest["source_sha256"] == project.digest(source),
             "manifest identifies another source executable")
    start = int(manifest["window"]["file_offset"], 0)
    expected = bytes.fromhex(manifest["window"]["after"])
    _require(image[start:start + len(expected)] == expected,
             "renamed name window is absent from the image")
    for slot in manifest["slots"]:
        at = int(slot["window_file_offset"], 0)
        encoded = slot["text"].encode("cp932") + b"\0"
        _require(image[at:at + len(encoded)] == encoded,
                 f"default name {slot['text']!r} is not at its reviewed offset")
    for patch in manifest["patches"]:
        at = int(patch["file_offset"], 0)
        _require(image[at:at + 4] == bytes.fromhex(patch["after"]),
                 f"name load at {patch['virtual_address']} was not repointed")
        target = int(patch["target_slot_offset"], 0)
        _require((_word(image, at) & 0xFFFF) == (target & 0xFFFF),
                 f"name load at {patch['virtual_address']} points elsewhere")
    _require(project.digest(image) != project.digest(source), "image is unchanged")
    return {"window_file_offset": manifest["window"]["file_offset"],
            "slots": [slot["text"] for slot in manifest["slots"]],
            "reference_sites": len(manifest["patches"]),
            "display": manifest["names"]["display"],
            "runtime_accepted": False}
