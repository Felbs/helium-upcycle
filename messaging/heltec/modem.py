# Heltec V3 as a dumb LoRa modem for the laptop (runs from main.py).
#
# USB serial, one command per line:
#   TX <sf> <hex>              send bytes now at spreading factor sf (on tx_khz),
#                              then listen at that sf for reply_win ms
#   CFG k=v [k=v ...]          tx_khz rx_khz listen_sf dbm reply_win
#   PING                       -> PONG
#   STAT                       -> current settings
# Lines from the board:
#   READY | PONG | OK ... | ERR ... | RX <sf> <rssi> <snr> <ok|bad> <hex>
import sys, select, time
import heltec

CFG = dict(tx_khz=904300, rx_khz=923300, listen_sf=7, dbm=20, reply_win=10000)


class Screen:
    """OLED status: counters, last packet, and the text of the last message heard."""
    def __init__(self):
        self.oled = None
        self.tx = self.rx = 0
        self.last = ("", 0, 0, 0)      # text, rssi, snr, ticks
        try:
            from machine import Pin, I2C
            Pin(36, Pin.OUT, value=0)                          # Vext on
            time.sleep_ms(50)
            rst = Pin(21, Pin.OUT, value=0); time.sleep_ms(20); rst.value(1); time.sleep_ms(20)
            import ssd1306
            self.oled = ssd1306.SSD1306_I2C(128, 64, I2C(0, scl=Pin(18), sda=Pin(17), freq=400000))
        except Exception as e:
            print("ERR oled", repr(e))

    @staticmethod
    def text_of(frame):
        """Best-effort readable part of an LC1 frame (the modem has no key, so unverified)."""
        if frame.startswith(b"LC1") and len(frame) > 16:
            body = frame[8:-8]
            if frame[7] == 1 and len(body) >= 4:
                body = body[4:]
            return "".join(chr(c) if 32 <= c < 127 else "?" for c in body)
        return frame.hex()[:48]

    def note_rx(self, frame, rssi, snr):
        self.rx += 1
        self.last = (self.text_of(frame), rssi, snr, time.ticks_ms())
        self.draw()

    def note_tx(self):
        self.tx += 1
        self.draw("sending...")

    def draw(self, note=None):
        if not self.oled: return
        try:
            o = self.oled; o.fill(0)
            up = time.ticks_ms() // 1000
            o.text("LORALINK %d:%02d" % (up // 60, up % 60), 0, 0)
            o.text("tx %d  rx %d" % (self.tx, self.rx), 0, 10)
            text, rssi, snr, t = self.last
            if t:
                o.text("%ddBm %.0fdB %ds" % (rssi, snr, time.ticks_diff(time.ticks_ms(), t) // 1000), 0, 20)
                for i in range(3):
                    o.text(text[i * 16:(i + 1) * 16], 0, 32 + i * 10)
            else:
                o.text("no msg yet", 0, 20)
            if note: o.text(note, 0, 54)
            o.show()
        except Exception as e:
            print("ERR oled draw", repr(e))


class Modem:
    def __init__(self):
        self.m = heltec.radio(dbm=CFG["dbm"])
        self.cur_sf = CFG["listen_sf"]
        self.sf_until = None
        self.screen = Screen()
        self.listen(self.cur_sf)
        self.screen.draw("ready")

    def listen(self, sf):
        self.cur_sf = sf
        self.m.standby()                      # configure() refuses while receiving
        self.m.configure(dict(freq_khz=CFG["rx_khz"], sf=sf))
        self.m.start_recv(continuous=True)

    def tx(self, sf, data):
        self.m.standby()
        self.m.configure(dict(freq_khz=CFG["tx_khz"], sf=sf, output_power=CFG["dbm"]))
        heltec.LED.on()
        self.screen.note_tx()
        self.m.send(data)
        heltec.LED.off()
        self.listen(sf)
        self.sf_until = time.ticks_add(time.ticks_ms(), CFG["reply_win"])

    def handle(self, line):
        parts = line.split(" ")
        cmd = parts[0].upper()
        if cmd == "PING":
            print("PONG")
        elif cmd == "STAT":
            print("STAT", " ".join("%s=%s" % kv for kv in CFG.items()), "cur_sf=%d" % self.cur_sf)
        elif cmd == "TX" and len(parts) == 3:
            sf = int(parts[1]); data = bytes.fromhex(parts[2])
            if not 5 <= sf <= 12 or not 1 <= len(data) <= 255:
                print("ERR bad tx args"); return
            self.tx(sf, data)
            print("OK tx %d bytes sf%d" % (len(data), sf))
        elif cmd == "CFG":
            for kv in parts[1:]:
                k, v = kv.split("=", 1)
                if k in CFG: CFG[k] = int(v)
            self.sf_until = None
            self.listen(CFG["listen_sf"])
            print("OK cfg")
        else:
            print("ERR unknown:", line[:40])

    def poll(self):
        p = self.m.poll_recv()
        if p is not True and p:
            heltec.LED.on()
            print("RX %d %d %.1f %s %s" % (self.cur_sf, p.rssi, p.snr / 4,
                                            "ok" if p.valid_crc else "bad", bytes(p).hex()))
            if p.valid_crc:
                self.screen.note_rx(bytes(p), p.rssi, p.snr / 4)
            heltec.LED.off()
        if self.sf_until is not None and time.ticks_diff(self.sf_until, time.ticks_ms()) < 0:
            self.sf_until = None
            if self.cur_sf != CFG["listen_sf"]:
                self.listen(CFG["listen_sf"])
        now = time.ticks_ms()
        if time.ticks_diff(now, getattr(self, "_drawn", 0)) > 5000:   # keep the age counter moving
            self._drawn = now
            self.screen.draw()


def run():
    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)
    modem = Modem()
    print("READY")
    while True:
        try:
            if poll.poll(0):
                line = sys.stdin.readline()
                if line:
                    line = line.strip()
                    if line:
                        modem.handle(line)
            modem.poll()
            time.sleep_ms(5)
        except Exception as e:
            print("ERR", repr(e))
            time.sleep_ms(500)
            try:
                modem = Modem(); print("READY")
            except Exception as e2:
                print("ERR radio init", repr(e2)); time.sleep(2)
