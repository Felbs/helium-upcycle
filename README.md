# helium-upcycle

**Your old Helium hotspot is a perfectly good LoRa gateway. Don't throw it out.**

Thousands of Helium IoT hotspots went into drawers when the rewards dried up. Inside each one is
a real 8-channel LoRaWAN concentrator (SX1301/SX1302), a decent antenna and often a small x86 or
Raspberry Pi computer. This repo shows how two "dead" hotspots were brought back as:

1. **a Helium hotspot again** (data-only, honest about what that earns),
2. **a The Things Network gateway at the same time**, from the same radio, and
3. **a long-range text link to yourself** using a ~$25 handheld LoRa board (Heltec V3) —
   signed messages, no internet, no cell service, about a mile.

Everything here runs on plain Linux (Arch) and was tested end to end.

| Hardware | Inside | Status here |
|---|---|---|
| FreedomFi gateway (FFG-HL-4-64) | Celeron J1900, 4 GB, 64 GB SSD, TPM 2.0, RAK5146 (SX1302, USB) | Arch Linux, Helium + TTN + messaging |
| Nebra Outdoor hotspot | Raspberry Pi CM3, SX1301 (SPI), ATECC608 key chip | Arch Linux ARM, Helium |
| Heltec WiFi LoRa 32 V3 | ESP32-S3 + SX1262 + OLED | MicroPython modem for the laptop |

## The honest part about Helium
Helium passed **HIP 149**: Proof-of-Coverage was retired for IoT hotspots. There are no
beacons and no witness rewards any more. A hotspot now earns only for *data it actually carries*,
which near most homes is close to zero. So the point of reviving one is the radio, not the tokens.
The good news: the hotspot's on-chain identity (its key) still works, so you can keep it on the
network for free and serve anyone's sensors that happen to be nearby.

**Keep the key.** The hotspot's identity lives in a TPM (FreedomFi) or an ECC608 chip (Nebra).
Do not clear the TPM or reflash the key chip. Everything in this guide leaves them untouched.

## How it fits together
```
                      ┌───────────────────── gateway box ─────────────────────┐
 LoRa sensors ))) ──► │ concentrator ─► lora_pkt_fwd ─► listener.py ─┬─► helium_gateway ─► Helium
 Heltec V3   ))) ──►  │  (SX1301/2)        (Semtech UDP :1700)       ├─► The Things Network
              ◄─── ((( │                                               └─► packets.jsonl (log)
                      │  loragw.py ─► 127.0.0.1:1702 (local transmit door) ─► forwarder ─► air
                      └────────────────────────────────────────────────────────┘
 laptop ── USB ── Heltec V3 (modem.py)  ◄── signed, numbered messages ──►  loragw.py
```

## Guide
1. [FreedomFi box → Linux](docs/01-freedomfi-to-linux.md) — serial console, BIOS, backup, install
2. [Nebra Outdoor → Linux](docs/02-nebra-outdoor-to-linux.md) — Arch ARM on microSD, SPI concentrator
3. [Stay on Helium](docs/03-stay-on-helium.md) — gateway-rs with the key where it already is
4. [Join The Things Network too](docs/04-join-the-things-network.md) — one radio, two networks
5. [Message yourself with a Heltec V3](docs/05-message-yourself-heltec.md) — the signed command link
6. [Range: what to expect](docs/06-range-what-to-expect.md) — two drive tests, real numbers

## Repository
```
gateway/      listener.py (relay + log + TX door), forwarder config template, Helium settings,
              systemd units, tx_test.py (send a known packet)
messaging/    lcore.py (frame format, HMAC signing, replay protection), loralink.py (laptop),
              loragw.py (gateway), drive_mode.sh, heltec/ (MicroPython: modem, range test)
docs/         the guide
```

Related: [numpy-lora](https://github.com/Felbs/numpy-lora) — a LoRa decoder for an SDR, developed
against these same gateways and Heltec.

## Rules of the road (US 902–928 MHz)
Stay within FCC Part 15 limits: these programs default to 14–26 dBm conducted; add your antenna
gain and keep EIRP legal. The gateway only transmits on 923–928 MHz (LoRaWAN downlink channels),
as configured in `tx_freq_min/max`.

MIT licence.
