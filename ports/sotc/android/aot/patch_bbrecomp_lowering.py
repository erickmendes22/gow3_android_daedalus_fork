#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Patch the pinned bb-recomp v1.3.0 LLVM lowerer with SotC's missing IR ops.

The compiler still uses FEX IR as INPUT, not FEX JIT/TSO as a CPU backend.
This patch is applied to a private clone of the official compiler sources.
It must be compiled and unit-tested before being used for an Android AOT APK.
"""
from __future__ import annotations

import argparse
from pathlib import Path

MASKED_MEMORY = r"""
  // x86 VMASKMOV: inactive lanes must never access guest memory, including
  // unmapped pages. An unconditional vector load plus select is WRONG here.
  // Emit an explicit control-flow diamond for every potentially active lane.
  case OP_VLOADVECTORMASKED: {
    auto* o = op->C<IROp_VLoadVectorMasked>();
    if (isz != 16 || !(e == 1 || e == 2 || e == 4 || e == 8)) return false;
    auto* elemTy = I(e);
    auto* vecTy = VT(elemTy, 16 / e);
    Value* addr = memAddr(o->Addr, o->Offset, o->OffsetType, o->OffsetScale);
    Value* masks = lanesI(A(o->Mask), 16, e);
    Value* output = ConstantAggregateZero::get(vecTy);
    for (unsigned i = 0; i < 16 / e; ++i) {
      Value* mask = B.CreateExtractElement(masks, (uint64_t)i);
      Value* active = B.CreateICmpSLT(mask, ConstantInt::get(elemTy, 0));
      BasicBlock* start = curBB();
      BasicBlock* loadBB = newBB("sotc.masked.load");
      BasicBlock* doneBB = newBB("sotc.masked.done");
      B.CreateCondBr(active, loadBB, doneBB);
      B.SetInsertPoint(loadBB);
      Value* laneAddr = B.CreateAdd(addr, c64(i * e));
      auto* loaded = B.CreateAlignedLoad(elemTy, B.CreateIntToPtr(laneAddr, Ptr), Align(1));
      // The load must remain in the active-only block to preserve fault
      // suppression for lanes whose sign bit is 0.
      loaded->setVolatile(true);
      B.CreateBr(doneBB);
      B.SetInsertPoint(doneBB);
      PHINode* val = B.CreatePHI(elemTy, 2);
      val->addIncoming(ConstantInt::get(elemTy, 0), start);
      val->addIncoming(loaded, loadBB);
      output = B.CreateInsertElement(output, val, (uint64_t)i);
    }
    def(node, B.CreateBitCast(output, V128));
    return true;
  }
  case OP_VSTOREVECTORMASKED: {
    auto* o = op->C<IROp_VStoreVectorMasked>();
    if (isz != 16 || !(e == 1 || e == 2 || e == 4 || e == 8)) return false;
    auto* elemTy = I(e);
    Value* addr = memAddr(o->Addr, o->Offset, o->OffsetType, o->OffsetScale);
    Value* masks = lanesI(A(o->Mask), 16, e);
    Value* values = lanesI(A(o->Data), 16, e);
    for (unsigned i = 0; i < 16 / e; ++i) {
      Value* mask = B.CreateExtractElement(masks, (uint64_t)i);
      Value* active = B.CreateICmpSLT(mask, ConstantInt::get(elemTy, 0));
      BasicBlock* storeBB = newBB("sotc.masked.store");
      BasicBlock* doneBB = newBB("sotc.masked.done");
      B.CreateCondBr(active, storeBB, doneBB);
      B.SetInsertPoint(storeBB);
      Value* laneAddr = B.CreateAdd(addr, c64(i * e));
      Value* data = B.CreateExtractElement(values, (uint64_t)i);
      auto* store = B.CreateAlignedStore(data, B.CreateIntToPtr(laneAddr, Ptr), Align(1));
      store->setVolatile(true);
      B.CreateBr(doneBB);
      B.SetInsertPoint(doneBB);
    }
    return true;
  }

