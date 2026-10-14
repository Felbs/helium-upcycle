#!/usr/bin/env python3
"""tx_test.py [count] [gap_s] [sf] [text|hex:XX..] [cr 1-4] — transmit a KNOWN LoRa payload
from the gateway on 923.3 MHz BW125 (CRC on, explicit header, public sync 0x34)."""
import socket, json, base64, time, sys
n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
gap = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
sf = int(sys.argv[3]) if len(sys.argv) > 3 else 7
text = sys.argv[4] if len(sys.argv) > 4 else "HELLO SDR 0123456789"
cr = int(sys.argv[5]) if len(sys.argv) > 5 else 1
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for i in range(1, n + 1):
    data = bytes.fromhex(text[4:]) if text.startswith("hex:") else ("%s #%d" % (text, i)).encode()
    txpk = {"txpk": {"imme": True, "freq": 923.3, "rfch": 0, "powe": 20, "modu": "LORA",
                     "datr": "SF%dBW125" % sf, "codr": "4/%d" % (4 + cr), "ipol": False, "size": len(data),
                     "data": base64.b64encode(data).decode()}}
    s.sendto(json.dumps(txpk).encode(), ("127.0.0.1", 1702))
    print(time.strftime("%H:%M:%S"), "TX", len(data), "B hex", data.hex(), flush=True)
    time.sleep(gap)
