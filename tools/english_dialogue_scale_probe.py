"""Stage an exact, translated 85%-scale diagnostic, never a production build."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import tempfile

import dialogue_scale_probe
import native_dialogue_scale_patch
import patch_game
import project
import scenario_source

ROOT = project.ROOT
INPUT = ROOT / "build/english-v0.1/EBOOT.elf"
INPUT_SHA256 = "a31bdd834a61cd38fa310f0f63832d2991bc4a09558859a7ba63415e245e5735"
OBSERVED_SDAT_SHA256 = "1dbdf62409d07aa76ce90bf67815719c38be1cbd1e88ba04d45a3b651bd1a7dd"
OUTPUT = ROOT / "build/english-dialogue-scale-85-diagnostic"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdat", type=Path, required=True,
                        help="read-only archive identified by the player's observation")
    args = parser.parse_args()
    if OUTPUT.exists():
        raise ValueError(f"Existing diagnostic preserved: {OUTPUT}")
    if patch_game.sha256_file(args.sdat) != OBSERVED_SDAT_SHA256:
        raise ValueError("Archive differs from the user-identified test archive")
    incoming = INPUT.read_bytes()
    if project.digest(incoming) != INPUT_SHA256:
        raise ValueError("Translated diagnostic input differs from the released build")
    template = dialogue_scale_probe.INPUT.read_bytes()
    previous = project.load(dialogue_scale_probe.INPUT.parent / "manifest.json")["native_layout"]
    candidate, native = native_dialogue_scale_patch.apply(incoming, previous, staged=template)
    source = project.source_bytes()
    dialogue_scale_probe.check_hook(source, candidate, native)
    dialogue_scale_probe.check_hook(source, candidate, native, null=True)
    layout = dialogue_scale_probe.check_layout(source, incoming, candidate, previous, native)
    kit = project.codec()
    before, after = scenario_source.scan(incoming, kit), scenario_source.scan(candidate, kit)
    if len(before) != 1884 or [(vars(row[0]), row[1:]) for row in before] != [
            (vars(row[0]), row[1:]) for row in after]:
        raise ValueError("Diagnostic changed scenario payloads")
    phoff = struct.unpack_from(">Q", incoming, 0x20)[0]
    start, end = previous["rx_extension"]["file_end"], native["rx_extension"]["file_end"]
    allowed = set(range(phoff + 32, phoff + 48))
    allowed.update(range(native_dialogue_scale_patch.HOOK - 0x10000,
                         native_dialogue_scale_patch.HOOK - 0x10000 + 4))
    allowed.update(range(start, end))
    if len(incoming) != len(candidate) or any(a != b and offset not in allowed
                                               for offset, (a, b) in enumerate(zip(incoming, candidate))):
        raise ValueError("Diagnostic changed bytes outside the scale helper and RX bounds")
    report = {"diagnostic_only": True, "runtime_verified": False,
              "production_growth_enabled": False, "input_sha256": INPUT_SHA256,
              "output_sha256": project.digest(candidate),
              "user_identified_sdat_sha256": OBSERVED_SDAT_SHA256,
              "user_identified_sdat_copied_or_modified": False,
              "scenario_payloads_unchanged": len(before), "native_layout": native,
              "layout_replay": layout,
              "limitations": ["No live GPU, full VM, readability or voice synchronization proof.",
                              "Not a production build, installer or runtime acceptance.",
                              "Sentence-spacing drafts are not included."]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".english-scale-", dir=OUTPUT.parent) as folder:
        target = Path(folder)
        (target / "EBOOT.elf").write_bytes(candidate)
        project.save(target / "manifest.json", report)
        target.rename(OUTPUT)
    print(json.dumps({"output": str(OUTPUT / "EBOOT.elf"), "sha256": report["output_sha256"],
                      "sdat_sha256": OBSERVED_SDAT_SHA256, "unchanged_scenarios": len(before),
                      "layout": layout}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        raise SystemExit(f"ERROR: {error}")
