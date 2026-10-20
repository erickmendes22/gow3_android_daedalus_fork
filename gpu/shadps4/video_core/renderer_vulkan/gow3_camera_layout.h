// SPDX-License-Identifier: GPL-2.0-or-later
// CUSA01715: discover camera transforms from bound guest vertex constants.
// Do not assume Bloodborne's 864-byte buffer layout or hardcoded offsets.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>

namespace Gow3CameraLayout {
using Affine = std::array<float, 12>;
using Projection = std::array<float, 4>;
struct Pose {
    Affine view{}, inverse{};
    unsigned view_offset = 0, inverse_offset = 0;
    bool valid = false;
};
struct Lens {
    Projection projection{};
    unsigned offset = 0;
    bool valid = false;
};
inline bool Near(float a, float b, float eps = 0.025f) {
    return std::isfinite(a) && std::isfinite(b) && std::abs(a - b) <= eps;
}
inline float Matrix(const float* values, size_t start, int r, int c, bool column) {
    return values[start + (column ? c * 4 + r : r * 4 + c)];
}
inline bool ReadAffine(const float* values, size_t count, size_t start, bool column,
                       Affine& out) {
    if (start + 16 > count) return false;
    for (int c = 0; c < 3; ++c)
        if (!Near(Matrix(values, start, 3, c, column), 0.f, 0.002f)) return false;
    if (!Near(Matrix(values, start, 3, 3, column), 1.f, 0.002f)) return false;
    for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 4; ++c) {
            const float v = Matrix(values, start, r, c, column);
            if (!std::isfinite(v) || std::abs(v) > (c == 3 ? 1000000.f : 1.5f))
                return false;
            out[r * 4 + c] = v;
        }
    }
    // Camera view and inverse matrices have rigid orthonormal axes.
    for (int r = 0; r < 3; ++r) {
        float len = 0.f;
        for (int c = 0; c < 3; ++c) len += out[r * 4 + c] * out[r * 4 + c];
        if (!Near(len, 1.f, 0.06f)) return false;
        for (int other = 0; other < r; ++other) {
            float dot = 0.f;
            for (int c = 0; c < 3; ++c)
                dot += out[r * 4 + c] * out[other * 4 + c];
            if (!Near(dot, 0.f, 0.045f)) return false;
        }
    }
    return true;
}
inline bool InversePair(const Affine& a, const Affine& b) {
    float error = 0.f;
    for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 4; ++c) {
            float v = c == 3 ? a[r * 4 + 3] : 0.f;
            for (int k = 0; k < 3; ++k)
                v += a[r * 4 + k] * b[k * 4 + c];
            const float expected = c == r ? 1.f : 0.f;
            error = std::max(error, std::abs(v - expected));
        }
    }
    return error < 0.025f;
}
inline Pose FindPose(const float* data, size_t count) {
    Pose out{};
    if (!data || count < 32) return out;
    count = std::min(count, size_t(1024));
    for (size_t i = 0; i + 16 <= count; i += 4) {
        for (int format = 0; format < 2; ++format) {
            Affine a{};
            if (!ReadAffine(data, count, i, format != 0, a)) continue;
            const size_t end = std::min(count, i + 272);
            for (size_t j = i + 16; j + 16 <= end; j += 4) {
                for (int format2 = 0; format2 < 2; ++format2) {
                    Affine b{};
                    if (!ReadAffine(data, count, j, format2 != 0, b)) continue;
                    if (InversePair(a, b) && InversePair(b, a)) {
                        out.view = a; out.inverse = b;
                        out.view_offset = unsigned(i);
                        out.inverse_offset = unsigned(j);
                        out.valid = true;
                        return out;
                    }
                }
            }
        }
    }
    return out;
}
inline Lens FindProjection(const float* data, size_t count) {
    Lens out{};
    if (!data || count < 16) return out;
    count = std::min(count, size_t(1024));
    for (size_t i = 0; i + 16 <= count; i += 4) {
        for (int layout = 0; layout < 2; ++layout) {
            const bool col = layout != 0;
            const auto m = [&](int r, int c) { return Matrix(data, i, r, c, col); };
            const float sx = m(0,0), sy = m(1,1), z = m(2,2), dz = m(2,3);
            if (!(sx > 0.2f && sx < 12.f && sy > 0.2f && sy < 12.f &&
                  z > 0.5f && z < 1.5f && dz < -0.00001f && dz > -1000.f))
                continue;
            if (!Near(m(3,2), 1.f, .001f) || !Near(m(3,3), 0.f, .001f) ||
                !Near(m(0,1), 0.f, .001f) || !Near(m(1,0), 0.f, .001f) ||
                !Near(m(0,2), 0.f, .001f) || !Near(m(1,2), 0.f, .001f) ||
                !Near(m(3,0), 0.f, .001f) || !Near(m(3,1), 0.f, .001f)) continue;
            const float near_plane = -dz / z;
            if (!(near_plane > 0.0001f && near_plane < 1000.f)) continue;
            out.projection = {sx, sy, z, dz};
            out.offset = unsigned(i);
            out.valid = true;
            return out;
        }
    }
    return out;
}
inline bool SimilarPose(const Affine& a, const Affine& b, float threshold=.015f) {
    for (int i = 0; i < 12; ++i)
        if (std::abs(a[i] - b[i]) > threshold) return false;
    return true;
}

