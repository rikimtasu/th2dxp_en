#!/usr/bin/env python3
"""Extract every encoded PC scenario string without executing a VM.

Run (from project root, no downloads):
  python tools/pc_reference.py extract --upstream work/upstream/th2xr-parser \
    --compiler "<path-to-g++>"

A successful run atomically publishes work/pc-reference/full-reference/ (must
not already exist). The old reference/ittaku/index.jsonl is never modified.
Every KCAP entry is inventoried; .sdt or LF-signature entries must validate as
Scenario and walk completely. Other entries are retained, not called scenarios.
All STRING8/STRING16 event operands and core SLoad filenames are retained,
including empty strings, controls and non-ASCII punctuation. Classification is
opcode-based, not proof that a string is visible dialogue or a character name.
Dynamic strings assembled by runtime expressions, external assets, and PS3
alignment are outside this encoded-operand reference. No expression is evaluated.

The independently licensed GPL-2.0 C++ helper links only pinned upstream parser
sources. No upstream GPL implementation is embedded in this Python wrapper.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from ittaku_reference import FormatError, lzss

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work' / 'pc-reference'
COMMIT = '14e8521ca999dfa9787b090c1c965ef3c6227530'
MANIFEST_SHA256 = '8e7ab4ca38f6dc155c731a96b3c0a7c746a93d60997e7ed8c0eda8f5d689ac9e'
HEADER = 1032
CLASSIFICATION = {
    'dialogue_or_message': ['SetMessage', 'SetMessage2', 'SetMessageEx', 'AddMessage', 'AddMessage2'],
    'choice': ['SetSelectMes', 'SetSelectMesEx'],
    'names_or_ui_text': ['SetText', 'SetTextEx', 'SetChipMessage'],
    'filename_or_resource': ['LoadScript', 'SLoad', 'SetBmp', 'SetBmpEx', 'SetBmpAnime', 'SetAvi'],
    'debug_text': ['DebugBox'],
    'map_event_label_or_resource': ['SetMapEvent'],
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FormatError(message)


def json_write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source_provenance(upstream: Path) -> dict:
    data = (upstream / 'source-manifest.json').read_bytes()
    require(digest(data) == MANIFEST_SHA256, 'upstream source manifest is not the pinned local manifest')
    manifest = json.loads(data)
    require(manifest['commit'] == COMMIT and manifest['license'] == 'GPL-2.0', 'wrong upstream revision/license')
    for name, record in manifest['files'].items():
        require(digest((upstream / name).read_bytes()) == record['sha256'], f'upstream source hash mismatch: {name}')
    return manifest


def archive_entries(data: bytes):
    require(data[:4] == b'KCAP' and len(data) >= 8, 'expected KCAP header')
    count = struct.unpack_from('<I', data, 4)[0]
    require(count == 1275, f'expected pinned 1275-entry KCAP, found {count}')
    directory_end = 8 + 36 * count
    require(directory_end <= len(data), 'truncated KCAP directory')
    intervals = []
    for index in range(count):
        kind, raw_name, offset, size = struct.unpack_from('<I24sII', data, 8 + 36 * index)
        require(offset + size <= len(data) and (size == 0 or offset >= directory_end),
                f'entry {index}: archive bounds')
        name_bytes = raw_name.split(b'\0', 1)[0].split(b'\xff', 1)[0]
        name = name_bytes.decode('cp932', errors='strict')
        stored = data[offset:offset + size]
        if size == 0:
            # Empty metadata markers have no compression header or payload interval.
            raw = b''
        elif kind:
            require(size >= 8, f'entry {index}: truncated compression header')
            raw = lzss(stored[8:], struct.unpack_from('<I', stored, 4)[0])
        else:
            raw = stored
        if size:
            intervals.append((offset, offset + size))
        yield {'entry_index': index, 'entry': name, 'entry_name_hex': name_bytes.hex(),
               'archive_offset': offset, 'stored_size': size, 'compressed': bool(kind),
               'archive_type': kind, 'empty_stored_entry': size == 0,
               'stored_sha256': digest(stored), 'decoded_sha256': digest(raw)}, raw
    intervals.sort()
    require(all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])), 'overlapping KCAP entries')


def read_rows(path: Path):
    with path.open(encoding='ascii', newline='') as stream:
        for line in stream:
            yield line.rstrip('\r\n').split('\t')


def operands(code: bytes, start: int, size: int, opcode: int, types: list[int]):
    """Read encoded lengths only; never evaluate register/number/compare values."""
    end = start + size
    pos = start + 2

    def take(count: int) -> int:
        nonlocal pos
        require(count >= 0 and pos + count <= end, f'operand outside instruction at {start}')
        old = pos
        pos += count
        return old

    def number() -> None:
        mode = code[take(1)]
        if mode == 2:
            length = code[take(1)]
            take(length)
        else:
            take(4)

    for argument, kind in enumerate(types):
        if kind in (1, 5, 7):
            take(1)
        elif kind in (8, 9):
            take(2)
        elif kind == 2:
            number()
        elif kind == 6:
            take(2)
            number()
        elif kind in (3, 4):
            prefix = take(1 if kind == 3 else 2)
            length = code[prefix] if kind == 3 else struct.unpack_from('<H', code, prefix)[0]
            text = take(length)
            yield argument, kind, prefix, text, length
        else:
            raise FormatError(f'unknown parameter type {kind} for opcode {opcode}')
    require(pos == end, f'operand metadata does not cover instruction at {start}: {pos} != {end}')


def collect(stage: Path, archive: bytes) -> dict:
    dump = stage / 'parser-dump'
    metadata = {}
    for opcode, name, kinds in read_rows(dump / 'metadata.tsv'):
        key = int(opcode)
        require(key not in metadata, 'duplicate opcode metadata')
        metadata[key] = (name, [int(item) for item in kinds.split(',')] if kinds else [])
    inventory = list(archive_entries(archive))
    rows = list(read_rows(dump / 'entries.tsv'))
    require(len(rows) == len(inventory), 'helper did not inventory every archive entry')
    entries, codes, cursors, counts, string_counts = [], {}, {}, Counter(), Counter()
    for (entry, raw), row in zip(inventory, rows):
        index, offset, stored, compressed, decoded, scenario = map(int, row)
        require((index, offset, stored, compressed, decoded) ==
                (entry['entry_index'], entry['archive_offset'], entry['stored_size'], int(entry['compressed']), len(raw)),
                f'helper/archive directory disagreement at entry {index}')
        require((dump / 'entries' / f'{index}.bin').read_bytes() == raw,
                f'helper decoded bytes differ from independently decoded archive entry {index}')
        expected_scenario = entry['entry'].lower().endswith('.sdt') or raw[:4] == b'L\0F\0'
        require(bool(scenario) == expected_scenario, f'scenario classification disagreement at {index}')
        entry.update(decoded_size=len(raw), scenario=bool(scenario), instruction_count=0, text_operand_count=0)
        entry['entry_classification'] = ('scenario' if scenario else
                                         'non_scenario_empty_entry' if entry['empty_stored_entry'] else
                                         'non_scenario_payload')
        if scenario:
            require(len(raw) >= HEADER and raw[:4] == b'L\0F\0', f'entry {index}: invalid scenario header')
            require(struct.unpack_from('<I', raw, 4)[0] == len(raw), f'entry {index}: declared size mismatch')
            code = raw[HEADER:]
            blocks = struct.unpack_from('<256I', raw, 8)
            require(all(address <= len(code) for address in blocks), f'entry {index}: block outside bytecode')
            entry['block_addresses'] = list(blocks)
            codes[index], cursors[index] = code, 0
        entries.append(entry)
    boundaries = {index: {0} for index in codes}
    with (stage / 'text-operands.jsonl').open('w', encoding='utf-8', newline='\n') as out:
        for row in read_rows(dump / 'walk.tsv'):
            index, offset, size, opcode = map(int, row[:4])
            name = row[4]
            require(index in codes and offset == cursors[index], f'noncontiguous instruction walk at entry {index}')
            code = codes[index]
            require(size >= 2 and offset + size <= len(code), f'instruction bounds at {index}:{offset}')
            require(struct.unpack_from('<H', code, offset)[0] == opcode, f'opcode mismatch at {index}:{offset}')
            cursors[index] += size
            boundaries[index].add(offset + size)
            entries[index]['instruction_count'] += 1
            counts[name] += 1
            if opcode >= 64:
                require(opcode in metadata and metadata[opcode][0] == name, 'opcode metadata mismatch')
                spans = operands(code, offset, size, opcode, metadata[opcode][1])
            elif opcode == 40:
                require(size >= 3 and size == 3 + code[offset + 2], 'invalid SLoad string length')
                spans = [(0, 3, offset + 2, offset + 3, code[offset + 2])]
            else:
                continue
            for argument, kind, prefix, text_offset, length in spans:
                raw = code[text_offset:text_offset + length]
                # Strict CP932: no replacement, trimming, control removal or newline normalization.
                text = raw.decode('cp932', errors='strict')
                entry_raw = inventory[index][1]
                require(raw == entry_raw[HEADER + text_offset:HEADER + text_offset + length], 'raw archive operand mismatch')
                category = next((category for category, names in CLASSIFICATION.items() if name in names), 'other_encoded_string')
                record = {'entry': entries[index]['entry'], 'entry_index': index,
                          'opcode': opcode, 'opcode_name': name, 'argument_index': argument,
                          'instruction_index': entries[index]['instruction_count'] - 1,
                          'instruction_offset': offset, 'instruction_size': size,
                          'instruction_entry_offset': HEADER + offset,
                          'length_prefix_offset': prefix, 'parameter_type': kind,
                          'text_offset': text_offset, 'text_entry_offset': HEADER + text_offset,
                          'byte_length': length, 'raw_hex': raw.hex(), 'raw_sha256': digest(raw),
                          'text': text, 'classification': category,
                          'archive_stored_offset': entries[index]['archive_offset'],
                          'archive_text_offset': None if entries[index]['compressed'] else entries[index]['archive_offset'] + HEADER + text_offset}
                out.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')
                entries[index]['text_operand_count'] += 1
                string_counts[name] += 1
    for index, code in codes.items():
        require(cursors[index] == len(code), f'entry {index}: incomplete bytecode walk')
        require(all(address == 0 or address - 1 in boundaries[index] for address in entries[index]['block_addresses']),
                f'entry {index}: block does not point to instruction boundary')
    json_write(stage / 'entries.json', entries)
    return {'archive_entries': len(entries), 'scenario_entries': len(codes),
            'non_scenario_entries': len(entries) - len(codes), 'instructions': sum(counts.values()),
            'empty_stored_entries': sum(entry['empty_stored_entry'] for entry in entries),
            'non_scenario_empty_entries': sum(entry['entry_classification'] == 'non_scenario_empty_entry' for entry in entries),
            'text_operands': sum(string_counts.values()), 'instruction_opcodes': dict(sorted(counts.items())),
            'text_operand_opcodes': dict(sorted(string_counts.items())),
            'all_scenario_bytecode_walked': True, 'all_entry_bytes_independently_verified': True,
            'all_text_bytes_verified': True, 'strict_cp932': True}


def extract(args) -> Path:
    upstream = Path(args.upstream).resolve()
    provenance = source_provenance(upstream)
    manifest = json.loads((ROOT / 'reference/ittaku/manifest.json').read_text(encoding='utf-8'))
    archive_path = Path(manifest['source']['path'])
    archive = archive_path.read_bytes()
    require(digest(archive) == manifest['source']['sha256'], 'archive hash differs from verified Ittaku reference')
    compiler = Path(args.compiler).resolve()
    require(compiler.is_file(), 'explicit local compiler does not exist')
    destination = Path(args.output).resolve()
    require(destination.is_relative_to(WORK.resolve()), 'output must remain inside ignored work/pc-reference/')
    require(not destination.exists(), 'output already exists; choose a new --output directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.extract-', dir=destination.parent))
    try:
        helper_source = ROOT / 'tools/pc_reference_dump.cpp'
        executable = stage / 'pc-reference-dump.exe'
        version = subprocess.run([str(compiler), '--version'], check=True, capture_output=True)
        (stage / 'compiler-version.txt').write_bytes(version.stdout + version.stderr)
        metadata_object = stage / 'event_metadata.o'
        metadata_command = [str(compiler), '-x', 'c', '-O2', '-c', '-I', str(upstream),
                            str(upstream / 'event_metadata.c'), '-o', str(metadata_object)]
        command = [str(compiler), '-std=c++20', '-O2', '-I', str(upstream),
                   str(helper_source), *[str(upstream / name) for name in ('archive.cpp', 'scenario.cpp', 'bytecode.cpp')],
                   str(metadata_object), '-o', str(executable)]
        environment = os.environ.copy()
        environment['PATH'] = str(compiler.parent) + os.pathsep + environment.get('PATH', '')
        json_write(stage / 'build-commands.json', [metadata_command, command])
        with (stage / 'metadata-build.stdout').open('wb') as stdout, (stage / 'metadata-build.stderr').open('wb') as stderr:
            subprocess.run(metadata_command, check=True, stdout=stdout, stderr=stderr, env=environment)
        with (stage / 'build.stdout').open('wb') as stdout, (stage / 'build.stderr').open('wb') as stderr:
            subprocess.run(command, check=True, stdout=stdout, stderr=stderr, env=environment)
        run_command = [str(executable), str(archive_path), str(stage / 'parser-dump')]
        with (stage / 'extract.stdout').open('wb') as stdout, (stage / 'extract.stderr').open('wb') as stderr:
            subprocess.run(run_command, check=True, stdout=stdout, stderr=stderr, env=environment)
        coverage = collect(stage, archive)
        shutil.copyfile(upstream / 'LICENSE.txt', stage / 'UPSTREAM-LICENSE.txt')
        json_write(stage / 'source-manifest.json', provenance)
        json_write(stage / 'manifest.json', {
            'schema_version': 1, 'archive_path': str(archive_path), 'archive_sha256': digest(archive),
            'upstream': provenance['repository'], 'commit': COMMIT, 'license': 'GPL-2.0',
            'upstream_manifest_sha256': MANIFEST_SHA256,
            'helper_sha256': digest(helper_source.read_bytes()), 'wrapper_sha256': digest(Path(__file__).read_bytes()),
            'independent_archive_decoder_sha256': digest((ROOT / 'tools/ittaku_reference.py').read_bytes()),
            'compiler_path': str(compiler), 'compiler_sha256': digest(compiler.read_bytes()),
            'compiler_version_sha256': digest((stage / 'compiler-version.txt').read_bytes()),
            'executable_sha256': digest(executable.read_bytes()),
            'metadata_object_sha256': digest(metadata_object.read_bytes()),
            'build_commands': [metadata_command, command], 'extract_command': run_command,
            'classification': CLASSIFICATION, 'coverage': coverage,
            'offset_convention': 'Zero-based. instruction_offset/text_offset/length_prefix_offset are bytecode-relative; *_entry_offset includes 1032-byte LF header. Compressed entries have no direct archive_text_offset.',
            'limits': ['Encoded strings only; no runtime expression evaluation or external-asset text.',
                       'Non-scenario entries inventoried and retained, not parsed as bytecode.',
                       'Zero-stored-size metadata entries retain original type/name/offset, have empty decoded bytes and no payload interval; empty .sdt entries still fail scenario validation.',
                       'Opcode classification is not dialogue/name visibility or PS3 alignment proof.',
                       'Unknown opcodes/metadata, bounds, truncation, header or CP932 errors fail the entire extraction.',
                       'No VM, rendering, game or emulator execution; no translation/import approval.'],
            'output_sha256': {str(path.relative_to(stage)): digest(path.read_bytes()) for path in
                              (stage / 'text-operands.jsonl', stage / 'entries.json', stage / 'parser-dump/walk.tsv', stage / 'parser-dump/metadata.tsv')},
        })
        stage.rename(destination)
        return destination
    except BaseException:
        # No partial result is published. Preserve diagnostics under an explicit failed directory.
        failed = stage.with_name(stage.name + '-failed')
        stage.rename(failed)
        print(f'Extraction failed; unpublished diagnostics: {failed}', file=sys.stderr)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('extract', help='Compile pinned headless parser and atomically extract/validate all encoded strings')
    command.add_argument('--upstream', required=True, help='Existing pinned local parser source root (never downloaded)')
    command.add_argument('--compiler', required=True, help='Existing local g++ executable')
    command.add_argument('--output', default=str(WORK / 'full-reference'), help='New directory beneath work/pc-reference/')
    args = parser.parse_args()
    try:
        print(extract(args))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'PC reference extraction failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
