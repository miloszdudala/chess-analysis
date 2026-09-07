"""Generate the 1024x1024 app icon used by bin/make-app.
Pure stdlib PNG writer (no Pillow), colours taken from the app's own palette."""
import struct, zlib

S = 1024
RADIUS = 232                     # macOS-ish corner rounding
INK   = (0x23, 0x21, 0x1d)       # --ink
CREAM = (0xfb, 0xfa, 0xf7)       # --bg
TEAL  = (0x1d, 0x6f, 0x6a)       # --accent

PAD = 190                        # board inset inside the rounded square
N = 4                            # 4x4 board reads cleanly even at 16px
CELL = (S - 2 * PAD) / N
SS = 3                           # 3x3 supersampling for smooth edges


def inside_round_rect(x, y, size, r):
    if x < r and y < r:
        return (x - r) ** 2 + (y - r) ** 2 <= r * r
    if x > size - r and y < r:
        return (x - (size - r)) ** 2 + (y - r) ** 2 <= r * r
    if x < r and y > size - r:
        return (x - r) ** 2 + (y - (size - r)) ** 2 <= r * r
    if x > size - r and y > size - r:
        return (x - (size - r)) ** 2 + (y - (size - r)) ** 2 <= r * r
    return True


def board_colour(x, y):
    """Colour at a point, or None if outside the board area."""
    if not (PAD <= x < S - PAD and PAD <= y < S - PAD):
        return None
    col = int((x - PAD) // CELL)
    row = int((y - PAD) // CELL)
    return CREAM if (col + row) % 2 == 0 else TEAL


rows = []
for py in range(S):
    row = bytearray()
    for px in range(S):
        r = g = b = a = 0
        for sy in range(SS):                     # supersample this pixel
            for sx in range(SS):
                x = px + (sx + 0.5) / SS
                y = py + (sy + 0.5) / SS
                if not inside_round_rect(x, y, S, RADIUS):
                    continue
                c = board_colour(x, y) or INK
                r += c[0]; g += c[1]; b += c[2]; a += 255
        n = SS * SS
        if a:                                    # premultiplied average
            cov = a / (255 * n)
            row += bytes((round(r / (n * cov)), round(g / (n * cov)),
                          round(b / (n * cov)), round(a / n)))
        else:
            row += b"\0\0\0\0"
    rows.append(bytes(row))

raw = b"".join(b"\x00" + r for r in rows)


def chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", S, S, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(raw, 9))
       + chunk(b"IEND", b""))

import sys
open(sys.argv[1], "wb").write(png)
print("wrote", sys.argv[1], len(png), "bytes")
