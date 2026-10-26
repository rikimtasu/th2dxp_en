"""Catalog native scenes and scoped manual observations without launching RPCS3."""
import json
from pathlib import Path
import struct

import project
import scenario_source

ROOT = Path(__file__).resolve().parents[1]


def catalog():
    data = project.source_bytes()
    kit = project.codec()
    observations = []
    for path in sorted((ROOT / "work/qa/observations").glob("*.json")):
        observation = project.load(path)
        if observation.get("source_sha256") != project.digest(data):
            raise ValueError(f"Observation source mismatch: {path}")
        screenshot = Path(observation["screenshot"])
        if project.digest(screenshot.read_bytes()) != observation["screenshot_sha256"]:
            raise ValueError(f"Observation screenshot changed: {path}")
        observations.append((str(path.relative_to(ROOT)), observation))
    references = {}
    index = ROOT / "reference/ittaku/index.jsonl"
    if index.exists():
        with index.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                if record["kind"] == "decoded":
                    references.setdefault(Path(record["entry"]).stem, []).append(record["id"])
    rows = []
    for entry, payload, name, chunks in scenario_source.scan(data, kit):
        label_count = struct.unpack_from("<I", payload, 8)[0]
        labels = []
        for i in range(label_count):
            off = 16 + i * 36
            text = payload[off:off + 32].split(b"\0", 1)[0].decode("cp932", errors="backslashreplace")
            labels.append({"name": text, "code_offset": struct.unpack_from("<I", payload, off + 32)[0]})
        texts = []
        path = project.BASELINE / entry.json_filename
        if path.exists():
            for ui, unit in enumerate(project.load(path)):
                for ii, item in enumerate(unit["items"]):
                    if item["kind"] == "text":
                        texts.append({"unit": ui, "item": ii, "japanese": item["original_text"]})
                        if len(texts) >= 3:
                            break
                if len(texts) >= 3:
                    break
        rows.append({"script": entry.json_filename, "source_name": name, "index": entry.entry_index,
                     "chunk_count": len(chunks), "labels": labels, "opening_text": texts,
                     "pc_reference_ids": references.get(name, [])[:5],
                     "pc_correspondence": "exact_archive_entry_name" if name in references else "none_in_ascii_index",
                     "route": None, "route_verified": False})
        navigation = []
        for path, observation in observations:
            if observation["source_name"] != name:
                continue
            source_units = project.load(project.BASELINE / entry.json_filename)
            matched = "".join(source_units[pos["unit"]]["items"][pos["item"]]["original_text"]
                              for pos in observation["matched_items"]).replace("\u3000", "")
            if matched != observation["observed_japanese"]:
                raise ValueError(f"Observation text does not match source: {path}")
            navigation.append({"evidence": path, "navigation": observation["navigation_reported_by_user"],
                               "new_game_first_scene_observed": observation["new_game_first_scene_observed"]})
        rows[-1]["navigation_observations"] = navigation
    report = {"source_sha256": project.digest(data), "scenario_count": len(rows), "scenarios": rows,
              "limits": "Exact source table/PC archive names are identifiers, not proof of identical scenes or runtime route"}
    project.save(ROOT / "work/scenes/catalog.json", report)
    print(json.dumps({"scenario_count": len(rows), "pc_named_matches": sum(bool(r["pc_reference_ids"]) for r in rows),
                      "opening_script": rows[0], "output": "work/scenes/catalog.json"}, ensure_ascii=False, indent=2))




def main():
    catalog()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(f"ERROR: {error}")
