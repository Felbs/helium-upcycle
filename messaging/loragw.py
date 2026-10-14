#!/usr/bin/env python3
"""loragw — gateway end of the LoRa command link (SX1302 card via packet forwarder).

  loragw daemon                   follow packets.jsonl, answer the laptop, serve the CLI
  loragw ping [--sf N]            round trip to the laptop
  loragw send "TEXT" [--sf N] [--wait S]
  loragw status                   this box's status line

Receives on the forwarder's channels (903.9-905.3 MHz), transmits on 923.3 MHz
through the listener's loopback inject door (127.0.0.1:1702).
Files: ~/lora/loralink.key ~/lora/loragw.state.json ~/lora/loragw.presets.json ~/lora/loragw.sock
"""
import base64, json, os, select, socket, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lcore

HOME = os.path.expanduser("~")
D = f"{HOME}/lora"
KEY, STATE, PRESETS, SOCK = f"{D}/loralink.key", f"{D}/loragw.state.json", f"{D}/loragw.presets.json", f"{D}/loragw.sock"
PKTS = f"{D}/packets.jsonl"
TX_FREQ, TX_DBM = 923.3, 26          # raised from 20 during drive 2 (user OK); SX1302 LUT max 27
HOST = socket.gethostname() if socket.gethostname() else "gateway"
DEFAULT_PRESETS = {"uptime": "uptime", "services": "systemctl is-active helium-gateway lora-pkt-fwd lora-listener | tr '\\n' ' '",
                   "lastpkts": "tail -3 ~/lora/packets.jsonl | cut -c1-70"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def _read(p, default=""):
    try:
        with open(p) as f: return f.read().strip()
    except Exception:
        return default


def status_text():
    up = float(_read("/proc/uptime", "0 0").split()[0])
    load = _read("/proc/loadavg", "? ").split()[0]
    t = _read("/sys/class/thermal/thermal_zone0/temp", "")
    temp = f"{int(t) // 1000}C" if t.isdigit() else "?"
    try:
        svc = subprocess.run(["systemctl", "is-active", "helium-gateway", "lora-pkt-fwd", "lora-listener"],
                             capture_output=True, text=True, timeout=5).stdout.split()
        svc = "/".join(s[:3] for s in svc)
    except Exception:
        svc = "?"
    try:
        hour_ago = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))
        tail = subprocess.run(["tail", "-n", "3000", PKTS], capture_output=True, text=True, timeout=5).stdout.splitlines()
        n = sum(1 for l in tail if json.loads(l).get("t", "") >= hour_ago)
    except Exception:
        n = "?"
    return f"{HOST} up {int(up // 3600)}h{int(up % 3600 // 60):02d} load {load} cpu {temp} svc {svc} pkts/1h {n}"[:230]


def presets():
    try:
        with open(PRESETS) as f: return json.load(f)
    except Exception:
        with open(PRESETS, "w") as f: json.dump(DEFAULT_PRESETS, f, indent=1)
        return dict(DEFAULT_PRESETS)


def handle_command(text):
    words = text.split(maxsplit=1)
    cmd = words[0].upper() if words else ""
    arg = words[1] if len(words) > 1 else ""
    if cmd == "PING":
        return f"PONG {HOST} {time.strftime('%H:%M:%S')}"
    if cmd == "STATUS":
        return status_text()
    if cmd == "RUN":
        p = presets()
        if arg not in p:
            return "ERR no preset " + arg[:20] + " (have: " + ",".join(sorted(p))[:150] + ")"
        try:
            r = subprocess.run(p[arg], shell=True, capture_output=True, text=True, timeout=25)
            return (r.stdout + r.stderr).strip()[:230] or f"(exit {r.returncode}, no output)"
        except subprocess.TimeoutExpired:
            return "ERR timeout"
    if cmd == "ASK":
        return "no agent here; ask the laptop"
    return "ERR unknown command"


