#!/usr/bin/env python3
"""listener.py — one LoRa card, two networks, plus a local transmit door.

Semtech-UDP relay between the packet forwarder and the network servers:

    lora_pkt_fwd -> 127.0.0.1:1700 (here) -+-> 127.0.0.1:1680  helium_gateway (Helium)
                                           +-> TTN_SERVER      The Things Network (copy)

* Every received packet goes to BOTH networks and is logged to LORA_LOG (JSON lines).
* Helium owns the ACKs; from TTN only transmit requests (downlinks) are passed back.
* 127.0.0.1:1702 accepts {"txpk": {...}} from local programs and hands it to the forwarder
  (loopback only) — that is how loragw.py and tx_test.py transmit.

Environment: LORA_LOG, HELIUM_PORT (1680), TTN_SERVER ("host:port", "" to disable).
"""
import socket, json, base64, struct, time, os, threading
LOG = os.path.expanduser(os.environ.get("LORA_LOG", "~/lora/packets.jsonl"))
UPSTREAM = ("127.0.0.1", int(os.environ.get("HELIUM_PORT", "1680")))   # helium_gateway (gateway-rs)
# Second network server that gets a copy of every packet (The Things Network). Empty = off.
_ttn = os.environ.get("TTN_SERVER", "nam1.cloud.thethings.network:1700")
TTN = (_ttn.rsplit(":", 1)[0], int(_ttn.rsplit(":", 1)[1])) if _ttn else None
MTYPE = ["JoinRequest", "JoinAccept", "UnconfUp", "UnconfDown", "ConfUp", "ConfDown", "RejoinReq", "Proprietary"]

def network(devaddr):
    # Best-effort guess from the DevAddr prefix (NetID). Not authoritative.
    if devaddr >> 25 == 0x13: return "TTN"
    if devaddr >> 24 in (0x48, 0x78): return "Helium?"
    return "other"

def decode(raw):
    d = {"len": len(raw)}
    if not raw: return d
    mtype = raw[0] >> 5
    d["type"] = MTYPE[mtype]
    if mtype == 0 and len(raw) >= 23:
        d["join_eui"] = raw[1:9][::-1].hex(); d["dev_eui"] = raw[9:17][::-1].hex()
    elif mtype in (2, 3, 4, 5) and len(raw) >= 8:
        addr = struct.unpack("<I", raw[1:5])[0]
        d.update(devaddr=f"{addr:08x}", fcnt=struct.unpack("<H", raw[6:8])[0], net=network(addr))
    return d

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("127.0.0.1", 1700))
peers = {}   # forwarder socket address -> our upstream socket for it
clients = {"down": None}   # forwarder downstream (PULL_DATA) socket address
inj = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); inj.bind(("127.0.0.1", 1702))
def injector():
    """Local transmit injection (loopback only): JSON {"txpk": {...}} sent to
    127.0.0.1:1702 is wrapped as a PULL_RESP and handed to the forwarder."""
    token = 0
    while True:
        msg, addr = inj.recvfrom(65535)
        client = clients["down"]
        if addr[0] != "127.0.0.1" or client is None: continue
        try:
            body = json.loads(msg); tx = body["txpk"]; token = (token + 1) & 0xFFFF
            s.sendto(bytes([2]) + struct.pack(">H", token) + bytes([3]) + json.dumps(body).encode(), client)
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} TX[local] {tx.get('freq')} MHz {tx.get('datr')} {tx.get('powe')} dBm {tx.get('size')} B", flush=True)
        except Exception as e:
            print(f"INJECT error: {e}", flush=True)
threading.Thread(target=injector, daemon=True).start()

def pump(up, client, name="helium"):
    """Relay server replies back to one forwarder socket; note TX requests.
    Helium owns the ACKs; from TTN only transmit requests (PULL_RESP) are passed back."""
    while True:
        try: msg = up.recv(65535)
        except OSError: time.sleep(1); continue   # server not up yet / unreachable (boot race)
        if name != "helium" and (len(msg) < 4 or msg[3] != 0x03): continue
        s.sendto(msg, client)
        if len(msg) > 4 and msg[3] == 0x03:   # PULL_RESP = transmit request
            try:
                tx = json.loads(msg[4:])["txpk"]
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} TX[{name}] {tx.get('freq')} MHz {tx.get('datr')} "
                      f"{tx.get('powe')} dBm {tx.get('size')} B", flush=True)
            except Exception:
                pass

def upstream_for(client):
    up = peers.get(client)
    if up is None:
        up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); up.connect(UPSTREAM)
        peers[client] = up
        threading.Thread(target=pump, args=(up, client), daemon=True).start()
    return up

ttn_peers = {}; ttn_retry = 0
def ttn_for(client):
    global ttn_retry
    if TTN is None: return None
    up = ttn_peers.get(client)
    if up is None and time.time() > ttn_retry:
        try:
            up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); up.connect(TTN)
            ttn_peers[client] = up
            threading.Thread(target=pump, args=(up, client, "ttn"), daemon=True).start()
        except OSError:                       # DNS/network not ready; try again in a minute
            up = None; ttn_retry = time.time() + 60
    return up

os.makedirs(os.path.dirname(LOG), exist_ok=True)
with open(LOG, "a", buffering=1) as f:
    while True:
        msg, addr = s.recvfrom(65535)
        if len(msg) < 4: continue
        if msg[3] == 0x02: clients["down"] = addr   # PULL_DATA socket takes PULL_RESP
        try: upstream_for(addr).send(msg)
        except OSError: pass                  # gateway not listening yet; forwarder retries
        try:
            t = ttn_for(addr)
            if t: t.send(msg)
        except OSError: pass
        if msg[3] != 0x00: continue           # only PUSH_DATA carries packets/stats
        try: body = json.loads(msg[12:])
        except Exception: continue
        if "stat" in body: print("STAT", json.dumps(body["stat"]), flush=True)
        for p in body.get("rxpk", []):
            raw = base64.b64decode(p.get("data", ""))
            rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "freq": p.get("freq"), "datr": p.get("datr"),
                   "rssi": p.get("rssi"), "snr": p.get("lsnr"), "crc": p.get("stat"), **decode(raw), "hex": raw.hex()}
            f.write(json.dumps(rec) + "\n")
            who = rec.get('devaddr', rec.get('dev_eui', ''))
            print(f"{rec['t']} {rec['freq']:.1f} MHz {rec['datr']:>12} RSSI {rec['rssi']:>4} SNR {rec['snr']:>5} {rec.get('type','?'):>12} {who} {rec.get('net','')}", flush=True)
