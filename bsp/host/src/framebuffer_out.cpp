/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 *
 * Framebuffer digests and PPM output.
 *
 * # Why the digest is defined the way it is
 *
 * The canonical form is the **raw RGB565 byte stream**: width * height *
 * 2 bytes, row-major, little-endian per pixel. Byte for byte the same
 * definition the firmware backend uses
 * (`picoem-picocalc/crates/picocalc-board/src/framebuffer.rs`).
 *
 * That is the whole point. An application that draws the same picture
 * under both backends produces the same 64 hex characters here and in
 * `picocalc-run`'s `framebuffer.rgb565_sha256`, so a cheap host run can
 * be checked against a slow firmware one without a human comparing
 * pictures. Hashing a PNG instead would break that the first time either
 * side changed encoder settings, without the picture changing at all.
 *
 * The SHA-256 is implemented here rather than pulled in, because the
 * host build has no dependencies and this is ninety lines of FIPS 180-4
 * that never needs to change.
 */

#include <stdio.h>
#include <string.h>

#include <string>
#include <vector>

#include "picocalc/display.h"
#include "picocalc/host.h"

namespace picocalc::display::detail {
extern uint16_t g_framebuffer[];
}

namespace {

// --- SHA-256 (FIPS 180-4) ---------------------------------------------

constexpr uint32_t kK[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

uint32_t rotr(uint32_t x, unsigned n) {
    return (x >> n) | (x << (32 - n));
}

std::string sha256_hex(const uint8_t* data, size_t len) {
    uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                     0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};

    // Message + 0x80 + zero padding to 56 mod 64 + 64-bit big-endian length.
    std::vector<uint8_t> msg(data, data + len);
    msg.push_back(0x80);
    while (msg.size() % 64 != 56) {
        msg.push_back(0);
    }
    const uint64_t bits = static_cast<uint64_t>(len) * 8;
    for (int i = 7; i >= 0; --i) {
        msg.push_back(static_cast<uint8_t>((bits >> (i * 8)) & 0xFF));
    }

    for (size_t off = 0; off < msg.size(); off += 64) {
        uint32_t w[64];
        for (int i = 0; i < 16; ++i) {
            const uint8_t* p = &msg[off + i * 4];
            w[i] = (static_cast<uint32_t>(p[0]) << 24) |
                   (static_cast<uint32_t>(p[1]) << 16) |
                   (static_cast<uint32_t>(p[2]) << 8) | p[3];
        }
        for (int i = 16; i < 64; ++i) {
            const uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
            const uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        uint32_t a = h[0], b = h[1], c = h[2], d = h[3];
        uint32_t e = h[4], f = h[5], g = h[6], hh = h[7];
        for (int i = 0; i < 64; ++i) {
            const uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
            const uint32_t ch = (e & f) ^ (~e & g);
            const uint32_t t1 = hh + s1 + ch + kK[i] + w[i];
            const uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
            const uint32_t t2 = s0 + maj;
            hh = g; g = f; f = e; e = d + t1;
            d = c; c = b; b = a; a = t1 + t2;
        }
        h[0] += a; h[1] += b; h[2] += c; h[3] += d;
        h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
    }

    static const char* kHex = "0123456789abcdef";
    std::string out;
    out.reserve(64);
    for (uint32_t word : h) {
        for (int shift = 28; shift >= 0; shift -= 4) {
            out.push_back(kHex[(word >> shift) & 0xF]);
        }
    }
    return out;
}

/// Canonical bytes for a rectangle: row-major, little-endian RGB565.
std::vector<uint8_t> region_bytes(int x, int y, int w, int h) {
    std::vector<uint8_t> raw;
    if (w <= 0 || h <= 0) {
        return raw;
    }
    raw.reserve(static_cast<size_t>(w) * static_cast<size_t>(h) * 2);
    for (int row = y; row < y + h; ++row) {
        for (int col = x; col < x + w; ++col) {
            const uint16_t px = picocalc::host::pixel(col, row);
            raw.push_back(static_cast<uint8_t>(px & 0xFF));
            raw.push_back(static_cast<uint8_t>(px >> 8));
        }
    }
    return raw;
}

}  // namespace

namespace picocalc::host {

std::string framebuffer_sha256() {
    return region_sha256(0, 0, display::width, display::height);
}

std::string region_sha256(int x, int y, int w, int h) {
    const std::vector<uint8_t> raw = region_bytes(x, y, w, h);
    return sha256_hex(raw.data(), raw.size());
}

bool write_ppm(const char* path) {
    if (path == nullptr) {
        return false;
    }
    FILE* file = fopen(path, "wb");
    if (file == nullptr) {
        return false;
    }
    fprintf(file, "P6\n%d %d\n255\n", display::width, display::height);
    // Replicate the high bits into the low ones so a full-scale channel
    // reaches 0xFF, matching how the firmware backend expands RGB565 for
    // its PNGs. Without it every white would come out as 0xF8.
    for (int y = 0; y < display::height; ++y) {
        for (int x = 0; x < display::width; ++x) {
            const uint16_t p = pixel(x, y);
            const uint8_t r5 = static_cast<uint8_t>((p >> 11) & 0x1F);
            const uint8_t g6 = static_cast<uint8_t>((p >> 5) & 0x3F);
            const uint8_t b5 = static_cast<uint8_t>(p & 0x1F);
            const uint8_t rgb[3] = {
                static_cast<uint8_t>((r5 << 3) | (r5 >> 2)),
                static_cast<uint8_t>((g6 << 2) | (g6 >> 4)),
                static_cast<uint8_t>((b5 << 3) | (b5 >> 2)),
            };
            fwrite(rgb, 1, 3, file);
        }
    }
    return fclose(file) == 0;
}

}  // namespace picocalc::host
