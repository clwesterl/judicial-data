"""Minimal 7z reader on Python's standard library -- no p7zip or py7zr needed.

Kritzer ships the State Supreme Court Election Archive as .7z files (to get past
Dataverse's ingest step), and neither Python nor a stock R install reads 7z. This
covers what 7-Zip writes by default and what those archives use: LZMA, LZMA2, the
BCJ x86 filter, and stored (copy) streams, in solid or non-solid archives, with
plain or compressed headers. It does not handle encryption, BCJ2, PPMd, or
multi-volume archives; it says so and exits if it meets one.

    import un7z
    members = un7z.read("AllFiles.7z")        # {name: bytes}, archive order

    python un7z.py ARCHIVE [OUTDIR]           # extract (default: list)
"""
import lzma
import os
import struct
import sys

SIGNATURE = b"7z\xbc\xaf'\x1c"


class _R:
    def __init__(self, b):
        self.b, self.p = b, 0

    def byte(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def take(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def num(self):
        """7z variable-length integer: leading 1-bits of the first byte count extra bytes."""
        first, mask, val = self.byte(), 0x80, 0
        for i in range(8):
            if first & mask == 0:
                return val | ((first & (mask - 1)) << (8 * i))
            val |= self.byte() << (8 * i)
            mask >>= 1
        return val


def _bits(r, n):
    out, b, mask = [], 0, 0
    for _ in range(n):
        if mask == 0:
            b, mask = r.byte(), 0x80
        out.append(bool(b & mask))
        mask >>= 1
    return out


def _digests(r, n):
    defined = [True] * n if r.byte() else _bits(r, n)
    return [struct.unpack("<I", r.take(4))[0] if d else None for d in defined]


def _pack_info(r):
    pos, n, sizes = r.num(), r.num(), []
    while (t := r.byte()) != 0:
        if t == 0x09:
            sizes = [r.num() for _ in range(n)]
        elif t == 0x0A:
            _digests(r, n)
    return pos, sizes


def _folder(r):
    coders, n_in, n_out = [], 0, 0
    for _ in range(r.num()):
        flag = r.byte()
        cid = r.take(flag & 0x0F).hex()
        ni, no = (r.num(), r.num()) if flag & 0x10 else (1, 1)
        props = r.take(r.num()) if flag & 0x20 else b""
        if flag & 0x80:
            raise SystemExit("7z: alternative coder methods are not supported")
        coders.append({"id": cid, "ni": ni, "no": no, "props": props})
        n_in, n_out = n_in + ni, n_out + no
    binds = [(r.num(), r.num()) for _ in range(n_out - 1)]
    n_packed = n_in - len(binds)
    packed = [r.num() for _ in range(n_packed)] if n_packed > 1 else None
    return {"coders": coders, "binds": binds, "packed": packed, "n_out": n_out}


def _final_size(f):
    bound = {o for _, o in f["binds"]}
    return next(f["sizes"][i] for i in range(f["n_out"]) if i not in bound)


def _unpack_info(r):
    if r.byte() != 0x0B:
        raise SystemExit("7z: malformed unpack info")
    n = r.num()
    if r.byte() != 0:
        raise SystemExit("7z: external folder definitions are not supported")
    folders = [_folder(r) for _ in range(n)]
    if r.byte() != 0x0C:
        raise SystemExit("7z: malformed unpack sizes")
    for f in folders:
        f["sizes"] = [r.num() for _ in range(f["n_out"])]
    while (t := r.byte()) != 0:
        if t == 0x0A:
            _digests(r, n)
    return folders


def _substreams(r, folders):
    nums, sizes, t = [1] * len(folders), [], r.byte()
    if t == 0x0D:
        nums, t = [r.num() for _ in folders], r.byte()
    for f, k in zip(folders, nums):
        if k == 0:
            continue
        got = [r.num() for _ in range(k - 1)] if t == 0x09 else []
        sizes += got + [_final_size(f) - sum(got)]
    if t == 0x09:
        t = r.byte()
    while t != 0:
        if t == 0x0A:
            _digests(r, sum(nums))
        t = r.byte()
    return nums, sizes


def _streams_info(r):
    pack = folders = sub = None
    while (t := r.byte()) != 0:
        if t == 0x06:
            pack = _pack_info(r)
        elif t == 0x07:
            folders = _unpack_info(r)
        elif t == 0x08:
            sub = _substreams(r, folders)
    if sub is None:
        sub = ([1] * len(folders), [_final_size(f) for f in folders])
    return pack, folders, sub


def _filter(c):
    p = c["props"]
    if c["id"] == "21":                                    # LZMA2
        d = p[0]
        size = 0xFFFFFFFF if d >= 40 else (2 | (d & 1)) << (d // 2 + 11)
        return {"id": lzma.FILTER_LZMA2, "dict_size": size}
    if c["id"] == "030101":                                # LZMA
        d = p[0]
        return {"id": lzma.FILTER_LZMA1, "lc": d % 9, "lp": (d // 9) % 5, "pb": d // 45,
                "dict_size": struct.unpack("<I", p[1:5])[0]}
    if c["id"] == "03030103":                              # BCJ x86
        return {"id": lzma.FILTER_X86}
    if c["id"] == "00":                                    # copy
        return None
    if c["id"].startswith("06f1"):
        raise SystemExit("7z: archive is encrypted")
    raise SystemExit(f"7z: unsupported coder {c['id']}")


def _decode(data, f):
    if len(f["coders"]) > 2 or any(c["ni"] != 1 or c["no"] != 1 for c in f["coders"]):
        raise SystemExit("7z: multi-stream coders (e.g. BCJ2) are not supported")
    filters = [x for x in map(_filter, f["coders"]) if x]   # coder 0 is outermost
    size = _final_size(f)
    if not filters:
        return data[:size]
    out = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=filters).decompress(data, size)
    if len(out) != size:
        raise SystemExit(f"7z: decoded {len(out)} bytes, expected {size}")
    return out


def _folders_data(buf, pack, folders):
    pos, psizes = pack
    off, k, out = 32 + pos, 0, []
    for f in folders:
        n = 1 if f["packed"] is None else len(f["packed"])
        out.append(_decode(buf[off:off + psizes[k]], f))
        off += sum(psizes[k:k + n])
        k += n
    return out


def read(path):
    """Return {member name: bytes} for every file in a .7z archive, in archive order.
    Directories and empty files are skipped."""
    with open(path, "rb") as fh:
        buf = fh.read()
    if buf[:6] != SIGNATURE:
        raise SystemExit(f"{path}: not a 7z archive")
    off, size = struct.unpack("<QQ", buf[12:28])
    r = _R(buf[32 + off:32 + off + size])
    t = r.byte()
    while t == 0x17:                                       # compressed header
        pack, folders, _ = _streams_info(r)
        r = _R(_folders_data(buf, pack, folders)[0])
        t = r.byte()
    if t != 0x01:
        raise SystemExit("7z: malformed header")
    main = None
    names, empty, empty_file, n_files = [], [], [], 0
    while (t := r.byte()) != 0:
        if t == 0x04:
            main = _streams_info(r)
        elif t == 0x05:
            n_files = r.num()
            while (pt := r.byte()) != 0:
                sub = _R(r.take(r.num()))
                if pt == 0x0E:
                    empty = _bits(sub, n_files)
                elif pt == 0x0F:
                    empty_file = _bits(sub, sum(empty))
                elif pt == 0x11:
                    if sub.byte() != 0:
                        raise SystemExit("7z: external names are not supported")
                    names = sub.b[sub.p:].decode("utf-16-le").split("\x00")[:n_files]
        elif t != 0x02 and t != 0x03:
            raise SystemExit(f"7z: unexpected header property {t:#x}")
    empty = empty or [False] * n_files
    out = {}
    if main is None:
        return out
    pack, folders, (nums, sizes) = main
    data = _folders_data(buf, pack, folders)
    fi, within, pos, si = 0, 0, 0, 0
    for i, name in enumerate(names):
        if empty[i]:
            continue
        while nums[fi] == 0:
            fi += 1
        n = sizes[si]
        out[name.replace("\\", "/")] = data[fi][pos:pos + n]
        si, pos, within = si + 1, pos + n, within + 1
        if within == nums[fi]:
            fi, within, pos = fi + 1, 0, 0
    return out


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    members = read(argv[0])
    if len(argv) < 2:
        for name, b in members.items():
            print(f"{len(b):>12,}  {name}")
        return
    root = os.path.abspath(argv[1])
    for name, b in members.items():
        dst = os.path.abspath(os.path.join(root, name))
        if not dst.startswith(root + os.sep):
            raise SystemExit(f"7z: refusing to write outside {root}: {name}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(b)
        print(f"{len(b):>12,}  {name}")


if __name__ == "__main__":
    main(sys.argv[1:])
