# 5. Message yourself with a Heltec V3

A Heltec WiFi LoRa 32 V3 (~$25) on a laptop's USB port becomes a LoRa modem. The gateway's
concentrator hears it on the normal LoRaWAN channels and answers on the downlink band, so the
laptop and the gateway can exchange messages with no internet at all.

```
laptop  loralink.py ── USB ── Heltec (modem.py) ──904.3 MHz──►  gateway card ─► loragw.py
                                               ◄──923.3 MHz──  (listener TX door)
```

## Security: signed and numbered
LoRa is a shared, unencrypted band: anyone with a $20 board can transmit. Every frame here is
`LC1 | counter | type | payload | HMAC-SHA256[:8]` with a shared 32-byte key. The receiver
rejects a bad signature and any counter it has already seen (no replays). Commands are a
whitelist: `PING`, `STATUS`, `RUN <preset>` where presets are named shell commands in a JSON
file you control. Tested: a forged frame is rejected, `RUN rm_rf` gets "no preset".

## Heltec setup (MicroPython)
1. Flash MicroPython for ESP32-S3 (`ESP32_GENERIC_S3`, v1.29) with esptool. Back up the
   factory firmware first (`esptool read-flash 0 0x800000 backup.bin`).
2. Copy micropython-lib's `lora` package (`lora/__init__.py`, `modem.py`, `sx126x.py`,
   `sync_modem.py`) and `ssd1306.py`, then [`messaging/heltec/`](../messaging/heltec/):
   `heltec.py` (pin map), `modem.py`, and `main.py`.
3. Heltec V3 pins: SPI SCK 9 / MOSI 10 / MISO 11, NSS 8, RST 12, BUSY 13, DIO1 14, TCXO 1.8 V
   on DIO3, DIO2 = RF switch; OLED SDA 17 / SCL 18 / RST 21, powered by Vext (GPIO 36 low).
4. **Antenna on before anything transmits.**

Two driver lessons that cost time: call `standby()` before `configure()` (it refuses while
receiving), and use continuous receive (`start_recv(continuous=True)` + `poll_recv()`). The
one-shot `recv()` missed about 1 reply in 6.

## Laptop and gateway
- Make a key: `head -c 32 /dev/urandom | base64 > ~/.config/loralink/key` (mode 600) and copy
  the same file to the gateway (`~/lora/loralink.key`).
- Laptop: `messaging/loralink.py daemon` (or the user unit in `messaging/systemd/`), then
  `loralink ping`, `loralink send STATUS`, `loralink send "RUN uptime" --sf 10`.
- Gateway: `messaging/loragw.py daemon` (unit `lora-gateway.service`), then `loragw ping`.
- The Heltec's screen shows messages sent/received, the last signal strength and the text of
  the last reply.

Measured indoors: 20/20 round trips each way, about 0.4 s at SF7 and 1.1 s at SF10.

## On the road
`messaging/drive_mode.sh on` keeps a laptop awake with the lid closed (systemd-inhibit) and
pings the gateway every 8 s, alternating SF7/SF10, logging each result with the time.
`drive_mode.sh off` restores normal sleep.