/**
 * CUSA01623 observed vertex constants:
 * - shader 05756ef0a3a4414c, slot 1, float offset 16: world->clip 4x4 (row-vector)
 * - shader 30e354c9bbe4f109, slot 0: projection with near 0.5, sy/sx=16/9
 * - world-space camera position independently matches slot 1 offset 160.
 *
 * For the GoW3 forward renderer B = View * Proj. Its first two columns are
 * scaled unit axes; the fourth column is the (positive) forward axis. With
 * depth = 1 - near / z, B[r][2] - B[r][3] = 0 for r < 3 and -near for r=3.
 * Unlike Bloodborne, there is NO view/inverse-view pair in the same block.
 *
 * Recover the row-vector View by dividing columns 0/1 by the projection
 * scales; transpose it to the column-vector 3x4 format CameraMotion uses.
 * Reject anything that is not a rigid and coherent GoW3 scene camera.
 */
struct GoW3ViewProjection {
    Affine view{}, inverse{};
    Projection projection{};
    std::array<float, 3> position{};
    float near_plane = 0.f;
    bool valid = false;
};
inline GoW3ViewProjection RecoverViewProjection(const float* data, size_t count,
                                                 unsigned buffer_slot) {
    GoW3ViewProjection out{};
    if (!data || buffer_slot != 1 || count < 32) return out;
    const float* b = data + 16;
    for (size_t i = 0; i < 16; ++i)
        if (!std::isfinite(b[i])) return out;
    // Offsets 16..31 are the proven 4x4 combined matrix, row-vector layout.
    // The values from the 2026-10-19 GoW3 eboot capture are close to
    // sx=1.975, sy=3.51, near=0.498 at 1280x720.
    float sx2 = 0.f, sy2 = 0.f, fw2 = 0.f;
    for (unsigned r = 0; r < 3; ++r) {
        sx2 += b[r * 4] * b[r * 4];
        sy2 += b[r * 4 + 1] * b[r * 4 + 1];
        fw2 += b[r * 4 + 3] * b[r * 4 + 3];
        if (std::abs(b[r * 4 + 2] - b[r * 4 + 3]) > 0.0005f)
            return out;
    }
    const float sx = std::sqrt(sx2), sy = std::sqrt(sy2);
    const float near = b[15] - b[14];
    if (!(sx > 1.25f && sx < 3.5f && sy > 2.f && sy < 6.5f &&
          std::abs(sy / sx - 16.f / 9.f) < 0.035f &&
          std::abs(fw2 - 1.f) < 0.025f &&
          near > 0.45f && near < 0.55f && std::abs(b[15]) > 5.f))
        return out;
    float row[4][4]{};
    for (unsigned r = 0; r < 4; ++r) {
        row[r][0] = b[r * 4] / sx;
        row[r][1] = b[r * 4 + 1] / sy;
        row[r][2] = b[r * 4 + 3];
        row[r][3] = r == 3 ? 1.f : 0.f;
    }
    for (unsigned r = 0; r < 3; ++r) {
        float length = 0.f;
        for (unsigned c = 0; c < 3; ++c)
            length += row[r][c] * row[r][c];
        if (std::abs(length - 1.f) > 0.035f) return out;
        for (unsigned k = 0; k < r; ++k) {
            float dot = 0.f;
            for (unsigned c = 0; c < 3; ++c)
                dot += row[r][c] * row[k][c];
            if (std::abs(dot) > 0.025f) return out;
        }
    }
    // Row-vector inverse: R^-1 = R^T, t^-1 = -t R^-1.
    float inverse[4][4]{};
    for (unsigned r = 0; r < 3; ++r)
        for (unsigned c = 0; c < 3; ++c)
            inverse[r][c] = row[c][r];
    for (unsigned r = 0; r < 3; ++r) {
        float t = 0.f;
        for (unsigned c = 0; c < 3; ++c)
            t -= row[3][c] * inverse[c][r];
        inverse[3][r] = t;
        out.position[r] = t;
        if (!std::isfinite(t) || std::abs(t) > 100000.f) return GoW3ViewProjection{};
    }
    for (unsigned r = 0; r < 3; ++r) {
        for (unsigned c = 0; c < 3; ++c) {
            // The CameraMotion shader uses column-vector 3x4 matrices,
            // transposed relative to GoW3's row-vector constants.
            out.view[r * 4 + c] = row[c][r];
            out.inverse[r * 4 + c] = inverse[c][r];
        }
        out.view[r * 4 + 3] = row[3][r];
        out.inverse[r * 4 + 3] = inverse[3][r];
    }
    // Reprojection uses positive forward-Z coordinates, so the GoW3
    // negative-Z projection becomes zScale=1 and depthOffset=-near.
    out.projection = {sx, sy, 1.f, -near};
    out.near_plane = near;
    out.valid = InversePair(out.view, out.inverse) &&
                InversePair(out.inverse, out.view);
    return out;
}

} // namespace Gow3CameraLayout
