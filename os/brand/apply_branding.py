#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Apply our branding to a ReactOS source tree.

What it changes (milestone 1: boot and setup only):
  * boot menu text in the FreeLoader .ini files
  * text-mode and graphical setup strings (English languages only)
  * the ProductName registry value
  * the kernel boot-screen logo bitmaps, redrawn from scratch at the same size and palette

What it never changes: copyright, licence, credit and URL strings, file paths,
identifiers, comments. ReactOS stays credited everywhere it credits itself.

Every group of changes is checked. If upstream moved a file and a required group
finds nothing, the script finishes the whole run, prints what it could not find,
and exits non-zero so the build stops instead of shipping half-branded.
"""
import argparse
import configparser
import glob
import os
import re
import struct
import sys
from collections import Counter

WORD = re.compile(r"\bReactOS\b")
C_STRING = re.compile(r'"((?:[^"\\\n]|\\.)*)"')

# A string containing any of these is credit/licence text and is left alone.
PROTECT = re.compile(
    r"ReactOS\s+(Team|Project|Foundation|Deutschland|Development|developers|contributors|Authors)"
    r"|reactos\.org|https?://|copyright|\(c\)|©|licen[cs]|based on|GNU|GPL",
    re.IGNORECASE,
)


def is_protected_c(s):
    # Escaped backslash ("C:\\ReactOS"), drive letters, slashes and file names are paths.
    return bool(PROTECT.search(s) or "\\\\" in s or "/" in s
                or re.search(r"[A-Za-z]:", s) or re.search(r"ReactOS\.\w", s))


def is_protected_ini(s):
    return bool(PROTECT.search(s) or "\\" in s or "/" in s or re.search(r"ReactOS\.\w", s))


def read_text(path):
    raw = open(path, "rb").read()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252"), "cp1252"


def write_text(path, text, enc):
    with open(path, "w", encoding=enc, newline="") as f:
        f.write(text)


def skip_line(line):
    t = line.strip()
    return (t.startswith(("//", "/*", "*", "#include", "#pragma", ";"))
            or t.upper().startswith(("LANGUAGE ", "#DEFINE IDS_")) and '"' not in t)


def brand_c_like(text, name, report, path):
    """Replace ReactOS inside C/RC string literals only."""
    out, n = [], 0
    for line in text.splitlines(keepends=True):
        if skip_line(line) or "ReactOS" not in line:
            out.append(line)
            continue

        def sub(m):
            nonlocal n
            s = m.group(1)
            if "ReactOS" not in s or is_protected_c(s):
                return m.group(0)
            new, k = WORD.subn(name, s)
            n += k
            if k:
                report.append(f"    {path}: \"{s[:70]}\" -> \"{new[:70]}\"")
            return f'"{new}"'

        out.append(C_STRING.sub(sub, line))
    return "".join(out), n


INI_DISPLAY_KEYS = {"titletext", "timetext", "bootmanagername"}


def brand_ini(text, name, report, path, only_keys=None):
    """Replace ReactOS in ini/inf values: quoted values, and unquoted display keys."""
    out, n = [], 0
    for line in text.splitlines(keepends=True):
        t = line.strip()
        if not t or t.startswith((";", "[")) or "ReactOS" not in line:
            out.append(line)
            continue
        if only_keys and not any(k.lower() in line.lower() for k in only_keys):
            out.append(line)
            continue
        new_line = line
        if "=" in line and '"' not in line.split("=", 1)[1]:
            key, val = line.split("=", 1)
            if key.strip().lower() in INI_DISPLAY_KEYS and not is_protected_ini(val):
                nv, k = WORD.subn(name, val)
                if k:
                    n += k
                    new_line = key + "=" + nv
                    report.append(f"    {path}: {t[:70]} -> {new_line.strip()[:70]}")
        else:
            # Only touch quoted strings to the right of '=' (left side is an identifier).
            head, sep, tail = line.partition("=") if "=" in line else ("", "", line)

            def sub(m):
                nonlocal n
                s = m.group(1)
                if "ReactOS" not in s or is_protected_ini(s):
                    return m.group(0)
                new, k = WORD.subn(name, s)
                n += k
                return f'"{new}"'

            new_tail = C_STRING.sub(sub, tail)
            if new_tail != tail:
                new_line = head + sep + new_tail
                report.append(f"    {path}: {t[:70]} -> {new_line.strip()[:70]}")
        out.append(new_line)
    return "".join(out), n


# (group, glob patterns relative to the source root, handler, required, extra)
GROUPS = [
    ("boot menu", ["boot/bootdata/*.ini", "boot/bootdata/**/*.ini", "boot/freeldr/**/*.ini"],
     "ini", True, None),
    ("text-mode setup", ["base/setup/usetup/lang/en-US.h", "base/setup/usetup/lang/en-GB.h"],
     "c", True, None),
    ("graphical setup", ["base/setup/*/lang/en-US.rc", "base/setup/*/lang/en-GB.rc",
                         "base/setup/*/*/lang/en-US.rc", "base/setup/*/*/lang/en-GB.rc"],
     "c", True, None),
    ("product name", ["boot/bootdata/hivesft.inf", "boot/bootdata/hivesys.inf"],
     "ini", True, ["ProductName"]),
]


def apply_strings(root, name, report):
    missing = []
    for group, patterns, kind, required, keys in GROUPS:
        files = sorted({f for p in patterns for f in glob.glob(os.path.join(root, p), recursive=True)})
        total = 0
        report.append(f"[{group}] {len(files)} candidate file(s)")
        for f in files:
            rel = os.path.relpath(f, root)
            text, enc = read_text(f)
            if kind == "c":
                new, n = brand_c_like(text, name, report, rel)
            else:
                new, n = brand_ini(text, name, report, rel, keys)
            if n:
                write_text(f, new, enc)
                total += n
        report.append(f"[{group}] {total} replacement(s)\n")
        if required and total == 0:
            missing.append(f"{group}: looked in {', '.join(patterns)}")
    return missing


# ---------------------------------------------------------------- bitmaps

class Bmp:
    def __init__(self, path):
        d = open(path, "rb").read()
        if d[:2] != b"BM":
            raise ValueError("not a BMP")
        self.off = struct.unpack_from("<I", d, 10)[0]
        hsize = struct.unpack_from("<I", d, 14)[0]
        self.w, h, _, self.bpp, self.comp, _, _, _, clr_used, _ = struct.unpack_from("<iiHHIIiiII", d, 18)
        self.topdown = h < 0
        self.h = abs(h)
        if self.bpp not in (1, 4, 8, 24) or self.comp not in (0, 1, 2):
            raise ValueError(f"unsupported BMP ({self.bpp} bpp, compression {self.comp})")
        ncol = clr_used or (1 << self.bpp if self.bpp <= 8 else 0)
        p = 14 + hsize
        self.palette = [(d[p + 4 * i + 2], d[p + 4 * i + 1], d[p + 4 * i]) for i in range(ncol)]
        self.header = bytearray(d[:p + 4 * ncol])
        self.pixels = self._decode(d)

    def _decode(self, d):
        w, h = self.w, self.h
        px = [[0] * w for _ in range(h)]
        if self.comp == 0:
            stride = ((w * self.bpp + 31) // 32) * 4
            for row in range(h):
                y = row if self.topdown else h - 1 - row
                base = self.off + row * stride
                for x in range(w):
                    if self.bpp == 24:
                        b, g, r = d[base + 3 * x: base + 3 * x + 3]
                        px[y][x] = (r, g, b)
                    elif self.bpp == 8:
                        px[y][x] = d[base + x]
                    elif self.bpp == 4:
                        v = d[base + x // 2]
                        px[y][x] = (v >> 4) if x % 2 == 0 else (v & 15)
                    else:
                        px[y][x] = (d[base + x // 8] >> (7 - x % 8)) & 1
            return px
        # RLE8 / RLE4, bottom-up
        i, x, row = self.off, 0, 0
        while i < len(d) - 1 and row < h:
            a, b = d[i], d[i + 1]
            i += 2
            if a:
                for k in range(a):
                    v = b if self.comp == 1 else ((b >> 4) if k % 2 == 0 else (b & 15))
                    if x < w:
                        px[h - 1 - row][x] = v
                    x += 1
            elif b == 0:
                x, row = 0, row + 1
            elif b == 1:
                break
            elif b == 2:
                x, row = x + d[i], row + d[i + 1]
                i += 2
            else:
                nbytes = b if self.comp == 1 else (b + 1) // 2
                for k in range(b):
                    v = d[i + k] if self.comp == 1 else ((d[i + k // 2] >> 4) if k % 2 == 0 else (d[i + k // 2] & 15))
                    if x < w and row < h:
                        px[h - 1 - row][x] = v
                    x += 1
                i += nbytes + (nbytes & 1)
        return px

    def save(self, path):
        """Write uncompressed, same size, bit depth and palette as the original."""
        w, h, bpp = self.w, self.h, self.bpp
        stride = ((w * bpp + 31) // 32) * 4
        body = bytearray()
        rows = range(h) if self.topdown else range(h - 1, -1, -1)
        for y in rows:
            line = bytearray(stride)
            for x in range(w):
                v = self.pixels[y][x]
                if bpp == 24:
                    line[3 * x:3 * x + 3] = bytes((v[2], v[1], v[0]))
                elif bpp == 8:
                    line[x] = v
                elif bpp == 4:
                    line[x // 2] |= (v << 4) if x % 2 == 0 else v
                else:
                    line[x // 8] |= v << (7 - x % 8)
            body += line
        hdr = bytearray(self.header)
        struct.pack_into("<I", hdr, 2, len(hdr) + len(body))   # file size
        struct.pack_into("<I", hdr, 10, len(hdr))               # pixel offset
        struct.pack_into("<I", hdr, 30, 0)                      # BI_RGB
        struct.pack_into("<I", hdr, 34, len(body))              # image size
        open(path, "wb").write(hdr + body)


def nearest(palette, rgb, exclude=()):
    best = min((i for i in range(len(palette)) if i not in exclude),
               key=lambda i: sum((a - b) ** 2 for a, b in zip(palette[i], rgb)))
    return best


def hex_rgb(s):
    s = s.strip().lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def load_font(size, bold=True):
    from PIL import ImageFont
    for p in (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold else []) + [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def redraw(bmp, brand, logo_cfg):
    from PIL import Image, ImageDraw
    w, h = bmp.w, bmp.h
    flat = [v for row in bmp.pixels for v in row]
    bg = Counter(flat).most_common(1)[0][0]
    if bmp.bpp == 24:
        fg, cr = hex_rgb(logo_cfg["text_colour"]), hex_rgb(logo_cfg["credit_colour"])
    else:
        fg = nearest(bmp.palette, hex_rgb(logo_cfg["text_colour"]), exclude={bg})
        cr = nearest(bmp.palette, hex_rgb(logo_cfg["credit_colour"]), exclude={bg})

    layers = []  # (mask, colour)
    full_screen = w >= 320 and h >= 200
    # Name: as large as fits in 80% of the width and ~35% of the height (smaller on full screens).
    size = max(8, int(h * (0.12 if full_screen else 0.6)))
    font = load_font(size)
    while size > 8:
        bx = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), brand["name"], font=font)
        if bx[2] - bx[0] <= w * 0.8 and bx[3] - bx[1] <= h * (0.2 if full_screen else 0.8):
            break
        size -= 1
        font = load_font(size)
    m = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(m)
    bx = dr.textbbox((0, 0), brand["name"], font=font)
    tw, th = bx[2] - bx[0], bx[3] - bx[1]
    cy = int(h * 0.38) if full_screen else h // 2
    dr.text(((w - tw) // 2 - bx[0], cy - th // 2 - bx[1]), brand["name"], font=font, fill=255)
    layers.append((m, fg))

    if full_screen:
        for text, rel_y, frac in ((brand.get("tagline", ""), 0.38 + 0.13, 0.045),
                                  (brand.get("credit", ""), 0.94, 0.035)):
            if not text:
                continue
            f2 = load_font(max(8, int(h * frac)), bold=False)
            m2 = Image.new("L", (w, h), 0)
            d2 = ImageDraw.Draw(m2)
            b2 = d2.textbbox((0, 0), text, font=f2)
            d2.text(((w - (b2[2] - b2[0])) // 2 - b2[0], int(h * rel_y) - (b2[3] - b2[1]) // 2 - b2[1]),
                    text, font=f2, fill=255)
            layers.append((m2, cr))

    px = [[bg] * w for _ in range(h)]
    for mask, colour in layers:
        data = mask.load()
        for y in range(h):
            for x in range(w):
                if data[x, y] >= 128:
                    px[y][x] = colour
    bmp.pixels = px


LOGO_ID = re.compile(r"LOGO|BOOT_SCREEN|BOOTSCREEN|SPLASH", re.I)
LOGO_SKIP = re.compile(r"COPYRIGHT|TEXT|BAR|PROGRESS|ROTAT|SHUTDOWN|LINE", re.I)
RC_BITMAP = re.compile(r'^\s*(\w+)\s+BITMAP\s+(?:[A-Z]+\s+)*"?([^"\s]+\.bmp)"?', re.I | re.M)


def apply_logos(root, brand, logo_cfg, report, dry_run=False):
    found = []
    report.append("[boot logo] bitmap resources under ntoskrnl/:")
    for rc in sorted(glob.glob(os.path.join(root, "ntoskrnl", "**", "*.rc"), recursive=True)):
        text, _ = read_text(rc)
        for ident, rel in RC_BITMAP.findall(text):
            path = os.path.normpath(os.path.join(os.path.dirname(rc), rel.replace("\\", "/")))
            pick = bool(LOGO_ID.search(ident)) and not LOGO_SKIP.search(ident)
            report.append(f"    {'REPLACE' if pick else 'keep   '} {ident:28} {os.path.relpath(path, root)}")
            if pick and os.path.exists(path):
                found.append((ident, path))
    replaced = 0
    for ident, path in found:
        try:
            bmp = Bmp(path)
        except ValueError as e:
            report.append(f"    ! {ident}: {e}")
            continue
        redraw(bmp, brand, logo_cfg)
        if not dry_run:
            bmp.save(path)
        replaced += 1
        report.append(f"    redrew {ident} ({bmp.w}x{bmp.h}, {bmp.bpp} bpp)")
    report.append(f"[boot logo] {replaced} bitmap(s) redrawn\n")
    return [] if replaced else ["boot logo: no LOGO/BOOT_SCREEN bitmap resources found in ntoskrnl/**/*.rc"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="ReactOS source tree")
    ap.add_argument("--brand", default=os.path.join(os.path.dirname(__file__), "brand.ini"))
    ap.add_argument("--report", help="write the change report here too")
    ap.add_argument("--preview", help="also save PNG previews of redrawn bitmaps into this folder")
    a = ap.parse_args()

    cp = configparser.ConfigParser(interpolation=None)
    cp.read(a.brand, encoding="utf-8")
    brand, logo_cfg = dict(cp["brand"]), dict(cp["logo"])
    if not os.path.isdir(os.path.join(a.source, "ntoskrnl")):
        sys.exit(f"{a.source} doesn't look like a ReactOS source tree (no ntoskrnl/)")

    report = [f"Branding '{brand['name']}' onto {a.source}\n"]
    missing = apply_strings(a.source, brand["name"], report)
    missing += apply_logos(a.source, brand, logo_cfg, report)

    if a.preview:
        from PIL import Image
        os.makedirs(a.preview, exist_ok=True)
        for line in report:
            if line.strip().startswith("REPLACE"):
                rel = line.split()[-1]
                p = os.path.join(a.source, rel)
                if os.path.exists(p):
                    Image.open(p).convert("RGB").save(os.path.join(a.preview, os.path.basename(p) + ".png"))

    if missing:
        report.append("NOT FOUND (upstream layout changed? update brand/apply_branding.py):")
        report += [f"  - {m}" for m in missing]
    text = "\n".join(report) + "\n"
    print(text)
    if a.report:
        open(a.report, "w", encoding="utf-8").write(text)
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
