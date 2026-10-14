#!/usr/bin/env python3
"""loralink — laptop end of the LoRa command link (Heltec V3 modem on USB).

  loralink daemon                 own the modem, answer gateway, serve the CLI
  loralink ping [--sf N]          round trip to gateway
  loralink send "TEXT" [--sf N] [--wait S]
  loralink status                 print this machine's status line (what STATUS sends)

Config: ~/.config/loralink/{key,state.json,presets.json,status.d/}
Socket: $XDG_RUNTIME_DIR/loralink.sock
"""
import json, os, select, socket, subprocess, sys, time, glob, shlex

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lcore

CONF = os.path.expanduser("~/.config/loralink")
KEY, STATE = f"{CONF}/key", f"{CONF}/state.json"
PRESETS = f"{CONF}/presets.json"
SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "loralink.sock")
PORT = os.environ.get("LORALINK_PORT", "/dev/ttyUSB0")
HOST = socket.gethostname()
DEFAULT_PRESETS = {"uptime": "uptime", "disk": "df -h / | tail -1", "mem": "free -m | sed -n 2p"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- status
def _read(p, default=""):
    try:
        with open(p) as f: return f.read().strip()
    except Exception:
        return default


def status_text():
    up = float(_read("/proc/uptime", "0 0").split()[0])
    load = _read("/proc/loadavg", "? ").split()[0]
    bat = _read("/sys/class/power_supply/BAT0/capacity", "?")
    bst = _read("/sys/class/power_supply/BAT0/status", "")[:1]      # C/D/F
    try:
        wifi = subprocess.run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], capture_output=True, text=True, timeout=5).stdout
        ssid = next((l.split(":", 1)[1] for l in wifi.splitlines() if l.startswith("yes:")), "-")
    except Exception:
        ssid = "?"
    try:
        ipj = json.loads(subprocess.run(["ip", "-j", "-4", "addr"], capture_output=True, text=True, timeout=5).stdout)
        ip = next((a["local"] for i in ipj for a in i.get("addr_info", []) if i["ifname"] != "lo"), "-")
    except Exception:
        ip = "?"
    rsp = any(_read(f"{d}/idVendor") == "1df7" for d in glob.glob("/sys/bus/usb/devices/*"))
    try:
        ps = subprocess.run(["ps", "-eo", "pcpu,comm", "--sort=-pcpu"], capture_output=True, text=True, timeout=5).stdout.splitlines()[1:3]
        top = ",".join(f"{l.split()[1][:12]}:{float(l.split()[0]):.0f}%" for l in ps if l.strip())
    except Exception:
        top = "?"
    parts = [f"{HOST} up {int(up // 3600)}h{int(up % 3600 // 60):02d} load {load} bat {bat}%{bst}",
             f"wifi {ssid} ip {ip} rspdx {'yes' if rsp else 'no'} top {top}"]
    for s in sorted(glob.glob(f"{CONF}/status.d/*")):
        if os.access(s, os.X_OK):
            try:
                out = subprocess.run([s], capture_output=True, text=True, timeout=10).stdout.strip()
                parts.append(f"{os.path.basename(s)}: {out[:60]}")
            except Exception as e:
                parts.append(f"{os.path.basename(s)}: err")
    return " | ".join(parts)[:230]


def presets():
    try:
        with open(PRESETS) as f: return json.load(f)
    except Exception:
        with open(PRESETS, "w") as f: json.dump(DEFAULT_PRESETS, f, indent=1)
        return dict(DEFAULT_PRESETS)


def handle_command(text):
    """A command that arrived over the air. Only whitelisted things happen here."""
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
        return "no local agent yet"
    return "ERR unknown command"


# ---------------------------------------------------------------- modem
class Modem:
    def __init__(self, port):
        import serial
        self.ser = serial.Serial(port, 115200, timeout=0)
        self.buf = b""
        self.ready = False

    def fileno(self): return self.ser.fileno()

    def write_line(self, s):
        self.ser.write(s.encode() + b"\n")

    def read_lines(self):
        self.buf += self.ser.read(4096)
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            yield line.decode("utf-8", "replace").strip()

    def wait_for(self, want, timeout):
        end = time.time() + timeout
        while time.time() < end:
            r, _, _ = select.select([self.ser], [], [], 0.2)
            if r:
                for line in self.read_lines():
                    if line.split(" ")[0] in want: return line
        return None

    def bring_up(self):
        self.write_line("PING")
        if self.wait_for({"PONG", "READY"}, 3):
            return True
        log("modem silent; soft-resetting board")
        self.ser.write(b"\r\x04")           # MicroPython soft reset -> main.py -> modem
        return bool(self.wait_for({"READY", "PONG"}, 12))

    def tx(self, sf, data):
        self.write_line(f"TX {sf} {data.hex()}")


