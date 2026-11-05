# Adapted from Bloodborne-Android 2e472653 test_prepare_native.py: synthetic PS4 modules only.
from paths import ROOT
import struct
import zlib
from pathlib import Path
from link_libc import encode_id
from prepare import nid

FS_LOAD = bytes.fromhex('64488b042500000000')
LOAD_SIZE, LOAD_MEM = 0x2000, 0x3000
EXPORT, IMPORT = 0x12, 0x12


class Module:
    """Symbols are (name, info, shndx, value, size); relocs are (target, kind, symbol index, addend)."""

    def __init__(self, libs=None, mods=None, needed=(), tls=False, init=0, procparam=False):
        self.libs, self.mods = libs or {}, mods or {}
        self.needed, self.tls, self.init, self.procparam = list(needed), tls, init, procparam
        self.symbols, self.rela, self.plt = [('', 0, 0, 0, 0)], [], []
        self.code = bytearray(LOAD_SIZE)
        self.extra_ph = []
        self.spans = []  # byte ranges worth corrupting, in the plain ELF
        self.self_spans = []  # ... and in the SELF

    def build(self):
        strings = bytearray(b'\0')

        def s(name):
            if not name:
                return 0
            strings.extend(name.encode() + b'\0')
            return len(strings) - len(name.encode()) - 1
        dyn = []
        for tag, table in ((0x61000013, self.libs), (0x6100000d, self.mods)):
            for ident, (name, version) in table.items():
                dyn.append((tag, ident << 48 | version << 32 | s(name)))
        for name in self.needed:
            dyn.append((1, s(name)))
        sym = b''.join(struct.pack('<IBBHQQ', s(n), info, 0, shndx, value, size)
                       for n, info, shndx, value, size in self.symbols)
        pack = lambda r: struct.pack('<QQq', r[0], r[2] << 32 | r[1], r[3])
        rela, plt = b''.join(map(pack, self.rela)), b''.join(map(pack, self.plt))
        blob = bytes(strings)
        blob += bytes(-len(blob) % 8)
        str_size = len(strings)
        sym_off = len(blob)
        blob += sym
        rela_off = len(blob)
        blob += rela
        plt_off = len(blob)
        blob += plt
        dyn += [(0x61000035, 0), (0x61000037, str_size), (0x61000039, sym_off), (0x6100003f, len(sym)),
                (0x61000029, rela_off), (0x6100002d, len(rela)), (0x6100002f, plt_off), (0x61000031, len(plt))]
        if self.init:
            dyn.append((12, self.init))
        dyn.append((0, 0))
        dynamic = b''.join(struct.pack('<QQ', *d) for d in dyn)
        ph = [(1, 5, 0x1000, 0, LOAD_SIZE, LOAD_MEM, 0x1000)]
        if self.tls:
            ph.append((7, 4, 0x2800, 0x1800, 16, 32, 8))
        ph.append((2, 6, 0x3000, 0, len(dynamic), len(dynamic), 8))
        ph.append((0x61000000, 4, 0x4000, 0, len(blob), len(blob), 16))
        if self.procparam:
            ph.append((0x61000001, 4, 0x3800, 0x100, 0x40, 0x40, 8))
        ph += self.extra_ph
        header = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01\x01\x09', 2, 62, 1, 0xa0, 64, 0, 0, 64, 56,
                             len(ph), 64, 0, 0)
        body = bytearray(0x4000 + len(blob))
        body[:len(header)] = header
        for i, (t, f, off, va, fsz, msz, al) in enumerate(ph):
            struct.pack_into('<IIQQQQQQ', body, 64 + 56 * i, t, f, off, va, va, fsz, msz, al)
        body[0x1000:0x1000 + LOAD_SIZE] = self.code
        body[0x3000:0x3000 + len(dynamic)] = dynamic
        body[0x3800:0x3840] = bytes(range(64))
        body[0x4000:] = blob
        self.ph_table = ph
        self.spans = [(0, 64 + 56 * len(ph)), (0x3000, 0x3000 + len(dynamic)), (0x4000, 0x4000 + len(blob))]
        return bytes(body)

    def build_self(self, uncovered=()):
        elf = self.build()
        ph = self.ph_table
        header_end = 64 + 56 * len(ph)
        covered = [i for i, p in enumerate(ph) if p[4] and i not in uncovered]
        base = 32 + 32 * len(covered)
        out = bytearray(base + header_end)
        out[:4] = b'O\x15=\x1d'
        struct.pack_into('<H', out, 24, len(covered))
        out[base:base + header_end] = elf[:header_end]
        self.self_spans = [(0, len(out))]
        for n, i in enumerate(covered):
            t, f, off, va, fsz, msz, al = ph[i]
            struct.pack_into('<QQQQ', out, 32 + 32 * n, 0x800 | i << 20, len(out), fsz, fsz)
            if t in (2, 0x61000000):
                self.self_spans.append((len(out), len(out) + fsz))
            out += elf[off:off + fsz]
        return bytes(out)


