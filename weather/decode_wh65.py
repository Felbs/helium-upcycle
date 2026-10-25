#!/usr/bin/env python3
"""Decode Fine Offset WH65B frames printed by wxrx1302 (sync AA 2D D4 -> the block starts at the family byte 0x24).
Integrity: CRC-8 poly 0x31 over bytes 0-14 == byte 15, and (sum of bytes 0-15) & 0xFF == byte 16.
usage: WX_DR=17241 WX_SYNC=AA2DD4 ./wxrx1302 3600 | python3 decode_wh65.py   (IDs masked: it may be a neighbour's station)"""
import sys

def crc8(d, c=0):
    for b in d:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x31) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c

for line in sys.stdin:
    if "size" not in line:
        continue
    b = bytes.fromhex("".join(line.split(":")[1].split()))
    if len(b) < 17 or b[0] != 0x24:
        continue
    ok = crc8(b[:15]) == b[15] and (sum(b[:16]) & 0xFF) == b[16]
    t_c = (((b[3] & 7) << 8 | b[4]) - 400) / 10
    wind = (b[6] | (b[3] & 0x10) << 4) * 0.125 * 0.51          # m/s (WH65B factor)
    print(f"{'ok ' if ok else 'BAD'} id=..{b[1] & 0xF:x} T={t_c:.1f}C RH={b[5]}% wind={wind:.1f}m/s gust={b[7]*0.51:.1f}m/s "
          f"dir={b[2] | (b[3] & 0x80) << 1} lux={(b[12] << 16 | b[13] << 8 | b[14]) / 10:.0f} uv_raw={b[10] << 8 | b[11]}")
