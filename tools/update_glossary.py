#!/usr/bin/env python3
"""Refresh VNDB names and render the binding glossary; Python 3.10+, stdlib only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "glossary" / "sources"
ENDPOINT = "https://api.vndb.org/kana/character"
TITLES = {"v20": "ToHeart2", "v90": "ToHeart2 AnotherDays"}
FIELDS = "name,original,aliases"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def request_payload(title_id: str, page: int) -> dict:
    return {
        "filters": ["vn", "=", ["id", "=", title_id]],
        "fields": FIELDS,
        "sort": "id",
        "results": 100,
        "page": page,
        "count": True,
    }


def fetch_title(title_id: str) -> dict:
    pages = []
    page = 1
    while True:
        payload = request_payload(title_id, page)
        request = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TH2DXPLUS-English-Glossary/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
        pages.append({"request": payload, "response": result})
        if not result["more"]:
            break
        if not result["results"]:
            raise ValueError(f"{title_id}: empty page with more=true")
        page += 1
    return {
        "source": "VNDB Kana character API",
        "endpoint": ENDPOINT,
        "method": "POST",
        "title_id": title_id,
        "title_url": f"https://vndb.org/{title_id}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pages": pages,
    }


def validate_snapshot(snapshot: dict, title_id: str) -> list[dict]:
    if snapshot["title_id"] != title_id or snapshot["endpoint"] != ENDPOINT:
        raise ValueError(f"{title_id}: unexpected source metadata")
    datetime.fromisoformat(snapshot["retrieved_at"])
    pages = snapshot["pages"]
    if not pages:
        raise ValueError(f"{title_id}: no source pages")
    characters = []
    seen = set()
    counts = set()
    for page_number, page in enumerate(pages, 1):
        if page["request"] != request_payload(title_id, page_number):
            raise ValueError(f"{title_id}: unexpected query on page {page_number}")
        response = page["response"]
        if response["more"] != (page_number < len(pages)):
            raise ValueError(f"{title_id}: incomplete or extra source pages")
        counts.add(response["count"])
        for character in response["results"]:
            character_id = character["id"]
            if not re.fullmatch(r"c[1-9][0-9]*", character_id) or character_id in seen:
                raise ValueError(f"{title_id}: invalid or duplicate ID {character_id}")
            if set(character) != {"id", "name", "original", "aliases"}:
                raise ValueError(f"{title_id}: unexpected fields for {character_id}")
            if not isinstance(character["name"], str) or not character["name"]:
                raise ValueError(f"{character_id}: missing VNDB name")
            if character["original"] is not None and not isinstance(character["original"], str):
                raise ValueError(f"{character_id}: invalid Japanese original")
            if not isinstance(character["aliases"], list) or not all(
                isinstance(alias, str) for alias in character["aliases"]
            ):
                raise ValueError(f"{character_id}: invalid aliases")
            seen.add(character_id)
            characters.append(character)
    if counts != {len(characters)}:
        raise ValueError(f"{title_id}: returned counts do not match complete source list")
    return characters


def build_glossary(snapshots: dict, overrides: dict, provenance: dict) -> dict:
    if overrides["schema_version"] != 1:
        raise ValueError("Unsupported project override schema")
    merged = {}
    sources = []
    for title_id, title in TITLES.items():
        snapshot = snapshots[title_id]
        characters = validate_snapshot(snapshot, title_id)
        sources.append({
            "title_id": title_id,
            "title": title,
            "title_url": snapshot["title_url"],
            "endpoint": ENDPOINT,
            "retrieved_at": snapshot["retrieved_at"],
            "character_count": len(characters),
            "snapshot": f"glossary/sources/{title_id}.json",
        })
        for character in characters:
            character_id = character["id"]
            source_names = {key: character[key] for key in ("name", "original", "aliases")}
            if character_id not in merged:
                merged[character_id] = {"source_names": source_names, "memberships": []}
            elif merged[character_id]["source_names"] != source_names:
                raise ValueError(f"{character_id}: VNDB name data differs across title snapshots; refresh again")
            merged[character_id]["memberships"].append(title_id)
    characters = []
    for character_id in sorted(merged, key=lambda item: int(item[1:])):
        entry = merged[character_id]
        names = entry["source_names"]
        override = overrides["characters"].get(character_id)
        if override is not None:
            if set(override) != {"display_name", "reason"}:
                raise ValueError(f"{character_id}: override requires display_name and reason only")
            if not all(isinstance(value, str) and value for value in override.values()):
                raise ValueError(f"{character_id}: empty or invalid project override")
        characters.append({
            "id": character_id,
            "source_url": f"https://vndb.org/{character_id}",
            "japanese_original": names["original"],
            "vndb_name": names["name"],
            "vndb_aliases": names["aliases"],
            "project_display_name": override["display_name"] if override else names["name"],
            "project_override_reason": override["reason"] if override else None,
            "display_review_required": override is None,
            "memberships": entry["memberships"],
        })
    return {
        "schema_version": 1,
        "attribution": "Character name data from VNDB and its contributors; project display-name edits by this translation project.",
        "license": provenance["license"],
        "policy": overrides["policy"],
        "sources": sources,
        "characters": characters,
    }


def cell(text: str | None) -> str:
    return (text or "—").replace("|", "&#124;").replace("\n", " ")


def render_markdown(glossary: dict) -> str:
    characters = glossary["characters"]
    shared = sum(len(character["memberships"]) == 2 for character in characters)
    lines = [
        "# Binding character glossary",
        "",
        "Generated by `tools/update_glossary.py` from the checked-in VNDB snapshots and explicit project overrides. Do not edit this table directly.",
        "",
        "## Translation policy",
        "",
        "- **Use the project display name**, not the VNDB canonical romanization, for full English names. Japanese personal names use given-name-first order. Preserve the source's choice of given name, surname, nickname or title in dialogue; do not expand every mention into a full name.",
        "- **Retain Japanese honorifics** when present in the source. Do not invent honorifics where none exist. VNDB aliases are reference spellings, not instructions to replace contextual dialogue or normalize all nicknames.",
        "- This ordering/honorific policy follows the local Ittaku `README.TXT`, lines 115–120 (translation-style paragraph). It does not claim that every spelling below was checked against Ittaku's translated script. The README is a local reference and is not redistributed here.",
        "- Model identifiers, mononyms and the role label are not mechanically reversed. Ruuko's VNDB canonical name is retained as an explicit exception rather than guessing an alternative name order.",
        "- `vndb_name` is the exact VNDB canonical romanization; `project_display_name` is a separate project decision. Japanese originals and aliases are preserved verbatim. These name lists may themselves reveal alternate names; no descriptions, roles, traits, images, relationships or unrelated appearances are fetched.",
        "- Title membership means listed under that VNDB title, not a guarantee of presence in every release or route. The v20 entry covers versions beyond PS3, so this glossary is not a verified PS3-only cast list.",
        "",
        "## Source coverage",
        "",
        f"**{len(characters)} distinct VNDB character IDs; {shared} shared by both title lists.** Merge identity is the stable `c…` ID, never a name match.",
        "",
    ]
    for source in glossary["sources"]:
        lines.append(
            f"- [{source['title_id']} — {source['title']}]({source['title_url']}): "
            f"{source['character_count']} characters; retrieved {source['retrieved_at']}; "
            f"snapshot [`{source['snapshot']}`]({source['snapshot']})."
        )
    lines.extend([
        "",
        "## Approved names",
        "",
        "| VNDB ID | Japanese original | VNDB canonical romanization | Project display name | Title memberships | VNDB aliases (verbatim) |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for character in characters:
        display_name = cell(character["project_display_name"])
        if character["display_review_required"]:
            display_name += " **[REVIEW REQUIRED; unapproved VNDB fallback]**"
        values = [
            f"[{character['id']}]({character['source_url']})",
            cell(character["japanese_original"]),
            cell(character["vndb_name"]),
            display_name,
            ", ".join(character["memberships"]),
            "; ".join(cell(alias) for alias in character["vndb_aliases"]) or "—",
        ]
        lines.append("| " + " | ".join(values) + " |")
    lines.extend([
        "",
        "## Refreshing and editing",
        "",
        "Requires Python 3.10+ and the standard library only. Commands work from any current directory when the script path is provided; all outputs resolve from the script's own project root.",
        "",
        "```console",
        "python tools/update_glossary.py",
        "python tools/update_glossary.py --offline",
        "python tools/update_glossary.py --check",
        "```",
        "",
        "- The default command POSTs public, unauthenticated queries to `https://api.vndb.org/kana/character` for v20 and v90 separately, requests only `name,original,aliases`, follows all result pages, and writes both source snapshots, `glossary/characters.json` and this file. It validates the complete merged result before writing; a failed fetch does not silently replace data with a partial list.",
        "- `--offline` regenerates both derived outputs from the existing source snapshots without a network request. `--check` validates snapshots, membership counts, merged identities and exact generated outputs offline, writes nothing, and exits nonzero for inconsistent or stale outputs. These two flags are mutually exclusive.",
        "- Make binding changes in [`glossary/sources/project_overrides.json`](glossary/sources/project_overrides.json), keyed by stable VNDB ID. Each entry has an explicit `display_name` and a `reason`. The updater never overwrites this file, including overrides for IDs no longer returned by VNDB. Then regenerate with `--offline` or a normal refresh.",
        "- A newly encountered ID without an override retains its VNDB name but is explicitly flagged `display_review_required` in JSON and in the table. Review and add an explicit override before using it as an approved translation name. An ID missing from a refreshed title is removed from that title's memberships; its old override remains available for editorial review.",
        "- Conflicting name data for the same ID across the two snapshots aborts generation rather than silently choosing a title's version. Refresh again if VNDB was edited between queries.",
        "",
        "## Attribution, licensing and provenance",
        "",
        "Character names, aliases and title associations are derived from **VNDB and its contributors**. The source database and this adapted name dataset are distributed under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1.0/); rights in individual database contents are covered by the [Database Contents License 1.0](https://opendatacommons.org/licenses/dbcl/1.0/). This notice applies to the VNDB-derived dataset, not to game assets or the Ittaku translation.",
        "",
        "VNDB's [data-license policy](https://vndb.org/d17#4) and [Kana documentation](https://api.vndb.org/kana) are the authority. The API is free for non-commercial use and rate-limited. No API token is needed for these queries. No images or descriptions, whose licensing can differ, are included.",
        "",
        "[`glossary/sources/provenance.json`](glossary/sources/provenance.json) records the retrieved licensing statement and Ittaku style evidence. Each v20/v90 snapshot records its endpoint, retrieval timestamp, exact paginated requests and complete name-only responses. Separate filtered queries establish each title's membership without exposing other character appearances. The derived JSON repeats source URLs, timestamps, license notices, override reasons and memberships for downstream tooling.",
        "",
    ])
    return "\n".join(lines)


def build_outputs(snapshots: dict) -> dict[Path, str]:
    glossary = build_glossary(
        snapshots,
        load_json(SOURCE_DIR / "project_overrides.json"),
        load_json(SOURCE_DIR / "provenance.json"),
    )
    return {
        ROOT / "glossary" / "characters.json": json_text(glossary),
        ROOT / "glossary.md": render_markdown(glossary),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Regenerate using existing snapshots without network access")
    mode.add_argument("--check", action="store_true", help="Validate existing outputs offline without writing")
    args = parser.parse_args()
    try:
        snapshots = {
            title_id: load_json(SOURCE_DIR / f"{title_id}.json")
            if args.offline or args.check else fetch_title(title_id)
            for title_id in TITLES
        }
        outputs = build_outputs(snapshots)
        if args.check:
            stale = [str(path.relative_to(ROOT)) for path, text in outputs.items()
                     if not path.exists() or path.read_text(encoding="utf-8") != text]
            if stale:
                raise ValueError("Stale generated outputs: " + ", ".join(stale))
            print("Glossary sources and generated outputs are consistent (offline).")
            return 0
        if not args.offline:
            outputs = {
                **{SOURCE_DIR / f"{title_id}.json": json_text(snapshot)
                   for title_id, snapshot in snapshots.items()},
                **outputs,
            }
        for path, text in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        print("Wrote " + ", ".join(str(path.relative_to(ROOT)) for path in outputs))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Glossary update failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