"""

STRING_COMPARE = r"""
  // Intermediate SSE4.2 PCMPISTRI/PCMPISTRM result used by the FEX decoder.
  // Low 16 bits = IntRes2. High nibble = SF,ZF,CF,OF in NZCV positions.
  // Implement the x86 implicit-length and four aggregation/polarity modes;
  // do not lower to a dummy zero or bbr_trap on libc.prx string routines.
  case OP_VPCMPISTRX: {
    auto* o = op->C<IROp_VPCMPISTRX>();
    const unsigned control = o->Control;
    const unsigned bytes = (control & 1) ? 2 : 1;
    const unsigned lanes = 16 / bytes;
    const unsigned dataMode = control & 3;
    const bool signedChar = (dataMode & 2) != 0;
    const unsigned aggregation = (control >> 2) & 3;
    const unsigned polarity = (control >> 4) & 3;
    auto* laneTy = I(bytes);
    auto* vectorTy = VT(laneTy, lanes);
    Value* lhsVector = B.CreateBitCast(A(o->LHS), vectorTy);
    Value* rhsVector = B.CreateBitCast(A(o->RHS), vectorTy);
    std::vector<Value*> lhs(lanes), rhs(lanes);
    Value* lhsLength = c32(lanes);
    Value* rhsLength = c32(lanes);
    for (unsigned i = 0; i < lanes; ++i) {
      Value* left = B.CreateExtractElement(lhsVector, (uint64_t)i);
      Value* right = B.CreateExtractElement(rhsVector, (uint64_t)i);
      lhsLength = B.CreateSelect(
          B.CreateAnd(B.CreateICmpEQ(left, ConstantInt::get(laneTy, 0)),
                      B.CreateICmpEQ(lhsLength, c32(lanes))),
          c32(i), lhsLength);
      rhsLength = B.CreateSelect(
          B.CreateAnd(B.CreateICmpEQ(right, ConstantInt::get(laneTy, 0)),
                      B.CreateICmpEQ(rhsLength, c32(lanes))),
          c32(i), rhsLength);
      lhs[i] = signedChar ? B.CreateSExt(left, I32) : B.CreateZExt(left, I32);
      rhs[i] = signedChar ? B.CreateSExt(right, I32) : B.CreateZExt(right, I32);
    }
    Value* intRes = c32(0);
    for (unsigned j = 0; j < lanes; ++j) {
      Value* rhsValid = B.CreateICmpULT(c32(j), rhsLength);
      Value* matched = B.getFalse();
      if (aggregation == 0) { // equal-any
        for (unsigned i = 0; i < lanes; ++i) {
          Value* ok = B.CreateAnd(
              B.CreateICmpULT(c32(i), lhsLength),
              B.CreateICmpEQ(lhs[i], rhs[j]));
          matched = B.CreateOr(matched, ok);
        }
        matched = B.CreateAnd(rhsValid, matched);
      } else if (aggregation == 1) { // unsigned/signed ranges
        for (unsigned i = 0; i + 1 < lanes; i += 2) {
          Value* valid = B.CreateICmpULT(c32(i + 1), lhsLength);
          Value* ge = B.CreateICmpSGE(rhs[j], lhs[i]);
          Value* le = B.CreateICmpSLE(rhs[j], lhs[i + 1]);
          matched = B.CreateOr(matched, B.CreateAnd(valid, B.CreateAnd(ge, le)));
        }
        matched = B.CreateAnd(rhsValid, matched);
      } else if (aggregation == 2) { // equal-each, both-invalid compares true
        Value* lhsValid = B.CreateICmpULT(c32(j), lhsLength);
        Value* bothValid = B.CreateAnd(lhsValid, rhsValid);
        Value* bothInvalid = B.CreateAnd(B.CreateNot(lhsValid), B.CreateNot(rhsValid));
        matched = B.CreateOr(bothInvalid,
                 B.CreateAnd(bothValid, B.CreateICmpEQ(lhs[j], rhs[j])));
      } else { // equal-ordered; short lhs matches all starting points
        Value* lhsEmpty = B.CreateICmpEQ(lhsLength, c32(0));
        Value* rhsFull = B.CreateICmpEQ(rhsLength, c32(lanes));
        Value* eligible = B.CreateAnd(rhsValid,
              B.CreateOr(rhsFull, B.CreateICmpULE(
                  B.CreateAdd(c32(j), lhsLength), rhsLength)));
        Value* equalPrefix = B.getTrue();
        for (unsigned i = 0; i + j < lanes; ++i) {
          Value* check = B.CreateAnd(
              B.CreateICmpULT(c32(i), lhsLength),
              B.CreateICmpULT(c32(i + j), rhsLength));
          Value* same = B.CreateICmpEQ(lhs[i], rhs[i + j]);
          equalPrefix = B.CreateAnd(equalPrefix,
                                   B.CreateOr(B.CreateNot(check), same));
        }
        matched = B.CreateOr(lhsEmpty, B.CreateAnd(eligible, equalPrefix));
      }
      intRes = B.CreateOr(intRes,
                 B.CreateShl(B.CreateZExt(matched, I32), c32(j)));
    }
    if (polarity == 1) {
      intRes = B.CreateXor(intRes, c32((1u << lanes) - 1));
    } else if (polarity == 3) {
      Value* validMask = B.CreateSub(B.CreateShl(c32(1), rhsLength), c32(1));
      intRes = B.CreateXor(intRes, validMask);
    }
    Value* zf = B.CreateICmpULT(rhsLength, c32(lanes));
    Value* sf = B.CreateICmpULT(lhsLength, c32(lanes));
    Value* cf = B.CreateICmpNE(intRes, c32(0));
    Value* of = B.CreateICmpNE(B.CreateAnd(intRes, c32(1)), c32(0));
    auto flag = [&](Value* predicate, unsigned bit) -> Value* {
      return B.CreateSelect(predicate, c32(1u << bit), c32(0));
    };
    Value* packed = B.CreateOr(
      intRes, B.CreateOr(flag(sf,31),
              B.CreateOr(flag(zf,30),
              B.CreateOr(flag(cf,29), flag(of,28)))));
    def(node, B.CreateZExt(packed, I64));
    return true;
  }

