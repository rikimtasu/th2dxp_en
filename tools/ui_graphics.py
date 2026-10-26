"""Source-bound UI atlas redraws; never packages DATs or changes font assets.

redraw(source_root, output_dir=..., glyphs=...) returns archive-name -> complete TPL bytes
and a JSON-serializable staging report. A private bilingual source/binding
inventory is required at work/ui/graphics-translations.json. The output directory
contains before/after record and individual native-cell previews, not runtime
screenshots. Unresolved native bindings remain explicit; this is not approval.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile

from PIL import Image, ImageFilter

import project
from native_layout_smoke import SourceMetrics

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "work/ui/graphics-translations.json"
FONT = ROOT / "work/assets/fonts/_initial/font.0.R.png"
BC3 = {0x88, 0xA8}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def codec():
    """Load a private vendor instance, extending only BC3 record sizing."""
    path = ROOT / "vendor/TH2DXP_KIT/tpl_image_tool.py"
    spec = importlib.util.spec_from_file_location("_ui_graphics_tpl", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    row, size = module.row_pitch_for, module.expected_payload_size

    def row_pitch(fmt, width, pitch):
        return (pitch or ((width + 3) // 4) * 16) if fmt in BC3 else row(fmt, width, pitch)

    def payload_size(fmt, width, height, pitch):
        if fmt not in BC3:
            return size(fmt, width, height, pitch)
        stride = row_pitch(fmt, width, pitch)
        if width <= 0 or height <= 0 or stride < ((width + 3) // 4) * 16:
            return None
        return stride * ((height + 3) // 4)

    module.row_pitch_for = row_pitch
    module.expected_payload_size = payload_size
    return module


def decode(module, data, record):
    if record.fmt not in BC3:
        return module.decode_record(data, record)
    stride = module.row_pitch_for(record.fmt, record.width, record.pitch)
    tight = ((record.width + 3) // 4) * 16
    payload = data[record.data_offset:record.end_offset]
    blocks = b"".join(payload[y * stride:y * stride + tight]
                      for y in range((record.height + 3) // 4))
    header = (b"DDS " + struct.pack("<7I", 124, 0x81007, record.height,
                                  record.width, len(blocks), 0, 0) + bytes(44)
              + struct.pack("<II4s5I", 32, 4, b"DXT5", 0, 0, 0, 0, 0)
              + struct.pack("<5I", 0x1000, 0, 0, 0, 0))
    with Image.open(io.BytesIO(header + blocks)) as image:
        return image.convert("RGBA")


class LatinAtlas:
    """48-pixel glyph cells with original or explicitly supplied native advances."""
    def __init__(self, source, atlas=None, *, glyphs=None):
        # The source atlas convention uses dilation for small UI labels. Gen's
        # supplied Regular masks already carry the intended stroke; dilating
        # them again closes counters and crowds the smaller footer/map cells.
        provenance = getattr(glyphs, "provenance", {})
        self.default_weight = 1 if provenance.get("face") == "Gen Interface JP Regular" else 3
        if glyphs is not None:
            expected = {chr(byte) for byte in range(0x20, 0x7F)}
            if set(glyphs) != expected:
                raise ValueError("Explicit Latin mapping must contain all 95 printable ASCII glyphs")
            for char, (mask, advance) in glyphs.items():
                if mask.mode != "L" or mask.height != 48 or mask.width < 1:
                    raise ValueError(f"Explicit Latin glyph must be a 48-pixel-high L mask: {char!r}")
                if not isinstance(advance, int) or isinstance(advance, bool) or advance < mask.width:
                    raise ValueError(f"Invalid explicit Latin glyph advance: {char!r}")
            self.glyphs = glyphs
            return
        self.metrics = SourceMetrics(source)
        self.atlas = atlas.convert("L")
        if self.atlas.size != (1536, 1536):
            raise ValueError("Unexpected source font atlas dimensions")
        self.glyphs = {}
        for byte in range(0x20, 0x7F):
            code = struct.unpack_from(">H", source, 0x2514B0 + 2 * (byte - 0x20))[0]
            index = 0
            for first, last in self.metrics.ranges:
                if first <= code <= last:
                    index += code - first
                    break
                index += last - first + 1
            else:
                raise ValueError(f"Missing original Latin glyph {byte:#x}")
            if index >= 1024:
                raise ValueError(f"Latin glyph outside font page R: {byte:#x}")
            left, width = self.metrics.main_pair(byte)
            x, y = index % 32 * 48, index // 32 * 48
            if left + width > 48:
                raise ValueError(f"Invalid original glyph bearing: {byte:#x}")
            self.glyphs[chr(byte)] = (self.atlas.crop((x + left, y, x + left + width, y + 48)),
                                       width + 6)

    def line(self, text, height, max_width, *, weight=None):
        if not text or any(char not in self.glyphs for char in text):
            raise ValueError(f"Not printable Latin in the selected glyph mapping: {text!r}")
        weight = self.default_weight if weight is None else weight
        width = sum(self.glyphs[char][1] for char in text)
        image = Image.new("L", (max(1, width), 48))
        x = 0
        for char in text:
            glyph, advance = self.glyphs[char]
            image.paste(glyph, (x, 0))
            x += advance
        if weight > 1:
            image = image.filter(ImageFilter.MaxFilter(weight))
        box = image.getbbox()
        if box is None:
            raise ValueError("Whitespace-only graphic translation")
        image = image.crop(box)
        # One font scale for every glyph, including punctuation and descenders.
        # Never stretch a hyphen to the height of a capital or squash a word.
        size = (max(1, round(image.width * height / 48)),
                max(1, round(image.height * height / 48)))
        if size[0] > max_width:
            raise ValueError(f"Uncompressed UI text exceeds its cell: {text!r}")
        return image.resize(size, Image.Resampling.LANCZOS)

    def mask(self, text, size, *, height=None, rotate=False, weight=None, minimum=14, padding=1):
        width, tall = size
        weight = self.default_weight if weight is None else weight
        if rotate:
            result = self.mask(text, (tall, width), height=height, weight=weight,
                               minimum=minimum, padding=padding)
            rotated = result.rotate(90, expand=True)
            rotated.info["ui_layout"] = dict(result.info["ui_layout"], rotated=True)
            return rotated
        for pixels in range(max(minimum, height or tall), minimum - 1, -1):
            lines = []
            fits = True
            for paragraph in text.split("\n"):
                current = ""
                for word in paragraph.split(" "):
                    candidate = word if not current else current + " " + word
                    try:
                        self.line(candidate, pixels, max(1, width - 2 * padding), weight=weight)
                    except ValueError:
                        if not current:
                            fits = False
                            break
                        lines.append(current)
                        current = word
                        try:
                            self.line(word, pixels, max(1, width - 2 * padding), weight=weight)
                        except ValueError:
                            fits = False
                            break
                    else:
                        current = candidate
                if not fits:
                    break
                lines.append(current)
            if not fits:
                continue
            rows = [self.line(line, pixels, max(1, width - 2 * padding), weight=weight) for line in lines]
            total = sum(row.height for row in rows) + 2 * (len(rows) - 1)
            if total > tall - 2 * padding:
                continue
            result = Image.new("L", size)
            y = (tall - total) // 2
            boxes = []
            for row in rows:
                x = (width - row.width) // 2
                result.paste(row, (x, y))
                boxes.append([x, y, row.width, row.height])
                y += row.height + 2
            result.info["ui_layout"] = {"font_pixels": pixels, "lines": lines, "line_boxes": boxes,
                                         "stroke_filter": weight, "padding": padding,
                                         "horizontal_compression": False, "rotated": False}
            return result
        raise ValueError(f"Readable complete UI text needs a larger native cell: {text!r}, {size}")


def editorial_labels():
    """English editorial data only; source Japanese remains in the private inventory."""
    labels = []

    def add(key, asset, record, rect, english, **style):
        labels.append(dict(id=key, asset=asset, record=record, rect=list(rect),
                           english=english, **style))

    title = [(0, "new-game", "New Game"), (1, "continue", "Continue"),
             (2, "options", "Options"), (3, "extras", "Extras"),
             (6, "ikuno", "Ikuno's Story"),
             (7, "konomi-tamaki", "Konomi & Tamaki's Story"),
             (8, "visual", "Visual Mode"), (9, "music", "Music Mode"),
             (10, "install", "Data Install")]
    for row, key, text in title:
        for state in range(2):
            x = state * 320
            end = 250 if row == 6 else 258 if row == 7 else 272
            add(f"title.{key}.{state}", "sys/title.tpl", 0,
                (x + 42, row * 32 + 2, x + end, row * 32 + 30), text,
                background="title-bar", sample_x=x + 39,
                color=[255, 88, 149, 255] if state else [255, 255, 255, 255], height=23)

    for channel in "RGBA":
        for key, rect, text, height in [("yes", (40, 7, 86, 31), "Yes", 20),
                                        ("no", (118, 7, 174, 31), "No", 20),
                                        ("confirm", (42, 55, 94, 83), "OK", 24),
                                        ("next", (145, 57, 190, 78), "Next", 18)]:
            # Next's former erase rectangle crossed the rounded right/bottom
            # frame. Restrict painting to the source's empty lettering interior.
            add(f"general.button.{key}.{channel}", "_initial/general.tpl", 1, rect, text,
                channel=channel, background=221 if channel == "A" else 0, height=height,
                padding=3 if key == "next" else 1)

    add("general.options", "_initial/general.tpl", 43, (130, 0, 330, 54), "Options", height=32)
    for key, x, text in [("dark", 0, "-"), ("bright", 32, "+"),
                         ("small", 64, "-"), ("large", 96, "+"),
                         ("slow", 384, "-"), ("fast", 416, "+")]:
        # Full option names/help carry the meaning; conventional decrement/
        # increment symbols remain legible in the original 32-pixel buttons.
        add("general.option-arrow." + key, "_initial/general.tpl", 43,
            (x, 192, x + 32, 240), text, background="dark-ink", height=24)
    add("general.story.ikuno", "_initial/general.tpl", 44, (164, 109, 384, 141), "Ikuno's Story", height=27)
    add("general.story.konomi-tamaki", "_initial/general.tpl", 44, (84, 157, 384, 189),
        "Konomi & Tamaki's Story", height=27)
    add("general.save", "_initial/general.tpl", 46, (92, 0, 330, 47), "Save Data", height=33)
    add("general.load", "_initial/general.tpl", 46, (92, 72, 330, 119), "Load Data", height=33)
    add("general.saved-at", "_initial/general.tpl", 46, (43, 240, 172, 256), "Saved on", height=16,
        color=[220, 220, 220, 255])
    add("general.save.story.konomi-tamaki", "_initial/general.tpl", 46, (280, 208, 464, 240),
        "Konomi & Tamaki's Story", height=18, color=[64, 64, 64, 255],
        background=[255, 250, 240, 255])
    add("general.save.story.ikuno", "_initial/general.tpl", 46, (280, 240, 464, 272),
        "Ikuno's Story", height=18, color=[64, 64, 64, 255],
        background=[250, 255, 240, 255])
    # The native date renderer addresses the original month/day cells separately.
    for key, rect in [("month", (140, 256, 154, 272)), ("day", (154, 256, 168, 272)),
                       ("large-month", (260, 272, 278, 296)), ("large-day", (278, 272, 296, 296))]:
        # Native month/day ordering is retained: MM/DD followed by whitespace,
        # not a spurious second slash between the date and the clock/time.
        text = " " if key.endswith("day") else "/"
        add("general.date." + key, "_initial/general.tpl", 46, rect, text, height=12,
            date_separator=True,
            color=[255, 255, 255, 255] if key.startswith("large-") else [128, 128, 128, 255])

    legends = [("confirm", "OK"), ("play", "Play"), ("back", "Back"), ("cursor", "Move cursor"),
               ("select", "Select"), ("stop", "Stop"), ("delete", "Delete character"),
               ("map", "Change map"), ("convert", "Convert"), ("options", "Options"),
               ("cancel", "Cancel"), ("item", "Change / select item"), ("page", "Change page")]
    cells = project.load(MANIFEST)["readable_layout"]["legend_cells"]
    for key, text in legends:
        add("general.legend." + key, "_initial/general.tpl", 49,
            cells["general.legend." + key], text, height=20)
    for row, text in enumerate(["Please select a destination.", "Please select where to save your data.",
                                "Please select the data to load."]):
        add(f"general.prompt.{row}", "_initial/general.tpl", 50,
            (0, row * 32, 320 if row == 0 else 416, row * 32 + 32), text, height=22)

    for row, (key, text) in enumerate([("family", "Enter Family Name"),
                                      ("family-reading", "Enter Family Name Reading"),
                                      ("first", "Enter First Name"),
                                      ("first-reading", "Enter First Name Reading"),
                                      ("nickname", "Enter Nickname")]):
        add("nameentry." + key, "sys/nameentry.tpl", 1,
            (120, row * 70, 404, row * 70 + 47), text, height=31)
    for key, rect, text in [("kana", (43, 5, 203, 35), "Kana"),
                            ("latin", (43, 45, 203, 75), "Alphanumeric"),
                            ("delete", (270, 45, 350, 75), "Delete"),
                            ("convert", (270, 85, 350, 115), "Convert"),
                            ("history", (270, 125, 350, 155), "History"),
                            ("confirm", (270, 165, 350, 195), "Confirm")]:
        add("nameentry.button." + key, "sys/nameentry.tpl", 2, rect, text, height=24,
            background="sample", sample=[rect[0], rect[1]])

    for key, rect, text in [("music", (65, 0, 388, 46), "Music Mode"),
                            ("visual", (65, 80, 388, 126), "Visual Mode"),
                            ("ikuno", (162, 269, 384, 301), "Ikuno's Story"),
                            ("konomi-tamaki", (84, 317, 384, 349), "Konomi & Tamaki's Story"),
                            ("vocal", (384, 384, 480, 406), "Vocals"),
                            ("compose", (384, 428, 480, 450), "Composer"),
                            ("words", (384, 406, 480, 428), "Lyrics"),
                            ("arrange", (384, 450, 480, 472), "Arranger")]:
        add("extra." + key, "sys/extra.tpl", 0, rect, text,
            height=32 if key in ("music", "visual") else (25 if "ikuno" == key or "konomi" in key else 16))

    holidays = ["Graduation Ceremony", "Vernal Equinox Day", "Term Closing Ceremony", "Spring Break",
                "Term Opening Ceremony", "Showa Day", "Constitution Memorial Day", "Greenery Day", "Children's Day"]
    for row, text in enumerate(holidays):
        add(f"calendar.holiday.{row}", "cal/calender.tpl", 1,
            (281, row * 48, 512, row * 48 + 48), text, height=30)
        add(f"calendar.holiday.vertical.{row}", "cal/calender.tpl", 1,
            (row * 28, 416, row * 28 + 28, 512), text, height=14, minimum=12, rotate=True)
    for row, initial in enumerate("SMTWTFS"):
        add(f"calendar.weekday.{row}", "cal/calender.tpl", 2,
            (224, row * 48 + 12, 256, row * 48 + 44), initial, height=22)

    places = [
        ["Home", "Shopping District", "Game Center", "Park", "Konomi's Middle School", "Hillside Road", "School Gate", "Schoolyard", "Bicycle Parking"],
        ["Backyard", "Shoe Lockers", "Gymnasium", "Book Stacks", "Library", "Audiovisual Room", "1F Corridor", "2F Corridor", "1F Classroom"],
        ["2F Classroom", "3F Corridor", "3F Classroom", "Student Council Room", "Back Gate", "Terajo Girls' School", "Arcade", "Monjayaki Restaurant", "Broadcasting Room"],
    ]
    for variant in range(5):
        for column, rows in enumerate(places):
            for row, text in enumerate(rows):
                add(f"map.{variant}.{column}.{row}", f"mp/map{variant}.tpl", 5,
                    (column * 170, row * 52, min(512, (column + 1) * 170), row * 52 + 52), text,
                    height=24)
    return labels


def background(image, label):
    box = label["rect"]
    value = label.get("background", 0 if image.mode == "L" else [0, 0] if image.mode == "LA" else [255, 255, 255, 0])
    if value == "sample":
        value = image.getpixel(tuple(label["sample"]))
    if value in ("title-bar", "dark-ink"):
        # Retain the actual bar/triangle pixels and faded watermarks. Only the
        # old bright lettering and its immediate antialias fringe are restored.
        patch = image.crop(box)
        clean = Image.new(image.mode, patch.size, (0, 0, 0, 255))
        ink = Image.new("L", patch.size)
        for y in range(patch.height):
            if value == "title-bar":
                clean.paste(image.getpixel((label["sample_x"], box[1] + y)),
                            (0, y, patch.width, y + 1))
            for x in range(patch.width):
                r, g, b, a = patch.getpixel((x, y))
                if a > 210 and max(r, g, b) > 160:
                    ink.putpixel((x, y), 255)
        patch.paste(clean, (0, 0), ink.filter(ImageFilter.MaxFilter(3)))
        return patch
    if isinstance(value, list):
        value = tuple(value)
    return Image.new(image.mode, (box[2] - box[0], box[3] - box[1]), value)


def paint(image, label, font):
    left, top, right, bottom = label["rect"]
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError(f"Out-of-record label rectangle: {label['id']}")
    patch = background(image, label)
    if label.get("date_separator") and label["english"].isspace():
        mask = Image.new("L", patch.size)
    else:
        mask = font.mask(label["english"], patch.size, height=label.get("height"),
                         rotate=label.get("rotate", False), weight=label.get("weight"),
                         minimum=label.get("minimum", 14), padding=label.get("padding", 1))
    if image.mode == "L":
        patch.paste(255, (0, 0, patch.width, patch.height), mask)
    else:
        # Coverage is alpha, not premultiplied luma/RGB. In particular the G8B8
        # label sheets need white L under partially transparent edge texels.
        color = tuple(label.get("color", [255, 255, 255, 255]))
        foreground = Image.new("RGBA", patch.size, color)
        foreground.putalpha(mask if color[3] == 255 else mask.point(
            lambda value: (value * color[3] + 127) // 255))
        patch = Image.alpha_composite(patch.convert("RGBA"), foreground).convert(image.mode)
    image.paste(patch, (left, top))
    return mask.info.get("ui_layout", {"date_separator": True, "horizontal_compression": False})


def pack_record(module, original, record, edited, channels, directory):
    payload = original[record.data_offset:record.end_offset]
    if record.fmt in BC3:
        raise ValueError("BC3 artwork must remain byte-identical; no BC3 label encoder")
    if record.fmt in module.FMT_DXT1:
        # Encode only changed 4x4 blocks, not an entire otherwise untouched sheet.
        before = decode(module, original, record)
        out = bytearray(payload)
        changed_blocks = []
        stride = module.row_pitch_for(record.fmt, record.width, record.pitch)
        for by in range((record.height + 3) // 4):
            for bx in range((record.width + 3) // 4):
                box = (bx * 4, by * 4, min(record.width, bx * 4 + 4), min(record.height, by * 4 + 4))
                old, new = before.crop(box), edited.crop(box)
                if old.tobytes() == new.tobytes():
                    continue
                if new.size != (4, 4):
                    padded = Image.new("RGBA", (4, 4))
                    for y in range(4):
                        for x in range(4):
                            padded.putpixel((x, y), new.getpixel((min(x, new.width - 1), min(y, new.height - 1))))
                    new = padded
                encoded = module.encode_dxt1_image(new, 4, 4, 0)
                offset = by * stride + bx * 8
                out[offset:offset + 8] = encoded
                changed_blocks.append([bx, by])
        return bytes(out), changed_blocks
    if record.fmt in module.FMT_A4R4G4B4:
        paths = {}
        for channel, image in channels.items():
            path = directory / f"{channel}.png"
            image.save(path)
            paths[channel] = path
        return module.pack_a4r4g4b4(payload, record, paths), []
    path = directory / "record.png"
    edited.save(path)
    if record.fmt in module.FMT_ARGB8888:
        return module.pack_argb8888(payload, record, path), []
    if record.fmt in module.FMT_L8:
        return module.pack_l8(payload, record, path), []
    if record.fmt in module.FMT_G8B8:
        return module.pack_g8b8(payload, record, path), []
    raise ValueError(f"Unsupported edited format: {record.fmt:#x}")


def preview(image):
    if image.mode == "L":
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    base = Image.new("RGBA", image.size, (45, 57, 75, 255))
    base.alpha_composite(rgba)
    return base.convert("RGB")


def redraw(source_root: Path, *, output_dir: Path | None = None, glyphs=None):
    """Return TPL replacements/report using original or explicit native glyph masks."""
    source_root = Path(source_root)
    output_dir = Path(output_dir) if output_dir else ROOT / "work/ui/graphics-preview"
    manifest_bytes = MANIFEST.read_bytes()
    inventory = json.loads(manifest_bytes)
    source = project.source_bytes()
    if digest(source) != inventory["native_source_sha256"]:
        raise ValueError("Graphic manifest native source mismatch")
    atlas_bytes = FONT.read_bytes()
    if digest(atlas_bytes) != inventory["font_sha256"]:
        raise ValueError("Original font atlas hash mismatch")
    font = LatinAtlas(source, Image.open(io.BytesIO(atlas_bytes)) if glyphs is None else None, glyphs=glyphs)
    if glyphs is None:
        font_method = "original font.0.R glyphs; SourceMetrics.main_pair bearings and widths; native +6 advance"
        font_provenance = {"method": font_method, "font_sha256": digest(atlas_bytes)}
    else:
        font_provenance = dict(getattr(glyphs, "provenance", {}))
        font_method = font_provenance.get("method", "explicit 48-pixel Latin glyph mapping; supplied exact native advances")
        font_provenance["method"] = font_method
        if font_provenance.get("face"):
            font_method = f"{font_provenance['face']}: {font_method}"
    glyph_hash = hashlib.sha256()
    for char, (mask, advance) in sorted(font.glyphs.items()):
        glyph_hash.update(struct.pack("<4I", ord(char), mask.width, mask.height, advance))
        glyph_hash.update(mask.tobytes())
    module = codec()
    if digest((ROOT / "vendor/TH2DXP_KIT/tpl_image_tool.py").read_bytes()) != inventory["tpl_tool_sha256"]:
        raise ValueError("Pinned TPL codec hash mismatch")
    labels = editorial_labels()
    originals = inventory["labels"]
    if set(originals) != {label["id"] for label in labels}:
        raise ValueError("Private bilingual inventory does not match editorial labels")
    grouped = defaultdict(lambda: defaultdict(list))
    for label in labels:
        if not originals[label["id"]]["original_japanese"]:
            raise ValueError(f"Missing reviewed source label: {label['id']}")
        binding = originals[label["id"]]["native_binding"]
        crop = binding.get("staged_source_crop", binding["native_source_crop"])
        left, top, right, bottom = label["rect"]
        if not (crop[0] <= left < right <= crop[2] and crop[1] <= top < bottom <= crop[3]):
            raise ValueError(f"Graphic label exceeds its native source crop: {label['id']}")
        grouped[label["asset"]][label["record"]].append(label)
    output_dir.mkdir(parents=True, exist_ok=True)
    replacements, records_report, label_report, layouts = {}, [], [], {}
    for name, expected in inventory["assets"].items():
        data = (source_root / name).read_bytes()
        if digest(data) != expected["sha256"]:
            raise ValueError(f"Source TPL hash mismatch: {name}")
        records = module.parse_records(data)
        if name not in grouped:
            continue
        result = bytearray(data)
        for index, record_labels in sorted(grouped[name].items()):
            record = records[index]
            image = decode(module, data, record)
            channels = module.extract_a4_channels(data, record) if record.fmt in module.FMT_A4R4G4B4 else {}
            before_channels = {key: value.copy() for key, value in channels.items()}
            before_image = image.copy()
            # Repacked caption cells have native source-table/code changes in
            # the paired ELF. Clear every old cell before painting any new cell.
            cleared = set()
            for label in record_labels:
                binding = originals[label["id"]]["native_binding"]
                if "staged_source_crop" in binding:
                    box = tuple(binding["native_source_crop"])
                    if box not in cleared:
                        image.paste(0, box)
                        cleared.add(box)
            for label in record_labels:
                target = channels[label["channel"]] if "channel" in label else image
                layouts[label["id"]] = paint(target, label, font)
            # Vendor packers retain original row padding. Only independently edited
            # A4 planes are changed; other planes are passed back byte-for-byte.
            with tempfile.TemporaryDirectory(prefix="ui-record-") as temporary:
                payload, blocks = pack_record(module, data, record, image, channels, Path(temporary))
            if len(payload) != record.payload_size:
                raise ValueError("Texture encoder changed the source payload size")
            result[record.data_offset:record.end_offset] = payload
            stem = name.replace("/", "_").replace(".tpl", "") + f"-{index}"
            final_image = decode(module, bytes(result), record)
            channel_reports = []
            for channel in (sorted(channels) if channels else [None]):
                old = before_channels[channel] if channel else before_image
                new = module.extract_a4_channels(bytes(result), record)[channel] if channel else final_image
                suffix = "-" + channel if channel else ""
                old_path, new_path = output_dir / f"{stem}{suffix}-before.png", output_dir / f"{stem}{suffix}-after.png"
                preview(old).save(old_path)
                preview(new).save(new_path)
                channel_reports.append(dict(channel=channel, before=str(old_path), after=str(new_path)))
            for label in record_labels:
                channel = label.get("channel")
                old = before_channels[channel] if channel else before_image
                new = module.extract_a4_channels(bytes(result), record)[channel] if channel else final_image
                binding = originals[label["id"]]["native_binding"]
                source_crop = binding["native_source_crop"]
                staged_crop = binding.get("staged_source_crop", source_crop)
                old_crop, new_crop = preview(old.crop(source_crop)), preview(new.crop(staged_crop))
                cell = Image.new("RGB", (max(old_crop.width, new_crop.width),
                                        old_crop.height + new_crop.height + 4), (32, 32, 32))
                cell.paste(old_crop, (0, 0)); cell.paste(new_crop, (0, old_crop.height + 4))
                cell_path = output_dir / (label["id"] + ".png")
                cell.save(cell_path)
                entry = dict(originals[label["id"]])
                entry.update(label)
                entry.update(source_sha256=expected["sha256"],
                             source_record_offset=record.record_offset, source_fmt=record.fmt,
                             preview=str(cell_path), preview_source_rect=source_crop,
                             preview_staged_rect=staged_crop, rendered_layout=layouts[label["id"]])
                label_report.append(entry)
            records_report.append(dict(asset=name, record=index, width=record.width, height=record.height,
                                       fmt=record.fmt, payload_offset=record.data_offset,
                                       payload_size=record.payload_size, preview=channel_reports,
                                       changed_bc1_blocks=blocks, original_payload_sha256=digest(data[record.data_offset:record.end_offset]),
                                       replacement_payload_sha256=digest(payload)))
        if len(result) != len(data):
            raise ValueError("TPL output changed source file size")
        replacements[name] = bytes(result)
    report = dict(schema_version=2, purpose="offline-ui-graphics-staging-only", runtime_approval=False,
                  manifest_sha256=digest(manifest_bytes), native_source_sha256=digest(source),
                  font_sha256=font_provenance.get("font_sha256"),
                  source_font_atlas_sha256=digest(atlas_bytes),
                  font_assets_modified=False if glyphs is None else None,
                  font_asset_scope="UI TPL replacements only; selected native font packaging is external",
                  font_method=font_method, selected_font=font_provenance,
                  selected_glyphs_sha256=glyph_hash.hexdigest(),
                  default_stroke_filter=font.default_weight,
                  output_dir=str(output_dir), labels=label_report, records=records_report,
                  inventory=inventory["assets"], unresolved_bindings=inventory["unresolved_bindings"],
                  native_binding_evidence=inventory["native_binding_evidence"],
                  retained_reviewed_source_labels=inventory["retained_reviewed_source_labels"],
                  native_qa_constraints=inventory["native_qa_constraints"],
                  native_save_date_review=inventory["native_save_date_review"],
                  readable_layout=inventory["readable_layout"],
                  readability=f"uniform {'original' if glyphs is None else 'selected'}-font scaling; whole-word wrapping; no horizontal condensation; native footer/credit cells repacked with paired ELF geometry",
                  replacement_hashes={name: digest(data) for name, data in replacements.items()},
                  preservation="original templates; exact record payload splice; untouched records/gaps/header/padding retained; BC1 only changed blocks; BC3 never reencoded")
    return replacements, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output", type=Path, help="separate staging destination, never a game installation")
    args = parser.parse_args()
    replacements, report = redraw(args.source_root, output_dir=args.output / "previews")
    for name, data in replacements.items():
        path = args.output / "tpl" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (args.output / "graphics-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