def sfo(entries):
    """A param.sfo; values are str (UTF-8), bytes (raw string) or int (format 0x404)."""
    keys = b''.join(k.encode() + b'\0' for k in entries)
    values, rows, key_off, data_off = b'', b'', 0, 0
    for k, v in entries.items():
        if isinstance(v, int):
            raw, fmt = struct.pack('<I', v), 0x404
        else:
            raw, fmt = (v.encode() if isinstance(v, str) else v) + b'\0', 0x204
        rows += struct.pack('<HHIII', key_off, fmt, len(raw), len(raw), data_off)
        key_off += len(k) + 1
        data_off += len(raw)
        values += raw
    key_table = 20 + 16 * len(entries)
    return struct.pack('<4sIIII', b'\0PSF', 0x101, key_table, key_table + len(keys), len(entries)) + rows + keys + values


def synthetic_game(extra_main=None, init_env=b'\xc3'):
    """An eboot, libc.prx and libSceFios2.prx that exercise every path of the linker."""
    libs = {1: ('libc', 1), 2: ('libkernel', 1), 3: ('libSceLibcInternal', 1)}
    mods = {0: ('libc', 1), 1: ('libkernel', 1)}
    A, B, C, D = (encode_id(i) for i in (0, 1, 2, 3))
    main = Module(libs, mods, needed=['libc.prx', 'libSceFios2.prx', 'libkernel.prx'], tls=True, procparam=True)
    main.code[0x10:0x19] = FS_LOAD
    main.code[0x100:0x109] = FS_LOAD
    main.code[0x1ff7:0x2000] = FS_LOAD
    main.code[0x200:0x209] = FS_LOAD
    main.code[0x209:0x212] = FS_LOAD  # back to back
    main.code[0x300:0x306] = FS_LOAD[:6]  # incomplete: not patched
    main.symbols += [
        ('AAAAAAAAAAA#B#A', IMPORT, 0, 0, 0),                 # 1: bound to libc's export
        ('BBBBBBBBBBB#B#A', 0x11, 0, 0, 0),                   # 2: object import nobody exports
        ('LLLLLLLLLLL#B#A', EXPORT, 1, 0x40, 8),              # 3: defined in the eboot
        ('', 0x00, 0xfff1, 0x1234, 0),                        # 4: absolute
        ('xinternal00#' + D + '#' + A, IMPORT, 0, 0, 0),      # 5: libSceLibcInternal -> libc's same NID
        ('AAAAAAAAAAA#C#B', IMPORT, 0, 0, 0),                 # 6: libkernel, nobody exports
        ('plain_name', IMPORT, 0, 0, 0),                      # 7: not a NID#lib#module name
        ('dataobject00#B#A', 0x11, 0, 0, 0),                  # 8: libc's object export, with an addend
    ]
    main.rela = [(0x100, 8, 0, 0x500), (0x108, 1, 1, 0), (0x110, 7, 2, 8), (0x118, 6, 3, 0x10), (0x120, 1, 4, 5),
                 (0x128, 1, 5, 0), (0x130, 1, 6, 0), (0x138, 1, 7, 0), (0x140, 1, 1, 0), (0x148, 1, 8, 16),
                 (0x150, 8, 0, 0x600)]
    main.plt = [(0x200, 7, 1, 0), (0x208, 7, 5, 0), (0x2f0, 1, 2, 4095)]
    if extra_main:
        extra_main(main)
    libc = Module({1: ('libc', 1), 2: ('libkernel', 1)}, {0: ('libc', 1), 1: ('libkernel', 1)}, tls=True, init=0x50)
    libc.code[0x300] = init_env[0]
    libc.code[0x10:0x19] = FS_LOAD
    libc.symbols += [
        ('', 0x03, 0, 0, 0),                                   # 1: TLS descriptor symbol
        ('AAAAAAAAAAA#B#A', EXPORT, 1, 0x100, 4),
        ('xinternal00#B#A', EXPORT, 1, 0x200, 4),
        (nid('_init_env') + '#B#A', EXPORT, 1, 0x300, 1),
        ('dataobject00#B#A', 0x11, 1, 0x1500, 8),
        ('module_start', 0x20, 0, 0, 0),                       # 6: weak undefined
        ('kkkkkkkkkkk#C#B', IMPORT, 0, 0, 0),                  # 7: libkernel import
        (nid('_ZNSt8ios_base4InitC1Ev') + '#B#A', EXPORT, 1, 0x400, 2),
        ('', 0x00, 0xfff1, 0xabcdef, 0),                       # 9: absolute
        ('localdata000#B#A', 0x11, 1, 0x1600, 8),              # 10
    ]
    libc.rela = [(0x1000, 8, 0, 0x700), (0x1008, 16, 1, 0), (0x1010, 6, 6, 0), (0x1018, 7, 7, 0), (0x1020, 1, 9, 3),
                 (0x1028, 6, 10, 8)]
    libc.plt = [(0x1030, 7, 7, 0)]
    fios = Module({1: ('libc', 1), 4: ('libNotInMain', 2)}, {0: ('libc', 1), 5: ('libNotInMain', 1)})
    fios.code[0x20:0x29] = FS_LOAD
    fios.symbols += [
        ('ffffffffff#B#A', EXPORT, 1, 0x80, 4),
        ('AAAAAAAAAAA#B#A', IMPORT, 0, 0, 0),
        ('newimport000#B#A', IMPORT, 0, 0, 0),
        ('zzzzzzzzzzz#' + encode_id(4) + '#' + encode_id(5), IMPORT, 0, 0, 0),
        ('gggggggggg#B#A', 0x11, 1, 0x88, 8),
    ]
    fios.rela = [(0x1000, 8, 0, 1), (0x1008, 1, 2, 0), (0x1010, 7, 3, 0), (0x1018, 7, 4, 0)]
    return main, libc, fios


def write_game(path, main, libc, fios, params=None, as_self=(True, True, True)):
    path = Path(path)
    (path / 'sce_module').mkdir(parents=True, exist_ok=True)
    (path / 'sce_sys').mkdir(exist_ok=True)
    for module, name, wrap in zip((main, libc, fios), ('eboot.bin', 'sce_module/libc.prx', 'sce_module/libSceFios2.prx'),
                                  as_self):
        data = module if isinstance(module, bytes) else module.build_self() if wrap else module.build()
        (path / name).write_bytes(data)
    entries = {'TITLE': 'Test ™', 'TITLE_ID': 'CUSA01715', 'APP_VER': '01.02', 'USER_DEFINED_PARAM_1': 13}
    entries.update(params or {})
    (path / 'sce_sys/param.sfo').write_bytes(sfo(entries))
    return path
