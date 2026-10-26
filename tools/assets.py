"""Recover local SDAT assets without invoking RPCS3 or changing the installation."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import mmap
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work/assets"
UPSTREAM = ROOT / "vendor/make_npdata/Linux"
BINARY = ROOT / "work/make_npdata.exe"
REVISION = "933f79d9e34f874bd23d25b3e14ca2dc3e43f9fb"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def prepare():
    WORK.mkdir(parents=True, exist_ok=True)
    if not UPSTREAM.exists():
        raise ValueError("Fetch pinned make_npdata using tools/bootstrap.py first")
    revision = subprocess.check_output(["git", "-C", str(UPSTREAM.parent), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError("Unexpected make_npdata revision")
    if not BINARY.exists():
        subprocess.run(["gcc", "-O2", "-D_FILE_OFFSET_BITS=64", "-o", str(BINARY),
                        *[str(UPSTREAM / n) for n in ("make_npdata.c", "aes.c", "sha1.c", "lz.c", "utils.c")]], check=True)
    config = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))
    source = Path(config["game_usrdir"]) / "data.sdat"
    output = WORK / "data.dat"
    manifest = WORK / "decryption.json"
    if manifest.exists() and output.exists():
        old = json.loads(manifest.read_text(encoding="utf-8"))
        if old["source_sha256"] == sha(source) and old["output_sha256"] == sha(output):
            print("Existing decrypted DAT verified", output)
            return
        raise ValueError("Existing recovered assets changed; refusing silent replacement")
    with source.open("rb") as f:
        header = f.read(144)
    if header[:4] != b"NPD\0" or not int.from_bytes(header[128:132], "big") & 0x1000000:
        raise ValueError("Expected an SDAT container")
    size = int.from_bytes(header[136:144], "big")
    source_hash = sha(source)
    temporary = WORK / "data.partial"
    log = WORK / "decryption.log"
    # Upstream's CLI needs -v for its argc check when no optional RAP is supplied.
    # It also returns zero for some failures; inspect its actual completion messages.
    with log.open("wb") as stream:
        result = subprocess.run([str(BINARY), "-v", "-d", str(source), str(temporary), "0"], stdout=stream, stderr=subprocess.STDOUT)
    messages = log.read_text(encoding="utf-8", errors="replace")
    if result.returncode or "File successfully decrypted!" not in messages or "File successfully parsed!" not in messages or "Decryption failed" in messages:
        raise ValueError(f"SDAT recovery failed; inspect {log}")
    if not temporary.exists() or temporary.stat().st_size != size:
        raise ValueError("Recovered DAT length differs from SDAT header")
    if sha(source) != source_hash:
        raise ValueError("Installed SDAT changed during recovery; output not promoted")
    dat = module("th2_asset_dat", ROOT / "vendor/TH2DXP_KIT/dat_tool.py")
    meta, entries = dat.parse_archive_table(temporary)
    temporary.replace(output)
    report = {"source": str(source), "source_sha256": source_hash, "source_size": source.stat().st_size,
              "output": str(output), "output_size": size, "output_sha256": sha(output),
              "make_npdata_revision": REVISION, "binary_sha256": sha(BINARY), "entry_count": len(entries),
              "decryption_log": str(log), "emulator_launched": False}
    save(manifest, report)
    print(json.dumps(report, indent=2))


def inspect():
    source = WORK / "data.dat"
    dat = module("th2_asset_dat", ROOT / "vendor/TH2DXP_KIT/dat_tool.py")
    tpl = module("th2_asset_tpl", ROOT / "vendor/TH2DXP_KIT/tpl_image_tool.py")
    meta, entries = dat.parse_archive_table(source)
    save(WORK / "catalog.json", {"metadata": meta, "entries": [vars(e) for e in entries]})
    candidates = [e for e in entries if re.search(r"font|fnt|\.tbl$", e.name, re.I)]
    recovered = []
    with source.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as blob:
        for entry in candidates:
            relative = Path(entry.name)
            if relative.is_absolute() or ".." in relative.parts or ":" in entry.name:
                raise ValueError("Unsafe archive asset path")
            path = WORK / "fonts" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            raw, flags = dat.decompress_archive_entry(blob, entry)
            path.write_bytes(raw)
            row = {"name": entry.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "chunk_flags": flags, "images": []}
            if path.suffix.lower() == ".tpl":
                records = tpl.parse_records(raw)
                row["textures"] = [vars(r) for r in records]
                for i, record in enumerate(records):
                    if record.fmt in tpl.FMT_A4R4G4B4:
                        images = tpl.extract_a4_channels(raw, record)
                    else:
                        # Expose only formats the dedicated upstream tool decodes.
                        decoder = {0x85: tpl.decode_argb8888, 0xA5: tpl.decode_argb8888,
                                   0x81: tpl.decode_l8, 0xA1: tpl.decode_l8,
                                   0x8B: tpl.decode_g8b8, 0xAB: tpl.decode_g8b8}.get(record.fmt)
                        if decoder is None:
                            row.setdefault("unsupported_formats", []).append(record.fmt)
                            continue
                        images = {"image": decoder(raw, record)}
                    for channel, image in images.items():
                        dest = path.with_name(f"{path.stem}.{i}.{channel}.png")
                        image.save(dest)
                        row["images"].append(str(dest.relative_to(ROOT)))
            recovered.append(row)
    report = {"archive_entries": len(entries), "font_candidates": recovered,
              "limits": "Extracted textures prove stored glyph pixels only, not runtime advance widths or screen fit"}
    save(WORK / "font-report.json", report)
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "inspect"))
    args = parser.parse_args()
    (prepare if args.command == "prepare" else inspect)()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"ERROR: {error}")
