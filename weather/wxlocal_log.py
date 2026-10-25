#!/usr/bin/env python3
"""Log a Fine Offset WH65B (915 MHz) weather station heard by the LoRa concentrator (listen-only) to a JSONL file
(WX_OUT, default ~/weather/wxlocal.jsonl), one line per frame that passes the CRC-8 and the sum.
Put the station's 8-bit ID in wxlocal.json next to this script: {"station_id": 29}  (find it with decode_wh65.py, or
pick the station whose temperature matches your display). The ID is kept out of the log; if the station is a
neighbour's, keep it out of anything public too.
Radio: wxrx1302b at 915.0 MHz, 17241 bit/s 2-FSK, sync AA 2D D4, 40-byte raw blocks. Decoding per rtl_433 fineoffset.c
(WH24/WH65 family 0x24; WH65B factors: wind 0.51 m/s per unit (avg x0.125), rain 0.254 mm per tip)."""
import json, os, subprocess, time
from datetime import datetime, timezone
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("WX_OUT", os.path.expanduser("~/weather/wxlocal.jsonl"))
SID = json.load(open(os.path.join(HERE, "wxlocal.json")))["station_id"]
ENV = dict(os.environ, WX_DR="17241", WX_SYNC="AA2DD4", WX_SYNCLEN="3")

def crc8(d, c=0):
    for b in d:
        c ^= b
        for _ in range(8): c = ((c << 1) ^ 0x31) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c

def decode(b):
    if len(b) < 17 or b[0] != 0x24 or b[1] != SID: return None
    if (sum(b[:16]) & 0xFF) != b[16] or crc8(b[:15]) != b[15]: return None
    t_raw = (b[3] & 7) << 8 | b[4]; rh = b[5]
    wind_raw = b[6] | (b[3] & 0x10) << 4; gust_raw = b[7]
    rain_raw = b[8] << 8 | b[9]; uv_raw = b[10] << 8 | b[11]; light = b[12] << 16 | b[13] << 8 | b[14]
    r = {}
    if t_raw != 0x7FF: r["temp_f"] = round(((t_raw - 400) / 10) * 9 / 5 + 32, 1)
    if rh != 0xFF: r["rh"] = rh
    if wind_raw != 0x1FF: r["wind_mph"] = round(wind_raw * 0.125 * 0.51 * 2.23694, 1)
    if gust_raw != 0xFF: r["gust_mph"] = round(gust_raw * 0.51 * 2.23694, 1)
    r["wind_dir"] = b[2] | (b[3] & 0x80) << 1
    if rain_raw != 0xFFFF: r["rain_total_in"] = round(rain_raw * 0.254 / 25.4, 2)
    if uv_raw != 0xFFFF: r["uv_raw"] = uv_raw
    if light != 0xFFFFFF: r["lux"] = round(light / 10)
    r["batt_low"] = (b[3] >> 3) & 1
    return r

while True:
    p = subprocess.Popen([os.path.join(HERE, "wxrx1302b"), "3600"], cwd=HERE, env=ENV, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True)
    for line in p.stdout:
        if "size" not in line: continue
        try:
            rssi = float(line.split()[2]); b = bytes.fromhex("".join(line.split(":")[1].split()))
        except (ValueError, IndexError): continue
        r = decode(b)
        if r:
            with open(OUT, "a") as f:
                f.write(json.dumps({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), **r, "rssi": rssi}) + "\n")
    p.wait()
    if p.returncode != 0: time.sleep(30)
