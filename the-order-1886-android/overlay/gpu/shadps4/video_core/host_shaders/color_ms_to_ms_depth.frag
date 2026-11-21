// SPDX-License-Identifier: GPL-2.0-or-later
#version 450 core
#extension GL_EXT_samplerless_texture_functions : require
layout(set = 0, binding = 0) uniform texture2DMS color_ms;
void main() {
    gl_FragDepth = texelFetch(color_ms, ivec2(gl_FragCoord.xy), gl_SampleID).r;
}
