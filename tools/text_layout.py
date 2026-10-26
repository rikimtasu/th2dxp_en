"""Opt-in ASCII layout experiment using the game's existing literal \\n control.

No font width is inferred here. A caller must choose an explicit diagnostic column
budget; production builds do not enable this compiler by default. Source controls
and provenance remain immutable; only additional no-wait line breaks are emitted.
"""
import copy
import re


BREAK = "\\n"


def wrap_ascii(text, columns):
    if not isinstance(columns, int) or isinstance(columns, bool) or columns < 1:
        raise ValueError("Layout columns must be a positive integer")
    if not text or any(not 0x20 <= ord(ch) <= 0x7E for ch in text) or "\\" in text:
        raise ValueError("Diagnostic wrapping requires printable ASCII without engine escapes")
    output = []
    column = 0
    for token in re.findall(r" +|[^ ]+", text):
        if not token.isspace() and len(token) <= columns and column and column + len(token) > columns:
            output.append(BREAK)
            column = 0
        for char in token:
            if column == columns:
                output.append(BREAK)
                column = 0
            output.append(char)
            column += 1
    return "".join(output)


def compile_units(units, *, columns, break_fragments):
    compiled = copy.deepcopy(units)
    changes = []
    for ui, unit in enumerate(compiled):
        previous_text = False
        for ii, item in enumerate(unit["items"]):
            if item["kind"] != "text":
                previous_text = False
                continue
            text = item["translated_text"]
            if text != item["original_text"]:
                emitted = wrap_ascii(text, columns)
                if previous_text and break_fragments:
                    emitted = BREAK + emitted
                budget = len(item["original_text"].encode("cp932", errors="strict"))
                size = len(emitted.encode("cp932", errors="strict"))
                if size > budget:
                    raise ValueError(f"unit {ui} item {ii}: compiled text needs {size} bytes, original budget is {budget}; content was not shortened")
                if emitted.replace(BREAK, "") != text:
                    raise ValueError("Layout compiler changed visible text")
                item["translated_text"] = emitted
                changes.append({"unit": ui, "item": ii, "input": text, "emitted": emitted,
                                "added_line_breaks": emitted.count(BREAK), "bytes": size, "budget": budget})
            previous_text = not item.get("control_suffix", "").endswith(BREAK)
    return compiled, {"columns": columns, "fragment_line_breaks": break_fragments, "records": changes,
                      "scope": "Explicit diagnostic profile, not a measured universal pixel-width limit"}