# ---------------------------------------------------------------- daemon
def daemon():
    os.makedirs(CONF, exist_ok=True)
    link = lcore.Link(KEY, STATE)
    while not os.path.exists(PORT):
        log("waiting for", PORT); time.sleep(5)
    modem = Modem(PORT)
    if not modem.bring_up():
        log("modem did not answer; exiting"); sys.exit(1)
    modem.write_line("STAT")
    try: os.unlink(SOCK)
    except FileNotFoundError: pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK); os.chmod(SOCK, 0o600); srv.listen(8); srv.setblocking(False)
    pending = {}           # cmd_ctr -> (conn, deadline, t0)
    log("loralink daemon up on", PORT, "socket", SOCK)
    while True:
        r, _, _ = select.select([modem, srv] + [c for c, _, _ in pending.values()], [], [], 0.25)
        now = time.time()
        if srv in r:
            conn, _ = srv.accept()
            try:
                conn.settimeout(2)
                req = json.loads(conn.makefile().readline() or "{}")
                text = req.get("send", "")
                sf = int(req.get("sf", 7)); wait = float(req.get("wait", 20))
                frame, ctr = link.pack(lcore.T_CMD, text.encode()[: lcore.MAX_PAYLOAD])
                modem.tx(sf, frame)
                log(f"-> gateway sf{sf} #{ctr}: {text}")
                pending[ctr] = (conn, now + wait, now)
            except Exception as e:
                try: conn.sendall(json.dumps({"error": str(e)}).encode() + b"\n")
                except Exception: pass
                conn.close()
        if modem in r:
            for line in modem.read_lines():
                if not line.startswith("RX "):
                    if line: log("modem:", line)
                    continue
                try:
                    _, sf, rssi, snr, crc, hexdata = line.split(" ")
                    frame = bytes.fromhex(hexdata)
                except ValueError:
                    log("modem garbled:", line[:60]); continue
                if crc != "ok":
                    log(f"RX bad crc rssi {rssi}"); continue
                try:
                    typ, ctr, payload = link.unpack(frame)
                except lcore.BadFrame as e:
                    log(f"RX rejected ({e}) rssi {rssi} len {len(frame)}"); continue
                if typ == lcore.T_CMD:
                    text = payload.decode("utf-8", "replace")
                    log(f"<- gateway #{ctr} rssi {rssi} snr {snr}: {text}")
                    reply = handle_command(text)
                    out, _ = lcore.pack_reply(link, ctr, reply)
                    modem.tx(int(sf), out)
                    log(f"-> reply #{ctr}: {reply[:80]}")
                elif typ == lcore.T_REPLY:
                    cmd_ctr, text = lcore.split_reply(payload)
                    log(f"<- reply to #{cmd_ctr} rssi {rssi} snr {snr}: {text[:80]}")
                    if cmd_ctr in pending:
                        conn, _, t0 = pending.pop(cmd_ctr)
                        try:
                            conn.sendall(json.dumps({"reply": text, "rssi": int(rssi), "snr": float(snr),
                                                     "rtt": round(now - t0, 1)}).encode() + b"\n")
                        except Exception: pass
                        conn.close()
        for ctr in [c for c, (_, dl, _) in pending.items() if dl < now]:
            conn, _, _ = pending.pop(ctr)
            try: conn.sendall(b'{"error": "no reply"}\n')
            except Exception: pass
            conn.close()
        for ctr, (conn, _, _) in list(pending.items()):      # client went away
            if conn in r:
                try:
                    if not conn.recv(1): pending.pop(ctr); conn.close()
                except Exception:
                    pending.pop(ctr, None); conn.close()


# ---------------------------------------------------------------- CLI
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
        if rest[i] in ("--sf", "--wait", "--every"):
            opts[rest[i][2:]] = float(rest[i + 1]); i += 2
        else:
            args.append(rest[i]); i += 1
    if cmd == "daemon":
        daemon()
    elif cmd == "beacon":
        # Drive-test mode: ping gateway forever, alternating SF7 / SF10, and log every result.
        every = float(opts.get("every", 8))
        logf = os.path.expanduser("~/loralink_drive.log")
        n = 0
        while True:
            for sf in (7, 10):
                n += 1
                t = time.strftime("%Y-%m-%d %H:%M:%S")
                try:
                    r = client({"send": "PING", "sf": sf, "wait": 12 if sf == 7 else 20})
                except Exception as e:
                    r = {"error": str(e)}
                line = (f"{t} #{n} sf{sf} OK rssi {r['rssi']} snr {r['snr']} rtt {r['rtt']}" if "reply" in r
                        else f"{t} #{n} sf{sf} MISS {r.get('error')}")
                print(line, flush=True)
                with open(logf, "a") as f: f.write(line + "\n")
                time.sleep(every)
    elif cmd == "status":
        print(status_text())
    elif cmd in ("ping", "send"):
        text = "PING" if cmd == "ping" else " ".join(args)
        t0 = time.time()
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
