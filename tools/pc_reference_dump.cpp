// SPDX-License-Identifier: GPL-2.0
// Headless reference extractor, linked with ripdog/th2xr-portable (GPL-2.0),
// revision 14e8521ca999dfa9787b090c1c965ef3c6227530. See its LICENSE.txt.
// This file is GPL-2.0, independently of the Python wrapper's project license.
#include "archive.hpp"
#include "bytecode.hpp"
#include "event_metadata.h"
#include "scenario.hpp"
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;
static std::ofstream output(const fs::path& path, bool binary = false) {
    std::ofstream stream(path, binary ? std::ios::binary : std::ios::out);
    stream.exceptions(std::ios::badbit | std::ios::failbit);
    return stream;
}
int main(int argc, char** argv) {
    if (argc != 3) { std::cerr << "usage: pc-reference-dump ARCHIVE NEW-DIRECTORY\n"; return 2; }
    try {
        const fs::path destination(argv[2]);
        if (!fs::create_directory(destination)) throw std::runtime_error("output already exists");
        fs::create_directory(destination / "entries");
        auto metadata = output(destination / "metadata.tsv");
        for (unsigned opcode = 64; opcode < 64 + th2_event_count(); ++opcode) {
            const char* name = th2_event_name(opcode);
            const char* types = th2_event_parameters(opcode);
            if (!name || !types) throw std::runtime_error("missing event metadata");
            metadata << opcode << '\t' << name << '\t';
            for (unsigned argument = 0; argument < 15 && types[argument]; ++argument) {
                if (argument) metadata << ',';
                metadata << static_cast<unsigned>(types[argument]);
            }
            metadata << '\n';
        }
        const th2::Archive archive(argv[1]);
        if (archive.kind() != th2::ArchiveKind::kcap) throw std::runtime_error("expected KCAP");
        auto entries = output(destination / "entries.tsv");
        auto walk = output(destination / "walk.tsv");
        std::size_t index = 0;
        for (const auto& entry : archive.entries()) {
            try {
                // KCAP zero-stored-size entries are metadata markers, not LZS streams.
                const auto bytes = entry.stored_size == 0
                    ? std::vector<std::uint8_t>{} : archive.read(entry);
                auto raw = output(destination / "entries" / (std::to_string(index) + ".bin"), true);
                if (!bytes.empty())
                    raw.write(reinterpret_cast<const char*>(bytes.data()), bytes.size());
                std::string name = entry.name;
                std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c) { return std::tolower(c); });
                const bool signature = bytes.size() >= 4 && bytes[0] == 'L' && bytes[1] == 0 && bytes[2] == 'F' && bytes[3] == 0;
                const bool scenario_file = name.ends_with(".sdt") || signature;
                entries << index << '\t' << entry.offset << '\t' << entry.stored_size << '\t'
                        << entry.compressed << '\t' << bytes.size() << '\t' << scenario_file << '\n';
                if (scenario_file) {
                    const th2::Scenario scenario(bytes);
                    const auto code = scenario.bytecode();
                    std::size_t offset = 0;
                    while (offset < code.size()) {
                        const auto instruction = th2::decode_instruction(code, offset);
                        if (!instruction.size || instruction.size > code.size() - offset)
                            throw std::runtime_error("invalid instruction length at " + std::to_string(offset));
                        walk << index << '\t' << offset << '\t' << instruction.size << '\t'
                             << instruction.opcode << '\t' << instruction.name << '\n';
                        offset += instruction.size;
                    }
                    if (offset != code.size()) throw std::runtime_error("incomplete bytecode walk");
                }
            } catch (const std::exception& error) {
                throw std::runtime_error("entry " + std::to_string(index) + " " + entry.name + ": " + error.what());
            }
            ++index;
        }
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
