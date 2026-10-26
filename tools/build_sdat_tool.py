"""Build a repaired, separately licensed make_npdata derivative; never edit vendor sources."""
from pathlib import Path
import subprocess

import assets
import project

OUTPUT = project.ROOT / "work/make_npdata-pack"
DRIVER = project.ROOT / "tools/sdat_pack.c"
SOURCE_HASHES = {
    "make_npdata.c": "ad9fe7336bb26210a3ec0fbdd28c8a77d54de1211a2317186789a0cf4e0d294d",
    "aes.c": "d794d83ad305fa836406b328de8be7c587e109e6e21f1232ef70b8bf9f55d020",
    "sha1.c": "5797b2706bd45ee8e884123f5e4331b1814ffed64b62bd37b0608a72681f20aa",
    "lz.c": "ba402dd991797f596974c52950a76b497580a1136a3b7e37387089ffaa0fbada",
    "utils.c": "60dd3acee7fef6d455495d18be5200904df40f1fefd4a70310fda6842ffd962a",
    "make_npdata.h": "16b0f02b0674287f36ac9277ec117b7e514c2f00578b413e5ae7dc1a957a6941",
    "utils.h": "8f06f66dfd5fd2eb1b02176f66f5c18309b28a234ca9621a6f4a32036511c686",
    "aes.h": "c59aaa4d3c335b527763e6797f334dc2ac3ecc30d7d0ed7323a13b584aa560f1",
    "sha1.h": "3b15bf5c812de09589397a7612ae1a7a4eee9767784c795eb845d52404205adf",
    "lz.h": "fed3bf7c7f6034f66607eea4a2163aeea4e43bc72679e5ab0710f4e869bf2a73",
}


def repaired_source():
    for name, expected in SOURCE_HASHES.items():
        if assets.sha(assets.UPSTREAM / name) != expected:
            raise ValueError(f"Pinned SDAT source changed: {name}")
    text = (assets.UPSTREAM / "make_npdata.c").read_text(encoding="utf-8")

    def replace_once(before, after):
        nonlocal text
        if text.count(before) != 1:
            raise ValueError("Pinned SDAT source repair no longer has exactly one anchor")
        text = text.replace(before, after)

    replace_once('FILE* output = fopen(output_file_name, "wb");\n\n\t\t// Read all the necessary parameters for encryption.',
                 'FILE* output = fopen(output_file_name, "w+b");\n\n\t\t// Read all the necessary parameters for encryption.')
    begin, end = text.index("bool encrypt("), text.index("// EDAT/SDAT functions.")
    encryption = text[begin:end]
    if encryption.count("in, length, test_hash") != 3:
        raise ValueError("Pinned SDAT ciphertext-authentication anchors changed")
    text = text[:begin] + encryption.replace("in, length, test_hash", "out, length, test_hash") + text[end:]
    begin, end = text.index("int encrypt_data("), text.index("int forge_data(")
    body = text[begin:end]
    allocation = "dec_data = (unsigned char *) malloc (length);"
    if body.count(allocation) != 1:
        raise ValueError("Pinned SDAT final-block padding anchor changed")
    text = text[:begin] + body.replace(allocation, "dec_data = (unsigned char *) calloc (length, 1);") + text[end:]
    header_hash = "\t// Generate the header hash (located at offset 0xA0).\n\tencrypt(hash_mode, crypto_mode, (npd->version == 4), header, empty_header, 0xA0, header_key, header_iv, key, header_hash);\n"
    replace_once(header_hash, "")
    metadata_hash = "\tencrypt(hash_mode, crypto_mode, (npd->version == 4), metadata, empty_metadata, metadata_size, header_key, header_iv, key, metadata_hash);\n"
    replace_once(metadata_hash, metadata_hash + "\n\t// Header authentication includes the completed metadata CMAC.\n\tmemcpy(header + 0x90, metadata_hash, 0x10);\n" + header_hash)
    return text.encode("utf-8")


def build(output_dir=OUTPUT):
    output_dir = Path(output_dir)
    fixed = repaired_source()
    if output_dir.exists():
        raise ValueError("Existing SDAT pack tool preserved; refusing overwrite")
    output_dir.mkdir(parents=True, exist_ok=False)
    generated = output_dir / "make_npdata.fixed.c"
    generated.write_bytes(fixed)
    binary = output_dir / "make_npdata-pack.exe"
    command = ["gcc", "-O2", "-D_FILE_OFFSET_BITS=64", "-I", str(output_dir),
               "-I", str(assets.UPSTREAM), "-o", str(binary), str(DRIVER),
               *[str(assets.UPSTREAM / name) for name in ("aes.c", "sha1.c", "lz.c", "utils.c")]]
    subprocess.run(command, check=True)
    report = {"upstream_revision": assets.REVISION, "source_hashes": SOURCE_HASHES,
              "builder_sha256": assets.sha(Path(__file__)), "driver_sha256": assets.sha(DRIVER),
              "generated_sha256": project.digest(fixed), "binary_sha256": assets.sha(binary),
              "compiler": subprocess.check_output(["gcc", "--version"], text=True).splitlines()[0],
              "command": command, "license": "GPL-3.0; separate from game/translation rights",
              "repairs": ["readable update-mode output for forging", "authenticate ciphertext, not plaintext",
                          "metadata CMAC before dependent header CMAC", "zero deterministic final-block padding"]}
    project.save(output_dir / "manifest.json", report)
    return report


def validated_tool():
    report = project.load(OUTPUT / "manifest.json")
    binary = OUTPUT / "make_npdata-pack.exe"
    if (report["upstream_revision"] != assets.REVISION or report["source_hashes"] != SOURCE_HASHES
            or report["builder_sha256"] != assets.sha(Path(__file__))
            or report["driver_sha256"] != assets.sha(DRIVER)
            or report["generated_sha256"] != project.digest(repaired_source())
            or report["binary_sha256"] != assets.sha(binary)):
        raise ValueError("Standalone SDAT pack tool differs from its pinned repaired source/provenance")
    return binary, report


if __name__ == "__main__":
    try:
        print(build()["binary_sha256"])
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"ERROR: {error}")
