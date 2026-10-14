# Heltec WiFi LoRa 32 V3 helper: SX1262 on SPI, pins from Heltec's board definition.
from machine import Pin, SPI
from lora import SX1262
import time

LED = Pin(35, Pin.OUT, value=0)

def radio(freq_khz=904300, sf=7, bw="125", syncword=0x34, dbm=14):
    spi = SPI(1, baudrate=2_000_000, polarity=0, phase=0,
              sck=Pin(9), mosi=Pin(10), miso=Pin(11))
    cfg = dict(freq_khz=freq_khz, sf=sf, bw=bw, coding_rate=5, preamble_len=8,
               output_power=dbm, syncword=syncword, crc_en=True, implicit_header=False)
    return SX1262(spi=spi, cs=Pin(8), busy=Pin(13), dio1=Pin(14), reset=Pin(12),
                  dio2_rf_sw=True, dio3_tcxo_millivolts=1800, dio3_tcxo_start_time_us=5000,
                  lora_cfg=cfg)

def beacon(n=5, gap_s=3, text="FELBS HELTEC TEST", **kw):
    m = radio(**kw)
    for i in range(n):
        msg = b"%s #%d" % (text, i + 1)
        LED.on(); t = m.send(msg); LED.off()
        print("sent", i + 1, msg, "at ms", t)
        time.sleep(gap_s)
    m.sleep()

def listen(seconds=30, **kw):
    m = radio(**kw)
    end = time.ticks_add(time.ticks_ms(), seconds * 1000)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        p = m.recv(timeout_ms=2000)
        if p:
            print("RX", bytes(p), "rssi", p.rssi, "snr", p.snr, "crc_ok", p.valid_crc)
    m.sleep()
