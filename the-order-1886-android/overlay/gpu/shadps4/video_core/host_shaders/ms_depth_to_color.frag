// SPDX-License-Identifier: GPL-2.0-or-later
#version 450 core
#extension GL_EXT_samplerless_texture_functions : require

// Inverse of color_to_ms_depth.frag, which expands R/G/B/A to MSAA depth
// sample indices 0/1/2/3. The Order aliases that same guest memory as an
// RGBA32 color texture again during depth effects. Resolving only sample 0
// would discard three channels and lose depth/lighting information.
layout (binding = 0, set = 0) uniform texture2DMS depth_ms;
layout (location = 0) out vec4 out_color;

void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    int samples = textureSamples(depth_ms);
    float s0 = texelFetch(depth_ms, pixel, 0).r;
    float s1 = samples > 1 ? texelFetch(depth_ms, pixel, 1).r : 0.0;
    float s2 = samples > 2 ? texelFetch(depth_ms, pixel, 2).r : 0.0;
    float s3 = samples > 3 ? texelFetch(depth_ms, pixel, 3).r : 1.0;
    out_color = vec4(s0, s1, s2, s3);
}
