"""Generate hash-bound RPCS3 debug-menu patches; never configure RPCS3."""
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

import debug_script_probe
import project


RPCS3_REVISION = "cd0c200b9f45427a2a55dc50c99993f2b100a987"
MODES = {
    "scene-menu": "Debug - Scene Selector",
    "graphics-test": "Debug - System Tests (Map, Calendar, Clock)",
}


def ppu_patch_hash(image: bytes) -> str:
    """Match RPCS3 ppu_load_exec, NOT a whole-file SHA-1 or SHA-256."""
    if len(image) < 64 or image[:6] != b"\x7fELF\x02\x02":
        raise ValueError("Expected a decrypted ELF64 big-endian executable")
    phoff = struct.unpack_from(">Q", image, 32)[0]
    stride, count = struct.unpack_from(">HH", image, 54)
    if stride != 56 or not count or phoff + stride * count > len(image):
        raise ValueError("Invalid ELF program-header table")
    digest = hashlib.sha1()
    for index in range(count):
        kind, flags, offset, address, _, file_size, mem_size, _ = struct.unpack_from(
            ">IIQQQQQQ", image, phoff + index * stride)
        digest.update(struct.pack(">II", kind, flags))
        if kind == 1 and mem_size:
            if file_size > mem_size or offset + file_size > len(image):
                raise ValueError("Invalid ELF load-segment bounds")
            digest.update(struct.pack(">QQ", address, mem_size))
            digest.update(image[offset:offset + file_size])
    return "PPU-" + digest.hexdigest()


def patch_document(images, source):
    """Emit two exclusive options per exact executable hash; verify each hook."""
    kit = project.codec()
    entries = {row["source_name"]: row for row in project.baseline()["entries"]}
    lines = ['Version: 1.2', '',
             '# Generated debug startup patches; enable ONE mode, then restart.',
             '# Do not use the prepatched debug-probe ELF with these cheats.', '']
    reports = []
    seen = set()
    for label, image in images:
        image_hash = project.digest(image)
        ppu_hash = ppu_patch_hash(image)
        if ppu_hash in seen:
            raise ValueError("Duplicate executable hash in patch inputs")
        seen.add(ppu_hash)
        headers = kit.read_elf_program_headers(image)
        if kit.vaddr_to_fileoff(debug_script_probe.START_VA, headers) != debug_script_probe.START_OFFSET:
            raise ValueError("Executable startup mapping differs from the verified source")
        lines.extend([f'# {label}; ELF SHA-256: {image_hash}', f'{ppu_hash}:'])
        modes = []
        for target, description in MODES.items():
            name = debug_script_probe.TARGETS[target]
            entry = entries[name]
            table_offset = 0xEE8B4 + entry['entry_index'] * 16
            name_va = struct.unpack_from('>I', image, table_offset)[0]
            offset = kit.vaddr_to_fileoff(name_va, headers)
            if image[offset:offset + 10] != name.encode('ascii') + b'\0':
                raise ValueError("Executable does not retain the verified test-script name")
            patched, writes = debug_script_probe.patch_named_start(image, name_va)
            # On the original image, ensure the same bytes as the existing probe.
            if image == source:
                reference, _ = debug_script_probe.investigate(source, target)
                if patched != reference:
                    raise ValueError("RPCS3 patch differs from the original debug probe")
            if image == source:
                note = ('Retained character/event selector. User confirmed this RPCS3 patch works on the original executable.'
                        if target == 'scene-menu' else
                        'Retained map, calendar and clock tests. User confirmed this RPCS3 patch works on the original executable.')
            else:
                note = ('Retained character/event selector. The original ELF probe was user-tested; '
                        'this RPCS3 patch packaging still needs manual confirmation.' if target == 'scene-menu'
                        else 'Retained map, calendar and clock tests. Runtime functionality is not yet confirmed.')
            note += ' Enable only one debug startup mode. Start a NEW ToHeart2 game; do not load or save progress. Disable and restart for normal play. Keep the correct SDAT paired with your executable.'
            lines.extend([
                f'  "{description}":',
                '    Games:',
                '      "ToHeart2 DX PLUS":',
                '        BLJM60381: [ All ]',
                '    Author: "TH2DXP localization workspace"',
                '    Patch Version: 1.0',
                '    Group: "TH2DXP Debug Startup"',
                f'    Notes: "{note}"',
                '    Patch:',
            ])
            for write in writes:
                lines.append(f"      - [ be32, {int(write['va'], 0):#010x}, 0x{write['after']} ]")
            modes.append({'name': description, 'native_script': name, 'writes': writes,
                          'patched_elf_sha256': project.digest(patched),
                          'user_reported_runtime_verified': image == source})
        lines.append('')
        reports.append({'label': label, 'elf_sha256': image_hash,
                        'ppu_patch_hash': ppu_hash, 'modes': modes})
    return '\n'.join(lines), {
        'rpcs3_reference_revision': RPCS3_REVISION,
        'hash_algorithm_reference': f'https://github.com/RPCS3/rpcs3/blob/{RPCS3_REVISION}/rpcs3/Emu/Cell/PPUModule.cpp#L2333-L2468',
        'patch_format_reference': f'https://github.com/RPCS3/rpcs3/blob/{RPCS3_REVISION}/Utilities/bin_patch.cpp',
        'inputs': reports,
        'runtime_evidence_scope': 'Both modes user-confirmed on the original executable on 2026-10-29; English variants remain unverified',
        'rpcs3_configuration_modified': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--additional-elf', action='append', type=Path, default=[],
                        help='Additional exact compatible executable to hash and guard')
    parser.add_argument('--output', required=True, type=Path,
                        help='New workspace patch.yml file; refuses overwrite')
    parser.add_argument('--report', required=True, type=Path,
                        help='New workspace JSON evidence file; refuses overwrite')
    args = parser.parse_args()
    output, report_path = args.output.resolve(), args.report.resolve()
    if output == report_path:
        raise ValueError('Patch and report paths must be different')
    for path in (output, report_path):
        if not path.is_relative_to(project.ROOT.resolve()) or path.exists():
            raise ValueError('Outputs must be new paths inside the workspace')
    source = project.source_bytes()
    images = [('Original Japanese BLJM60381', source)]
    for path in args.additional_elf:
        resolved = path.resolve()
        if not resolved.is_relative_to(project.ROOT.resolve()):
            raise ValueError('Additional ELF must be a staged workspace file')
        images.append((path.as_posix(), resolved.read_bytes()))
    text, report = patch_document(images, source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    project.save(report_path, report)
    print(f'Created: {output}')
    for row in report['inputs']:
        print(f"{row['label']}: {row['ppu_patch_hash']}")
    print('No RPCS3 configuration, installed executable, archive or save was modified.')


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        raise SystemExit(f'ERROR: {error}') from error
