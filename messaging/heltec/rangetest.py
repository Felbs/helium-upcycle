# Autonomous range test for the Heltec V3: ping gateway on 904.3 MHz, listen for its
# ACK on 923.3 MHz, alternate SF7 / SF10, log to flash, show status on the OLED.
import time, machine
from machine import Pin, I2C
import heltec

TX_KHZ, RX_KHZ, DBM = 904300, 923300, 20
PLAN = ((7, 3000), (10, 5000))        # (spreading factor, ms to wait for the ACK)
LOG = "/rangelog.txt"

def oled_init():
    try:
        Pin(36, Pin.OUT, value=0)                      # Vext: low = peripherals powered
        time.sleep_ms(50)
        rst = Pin(21, Pin.OUT, value=0); time.sleep_ms(20); rst.value(1); time.sleep_ms(20)
        i2c = I2C(0, scl=Pin(18), sda=Pin(17), freq=400000)
        import ssd1306
        return ssd1306.SSD1306_I2C(128, 64, i2c)
    except Exception as e:
        print("oled unavailable:", e)
        return None

def show(oled, lines):
    if not oled: return
    try:
        oled.fill(0)
        for i, l in enumerate(lines[:6]): oled.text(l, 0, i * 10)
        oled.show()
    except Exception as e:
        print("oled err", e)

def run(cycles=None):
    oled = oled_init()
    show(oled, ["RANGE TEST", "starting..."])
    m = heltec.radio(dbm=DBM)
    seq = heard = fails = 0; last = "none"
    while cycles is None or cycles > 0:
        if cycles: cycles -= 1
        for sf, win in PLAN:
            seq += 1
            try:
                up = time.ticks_ms() // 1000
                msg = b"RT seq=%d sf=%d up=%d rx=%d" % (seq, sf, up, heard)
                m.configure(dict(freq_khz=TX_KHZ, sf=sf))
                heltec.LED.on(); m.send(msg); heltec.LED.off()
                m.configure(dict(freq_khz=RX_KHZ))
                p = m.recv(timeout_ms=win)
                if p and bytes(p).startswith(b"ACK"):
                    heard += 1; last = "%d dBm" % p.rssi
                    rec = "%d sf%d up=%d ACK rssi=%d snr=%.1f %s" % (seq, sf, up, p.rssi, p.snr / 4, bytes(p).decode())
                    heltec.LED.on(); time.sleep_ms(400); heltec.LED.off()
                elif p:
                    rec = "%d sf%d up=%d GARBLED crc_ok=%s rssi=%d snr=%.1f hex=%s" % (seq, sf, up, p.valid_crc, p.rssi, p.snr / 4, bytes(p).hex())
                else:
                    rec = "%d sf%d up=%d no-reply" % (seq, sf, up)
                print(rec)
                with open(LOG, "a") as f: f.write(rec + "\n")
                show(oled, ["RANGE TEST", "ping %d  SF%d" % (seq, sf), "heard %d/%d" % (heard, seq),
                            "last " + last, "up %d:%02d" % (up // 60, up % 60)])
                fails = 0
            except Exception as e:
                fails += 1; print("cycle error:", repr(e))
                show(oled, ["RANGE TEST", "radio error", str(e)[:16], "retry %d" % fails])
                time.sleep(2)
                if fails >= 5: machine.reset()
                try: m = heltec.radio(dbm=DBM)
                except Exception: pass
    m.sleep()