class Radio:
    """TX through the listener's inject door; RX by following packets.jsonl."""
    def __init__(self):
        self.inj = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.f = open(PKTS)
        self.f.seek(0, 2)

    def tx(self, sf, data):
        txpk = {"txpk": {"imme": True, "freq": TX_FREQ, "rfch": 0, "powe": TX_DBM, "modu": "LORA",
                         "datr": f"SF{sf}BW125", "codr": "4/5", "ipol": False, "size": len(data),
                         "data": base64.b64encode(data).decode()}}
        self.inj.sendto(json.dumps(txpk).encode(), ("127.0.0.1", 1702))

    def rx(self):
        """Yield (sf, rssi, snr, bytes) for new frames of ours."""
        while True:
            line = self.f.readline()
            if not line: return
            try:
                r = json.loads(line)
                raw = bytes.fromhex(r["hex"])
            except Exception:
                continue
            if not raw.startswith(lcore.MAGIC) or r.get("crc") != 1:
                continue
            sf = int(r["datr"].split("BW")[0][2:])
            yield sf, r["rssi"], r["snr"], raw


def daemon():
    link = lcore.Link(KEY, STATE)
    radio = Radio()
    try: os.unlink(SOCK)
    except FileNotFoundError: pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK); os.chmod(SOCK, 0o600); srv.listen(8); srv.setblocking(False)
    pending = {}
    log("loragw daemon up; following", PKTS)
    while True:
        r, _, _ = select.select([srv] + [c for c, _, _ in pending.values()], [], [], 0.1)
        now = time.time()
        if srv in r:
            conn, _ = srv.accept()
            try:
                conn.settimeout(2)
                req = json.loads(conn.makefile().readline() or "{}")
                text = req.get("send", "")
                sf = int(req.get("sf", 7)); wait = float(req.get("wait", 20))
                frame, ctr = link.pack(lcore.T_CMD, text.encode()[: lcore.MAX_PAYLOAD])
                radio.tx(sf, frame)
                log(f"-> macbook sf{sf} #{ctr}: {text}")
                pending[ctr] = (conn, now + wait, now)
            except Exception as e:
                try: conn.sendall(json.dumps({"error": str(e)}).encode() + b"\n")
                except Exception: pass
                conn.close()
        for sf, rssi, snr, frame in radio.rx():
            try:
                typ, ctr, payload = link.unpack(frame)
            except lcore.BadFrame as e:
                log(f"RX rejected ({e}) rssi {rssi} len {len(frame)}"); continue
            if typ == lcore.T_CMD:
                text = payload.decode("utf-8", "replace")
                log(f"<- macbook #{ctr} sf{sf} rssi {rssi} snr {snr}: {text}")
                reply = handle_command(text)
                out, _ = lcore.pack_reply(link, ctr, reply)
                radio.tx(sf, out)
                log(f"-> reply #{ctr}: {reply[:80]}")
            elif typ == lcore.T_REPLY:
                cmd_ctr, text = lcore.split_reply(payload)
                log(f"<- reply to #{cmd_ctr} rssi {rssi} snr {snr}: {text[:80]}")
                if cmd_ctr in pending:
                    conn, _, t0 = pending.pop(cmd_ctr)
                    try:
                        conn.sendall(json.dumps({"reply": text, "rssi": rssi, "snr": snr,
                                                 "rtt": round(now - t0, 1)}).encode() + b"\n")
                    except Exception: pass
                    conn.close()
        for ctr in [c for c, (_, dl, _) in pending.items() if dl < now]:
            conn, _, _ = pending.pop(ctr)
            try: conn.sendall(b'{"error": "no reply"}\n')
            except Exception: pass
            conn.close()


def client(req):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCK)
    s.sendall(json.dumps(req).encode() + b"\n")
    s.settimeout(float(req.get("wait", 20)) + 5)
    data = s.makefile().readline()
    s.close()
    return json.loads(data or '{"error": "daemon closed"}')


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    cmd, rest = argv[0], argv[1:]
    opts = {"sf": 7, "wait": 20}
    args = []
    i = 0
    while i < len(rest):
        if rest[i] in ("--sf", "--wait"):
            opts[rest[i][2:]] = float(rest[i + 1]); i += 2
        else:
            args.append(rest[i]); i += 1
    if cmd == "daemon":
        daemon()
    elif cmd == "status":
        print(status_text())
    elif cmd in ("ping", "send"):
        text = "PING" if cmd == "ping" else " ".join(args)
        r = client({"send": text, "sf": int(opts["sf"]), "wait": opts["wait"]})
        if "reply" in r:
            print(f"{r['reply']}\n  [rssi {r['rssi']} snr {r['snr']} rtt {r['rtt']} s]")
        else:
            print("no answer:", r.get("error")); return 1
    else:
        print("unknown command", cmd); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
