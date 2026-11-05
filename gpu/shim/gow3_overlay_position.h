#pragma once

namespace Gow3Overlay {
struct Anchor { float x, y; };
// Existing corner values remain compatible with saved desktop settings.
constexpr Anchor Position(int corner) {
    switch (corner) {
    case 0: return {0.0f, 0.0f};
    case 2: return {0.0f, 1.0f};
    case 3: return {1.0f, 1.0f};
    case 4: return {0.5f, 0.0f};
    default: return {1.0f, 0.0f};
    }
}
}
