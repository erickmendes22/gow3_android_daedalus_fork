#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Match Android SotC barycentric GS position IO to actual vertex shader IO.

The PC fallback's GS consumes and emits a gl_PerVertex Block containing
Position, PointSize, ClipDistance[1], CullDistance[1], while the preceding
SotC vertex shader emits a standalone BuiltIn Position variable and may emit
other separate BuiltIns. On Turnip, avoid an unnecessary mismatched block:
declare geometry gl_PerVertex blocks containing only BuiltIn Position.
The interpolation varyings (locations, qualifiers, barycentric vectors,
triangle ordering) are unchanged.
"""
from pathlib import Path

def patch_adreno_gs_position(gpu: Path):
    path=gpu/"shadps4/shader_recompiler/backend/spirv/emit_spirv_quad_rect.cpp"
    text=path.read_text()
    before='''    const Id float_arr{m.TypeArray(float_id, m.Constant(uint_id, 1U))};
    const Id per_vertex{m.TypeStruct(vec4_id, float_id, float_arr, float_arr)};
    m.Decorate(per_vertex, spv::Decoration::Block);
    m.MemberDecorate(per_vertex, 0U, spv::Decoration::BuiltIn, u32(spv::BuiltIn::Position));
    // sotc: matches the Invariant on the vertex shader's own position output
    // (EmitContext::DefineVertexBlock) - see the comment there.
    m.MemberDecorate(per_vertex, 0U, spv::Decoration::Invariant);
    m.MemberDecorate(per_vertex, 1U, spv::Decoration::BuiltIn, u32(spv::BuiltIn::PointSize));
    m.MemberDecorate(per_vertex, 2U, spv::Decoration::BuiltIn, u32(spv::BuiltIn::ClipDistance));
    m.MemberDecorate(per_vertex, 3U, spv::Decoration::BuiltIn, u32(spv::BuiltIn::CullDistance));'''
    after='''    // Android/Turnip: the vertex shader exports standalone BuiltIn Position,
    // not a gl_PerVertex Block. Using that same interface here also avoids
    // declaring unwritten PointSize/ClipDistance/CullDistance block members.
    // Do not touch parameter locations or barycentric interpolation.
    const Id gs_position_block{m.TypeStruct(vec4_id)};
    m.Decorate(gs_position_block, spv::Decoration::Block);
    m.MemberDecorate(gs_position_block, 0U, spv::Decoration::BuiltIn,
                     u32(spv::BuiltIn::Position));
    m.MemberDecorate(gs_position_block, 0U, spv::Decoration::Invariant);'''
    if text.count(before)!=1:
        raise ValueError(f"SotC GS position: expected one PC block declaration, saw {text.count(before)}")
    text=text.replace(before,after,1)
    before='''    const Id gl_in{variable(spv::StorageClass::Input,
                            m.TypeArray(per_vertex, m.Constant(uint_id, 3U)), std::nullopt)};
    const Id gl_out{variable(spv::StorageClass::Output, per_vertex, std::nullopt)};'''
    after='''    const Id gl_in{variable(spv::StorageClass::Input,
                            m.TypeArray(gs_position_block, m.Constant(uint_id, 3U)),
                            std::nullopt)};
    const Id gl_out{variable(spv::StorageClass::Output, gs_position_block, std::nullopt)};'''
    if text.count(before)!=1:
        raise ValueError(f"SotC GS position: expected one PC Position IO, saw {text.count(before)}")
    text=text.replace(before,after,1)
    before='''        const Id position{m.OpLoad(vec4_id, m.OpAccessChain(in_vec4, gl_in, index(v), index(0)))};
        m.OpStore(m.OpAccessChain(out_vec4, gl_out, index(0)), position);'''
    after='''        const Id position{m.OpLoad(vec4_id, m.OpAccessChain(in_vec4, gl_in, index(v), index(0)))};
        m.OpStore(m.OpAccessChain(out_vec4, gl_out, index(0)), position);'''
    if text.count(before)!=1:
        raise ValueError(f"SotC GS position: expected one vertex position loop, saw {text.count(before)}")
    text=text.replace(before,after,1)
    for guard in ["m.OpEmitVertex();", "m.OpEndPrimitive();",
                  "m.OpStore(bary_smooth, bary);", "m.OpStore(bary_nopersp, bary);",
                  "m.Decorate(out, spv::Decoration::Flat);"]:
        if guard not in text:
            raise ValueError(f"SotC GS: preserved varyings guard missing: {guard}")
    path.write_text(text)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--gpu",type=Path,required=True)
    patch_adreno_gs_position(p.parse_args().gpu)
