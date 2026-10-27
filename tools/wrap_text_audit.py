"""Read-only candidate scan for base-story English spacing; not a visual test."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

import project


MISSING_SPACE = re.compile(r"(?<!\.)[.!?](?=[A-Z])")
MULTIPLE_SPACES = re.compile(r" {2,}")


def scan_unit(filename, unit_index, items):
    """Scan contiguous translated text runs; native controls delimit runs."""
    findings = []
    run = []

    def flush():
        if not run:
            return
        text = "".join(part for _, part in run)
        offsets = []
        position = 0
        for item_index, part in run:
            offsets.append((position, position + len(part), item_index))
            position += len(part)
        for category, pattern in (("sentence_spacing", MISSING_SPACE),
                                  ("multiple_ascii_spaces", MULTIPLE_SPACES)):
            for match in pattern.finditer(text):
                left = next(index for start, end, index in offsets if start <= match.start() < end)
                right_pos = match.end() if category == "sentence_spacing" else match.end() - 1
                right = next(index for start, end, index in offsets if start <= right_pos < end)
                findings.append({
                    "category": category, "file": filename, "unit": unit_index,
                    "left_item": left, "right_item": right,
                    "across_fragments": left != right,
                    "context": text[max(0, match.start() - 45):match.end() + 45],
                })
        for left_offset, right_offset in zip(offsets, offsets[1:]):
            _, boundary, left_index = left_offset
            start, end, right_index = right_offset
            if (boundary == start and 0 < boundary < len(text) and start < end
                    and text[boundary - 1].isascii() and text[boundary - 1].isalpha()
                    and text[boundary].isascii() and text[boundary].isalpha()):
                findings.append({"category": "joined_word_boundary", "file": filename,
                                 "unit": unit_index, "left_item": left_index,
                                 "right_item": right_index, "across_fragments": True,
                                 "context": text[max(0, boundary - 45):boundary + 45]})
        run.clear()

    for index, item in enumerate(items):
        if item.get("kind") != "text":
            flush()
            continue
        text = item.get("translated_text")
        if not isinstance(text, str):
            raise ValueError(f"Missing translated text: {filename}:{unit_index}:{index}")
        run.append((index, text))
        if item.get("control_suffix") or "\\" in text or "<" in text:
            flush()
    flush()
    return findings


def audit(membership, inventory, script_dir):
    scenarios = membership["scenarios"]
    names = [row["script"] for row in scenarios if row["status"] in ("base_game", "shared")]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate base-story scenario in membership inventory")
    inventory_rows = {row["script"]: row for row in inventory["scenarios"]}
    if len(inventory_rows) != len(inventory["scenarios"]):
        raise ValueError("Duplicate scenario in baseline inventory")
    counts = Counter()
    findings = []
    for name in names:
        path = script_dir / name
        if not path.is_file():
            row = inventory_rows.get(name)
            if not row or row["editable_text_record_count"] != 0:
                raise ValueError(f"Missing base-story script with text: {path}")
            counts["scenarios_without_message_script"] += 1
            continue
        units = project.load(path)
        counts["scripts"] += 1
        for unit_index, unit in enumerate(units):
            items = unit["items"]
            for item in items:
                if item.get("kind") == "text":
                    counts["text_items"] += 1
                    if item["translated_text"] != item["original_text"]:
                        counts["changed_text_items"] += 1
            findings.extend(scan_unit(name, unit_index, items))
    counts.update(row["category"] for row in findings)
    return {"scope": "base_game and shared story ownership, message text only",
            "limitations": ["Candidate matching is not visual word-wrap or translation review.",
                            "Joined-word boundaries often split a single word intentionally; abbreviations may be false positives.",
                            "Choices, route execution, native controls and GPU rendering are not checked."],
            "counts": dict(counts), "candidates": findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError(f"Refusing to overwrite report: {args.output}")
    membership = project.load(project.ROOT / "work/scenes/scenario-membership.json")
    inventory = project.load(project.ROOT / "work/scenes/base-game-inventory.json")
    result = audit(membership, inventory, project.ROOT / "script")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps(result["counts"], indent=2))


if __name__ == "__main__":
    main()
