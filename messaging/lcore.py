"""Shared frame format + authentication for the LoRa command link.

Used unchanged on both ends (laptop `loralink.py`, gateway `loragw.py`).

Frame on the air:  b"LC1" | counter u32 BE | type u8 | payload | mac (8 bytes)
  mac = HMAC-SHA256(key, everything before it)[:8]
  counter increases on every frame a side sends; the receiver only accepts a
  counter higher than the last one it saw from that peer (no replays).
  A reply's payload starts with the u32 counter of the command it answers.
"""
import base64, hmac, hashlib, json, os, struct, tempfile

MAGIC = b"LC1"
T_CMD, T_REPLY, T_EVENT = 0, 1, 2
MAC_LEN = 8
HDR = struct.Struct(">IB")
MAX_FRAME = 255                                    # LoRa payload limit
MAX_PAYLOAD = MAX_FRAME - len(MAGIC) - HDR.size - MAC_LEN   # 239


class BadFrame(Exception):
    pass


class Link:
    def __init__(self, key_path, state_path):
        with open(key_path) as f:
            self.key = base64.b64decode(f.read().strip())
        if len(self.key) < 16:
            raise ValueError("key too short")
        self.state_path = state_path
        try:
            with open(state_path) as f:
                self.state = json.load(f)
        except Exception:
            self.state = {"tx": 0, "rx": 0}

    def _save(self):
        d = os.path.dirname(self.state_path) or "."
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".state")
        with os.fdopen(fd, "w") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.state_path)

    def _mac(self, body):
        return hmac.new(self.key, body, hashlib.sha256).digest()[:MAC_LEN]

    def pack(self, typ, payload):
        if len(payload) > MAX_PAYLOAD:
            raise ValueError("payload %d > %d" % (len(payload), MAX_PAYLOAD))
        self.state["tx"] += 1
        self._save()
        body = MAGIC + HDR.pack(self.state["tx"], typ) + payload
        return body + self._mac(body), self.state["tx"]

    def unpack(self, frame):
        """Return (typ, counter, payload) or raise BadFrame."""
        if not frame.startswith(MAGIC) or len(frame) < len(MAGIC) + HDR.size + MAC_LEN:
            raise BadFrame("not ours")
        body, mac = frame[:-MAC_LEN], frame[-MAC_LEN:]
        if not hmac.compare_digest(mac, self._mac(body)):
            raise BadFrame("bad signature")
        ctr, typ = HDR.unpack_from(body, len(MAGIC))
        if ctr <= self.state["rx"]:
            raise BadFrame("replay (ctr %d <= %d)" % (ctr, self.state["rx"]))
        self.state["rx"] = ctr
        self._save()
        return typ, ctr, body[len(MAGIC) + HDR.size:]


def pack_reply(link, cmd_ctr, text):
    text = text.encode("utf-8", "replace")[: MAX_PAYLOAD - 4]
    return link.pack(T_REPLY, struct.pack(">I", cmd_ctr) + text)


def split_reply(payload):
    """payload of a T_REPLY -> (cmd_ctr, text)"""
    if len(payload) < 4:
        raise BadFrame("short reply")
    return struct.unpack(">I", payload[:4])[0], payload[4:].decode("utf-8", "replace")
