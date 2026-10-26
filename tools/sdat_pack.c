/* SPDX-License-Identifier: GPL-3.0-only
 * Standalone derivative of Hykem's GPL-3.0 make_npdata; not part of the game.
 * The generated upstream source retains its original copyright/license notice.
 */
#include <limits.h>
#include <stdlib.h>
#define main make_npdata_upstream_main
#include "make_npdata.fixed.c"
#undef main

static unsigned int read_be32(const unsigned char *p)
{
    return ((unsigned int)p[0] << 24) | ((unsigned int)p[1] << 16)
        | ((unsigned int)p[2] << 8) | p[3];
}

static u64 read_be64(const unsigned char *p)
{
    return ((u64)read_be32(p) << 32) | read_be32(p + 4);
}

static int cmac_matches(unsigned char *key, unsigned char *data, int size,
                        const unsigned char *expected)
{
    unsigned char actual[16];
    cmac_hash_forge(key, 16, data, size, actual);
    return memcmp(actual, expected, 16) == 0;
}

/* Unlike upstream decrypt_data, this path checks every authentication result.
 * Only the exact contiguous-CMAC format emitted by the local packer is accepted.
 */
static int verify_sdat(const char *path)
{
    FILE *stream = fopen(path, "rb");
    unsigned char header[0xB0], block[0x4000], root_key[16], hash_key[16];
    unsigned char block_key[16], encrypted_key[16], *metadata = NULL;
    aes_context root_context, master_context;
    int result = 1;
    const char *error = "Cannot read complete SDAT header";
    if (!stream)
    {
        fprintf(stderr, "ERROR: Cannot open SDAT for authentication\n");
        return 1;
    }
    if (fread(header, 1, sizeof(header), stream) != sizeof(header))
        goto done;
    unsigned int version = read_be32(header + 4);
    u64 size = read_be64(header + 0x88);
    error = "Unsupported SDAT authentication format";
    if (memcmp(header, "NPD\0", 4) || version < 1 || version > 4
        || read_be32(header + 8) != 0 || read_be32(header + 0x80) != 0x0100000C
        || read_be32(header + 0x84) != sizeof(block) || !size)
        goto done;
    u64 blocks = (size - 1) / sizeof(block) + 1;
    error = "SDAT metadata or file length is outside format bounds";
    if (blocks > INT_MAX / 16)
        goto done;
    int metadata_size = (int)(blocks * 16);
    u64 expected_size = 0x100 + (u64)metadata_size + ((size + 15) & ~(u64)15) + 16;
    if (fseeko(stream, 0, SEEK_END) || ftello(stream) < 0
        || (u64)ftello(stream) != expected_size)
        goto done;
    for (int i = 0; i < 16; ++i)
        root_key[i] = header[0x60 + i] ^ SDAT_KEY[i];
    aes_setkey_enc(&root_context, root_key, 128);
    aes_setkey_dec(&master_context, version == 4 ? EDAT_KEY_1 : EDAT_KEY_0, 128);
    aes_crypt_ecb(&master_context, AES_DECRYPT, root_key, hash_key);
    error = "SDAT header CMAC differs";
    if (!cmac_matches(hash_key, header, 0xA0, header + 0xA0))
        goto done;
    metadata = (unsigned char *)malloc(metadata_size);
    error = "Cannot allocate/read complete SDAT metadata";
    if (!metadata || fseeko(stream, 0x100, SEEK_SET)
        || fread(metadata, 1, metadata_size, stream) != (size_t)metadata_size)
        goto done;
    error = "SDAT metadata CMAC differs";
    if (!cmac_matches(hash_key, metadata, metadata_size, header + 0x90))
        goto done;
    memset(block_key, 0, sizeof(block_key));
    if (version > 1)
        memcpy(block_key, header + 0x60, 12);
    for (u64 i = 0; i < blocks; ++i)
    {
        u64 remaining = size - i * sizeof(block);
        size_t length = remaining < sizeof(block) ? (size_t)((remaining + 15) & ~(u64)15) : sizeof(block);
        error = "Cannot read complete SDAT ciphertext block";
        if (fread(block, 1, length, stream) != length)
            goto done;
        block_key[12] = (unsigned char)(i >> 24);
        block_key[13] = (unsigned char)(i >> 16);
        block_key[14] = (unsigned char)(i >> 8);
        block_key[15] = (unsigned char)i;
        aes_crypt_ecb(&root_context, AES_ENCRYPT, block_key, encrypted_key);
        aes_crypt_ecb(&master_context, AES_DECRYPT, encrypted_key, hash_key);
        error = "SDAT ciphertext block CMAC differs";
        if (!cmac_matches(hash_key, block, (int)length, metadata + i * 16))
        {
            fprintf(stderr, "Authentication rejected block %llu\n", (unsigned long long)i);
            goto done;
        }
    }
    printf("Authenticated %llu SDAT blocks.\n", (unsigned long long)blocks);
    puts("SDAT header, metadata and every ciphertext block authenticated!");
    result = 0;
done:
    if (result)
        fprintf(stderr, "ERROR: %s\n", error);
    free(metadata);
    fclose(stream);
    return result;
}

int main(int argc, char **argv)
{
    if (argc == 3 && strcmp(argv[1], "--verify") == 0)
        return verify_sdat(argv[2]);
    return make_npdata_upstream_main(argc, argv);
}
