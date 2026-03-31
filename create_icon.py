"""ICO dosyası oluşturma betiği."""
import struct
import zlib
import math
import os


def create_png(w, h, px):
    """Minimal PNG oluştur."""
    def chunk(ct, d):
        c = ct + d
        crc = zlib.crc32(c) & 0xffffffff
        return struct.pack('>I', len(d)) + c + struct.pack('>I', crc)

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    raw = b''
    for y in range(h):
        raw += b'\x00'
        for x in range(w):
            i = (y * w + x) * 4
            raw += bytes([px[i], px[i + 1], px[i + 2], px[i + 3]])
    idat = chunk(b'IDAT', zlib.compress(raw, 9))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


def draw(sz):
    """Audio Sync ikonu çiz."""
    px = [0] * (sz * sz * 4)
    cx, cy = sz // 2, sz // 2
    r = sz // 2 - 2

    for y in range(sz):
        for x in range(sz):
            i = (y * sz + x) * 4
            dx, dy = x - cx, y - cy
            d = math.sqrt(dx * dx + dy * dy)

            if d <= r:
                t = d / r
                R = int(18 + t * 8)
                G = int(18 + t * 8)
                B = int(32 + t * 12)

                # Dış halka
                if abs(d - r * 0.92) < r * 0.035:
                    R, G, B = 108, 99, 255
                elif abs(d - r * 0.87) < r * 0.02:
                    R, G, B = 255, 101, 132

                # Sol dalga
                wl = cx - sz * 0.2
                wd = x - wl
                if abs(wd) < sz * 0.14:
                    a = sz * 0.18 * (1 - abs(wd) / (sz * 0.14))
                    if abs(y - cy - a * math.sin(wd * 0.18)) < max(2, sz * 0.022):
                        R, G, B = 108, 99, 255

                # Sağ dalga
                wr = cx + sz * 0.2
                wd2 = x - wr
                if abs(wd2) < sz * 0.14:
                    a2 = sz * 0.18 * (1 - abs(wd2) / (sz * 0.14))
                    if abs(y - cy - a2 * math.sin(wd2 * 0.18)) < max(2, sz * 0.022):
                        R, G, B = 255, 101, 132

                # Merkez nokta
                if dx * dx + dy * dy < (sz * 0.035) ** 2:
                    R, G, B = 232, 232, 240

                al = 255
                if d > r - 1.5:
                    al = max(0, int(255 * (r - d + 1.5) / 1.5))

                px[i] = max(0, min(255, R))
                px[i + 1] = max(0, min(255, G))
                px[i + 2] = max(0, min(255, B))
                px[i + 3] = max(0, min(255, al))
            else:
                px[i] = px[i + 1] = px[i + 2] = px[i + 3] = 0

    return px


def main():
    pngs = []
    for s in [48, 32, 16]:
        p = draw(s)
        pngs.append((s, create_png(s, s, p)))

    n = len(pngs)
    hdr = struct.pack('<HHH', 0, 1, n)
    off = 6 + n * 16
    d = b''
    for s, png in pngs:
        d += struct.pack('<BBBBHHII', s, s, 0, 0, 1, 32, len(png), off)
        off += len(png)

    ico = hdr + d
    for _, png in pngs:
        ico += png

    fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'audio_sync.ico')
    with open(fp, 'wb') as f:
        f.write(ico)
    print(f'Created: {fp} ({len(ico)} bytes)')


if __name__ == '__main__':
    main()