"""

def patch(file: Path) -> dict:
    source = file.read_text()
    marker = "  case OP_VLOADTWOGPRS: {"
    if source.count(marker) != 1:
        raise ValueError("Pinned v1.3.0 lower_vector.cpp site changed or already patched")
    if "case OP_VPCMPISTRX:" in source or "case OP_VSTOREVECTORMASKED:" in source:
        raise ValueError("Compiler already implements missing ops; inspect before patching")
    source=source.replace(marker, MASKED_MEMORY + STRING_COMPARE + marker, 1)
    # Keep a linker-retained, externally visible marker in the *compiled tool*.
    # A release packager can reject official unpatched bb-recomp even if it
    # presents the same upstream CLI version.
    signature='extern "C" __attribute__((used, retain, visibility("default"))) const char sotcAotLoweringSignature[] = "SOTC_AOT_MASKED_SSE42_JTRODATA_NO_TSO_2";\n'
    if source.count("using namespace llvm;") != 1:
        raise ValueError("Pinned source missing compiler signature insertion point")
    source=source.replace("using namespace llvm;", signature + "using namespace llvm;", 1)
    file.write_text(source)
    return {"file":str(file), "masked_load":True, "masked_store":True,
            "pcmpistrx":True, "no_tso":True, "no_bbr_trap_added":True}

def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("compiler_source",type=Path)
    args=ap.parse_args()
    target=args.compiler_source/"src/lower_vector.cpp"
    if not target.is_file():
        raise SystemExit(f"Missing upstream source: {target}")
    print(patch(target))

if __name__ == "__main__":
    main()
