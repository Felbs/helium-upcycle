# 8. The concentrator as a weather-station receiver

Many backyard weather stations sold in North America send their readings to
the indoor display on **915 MHz, two-tone FSK, on one fixed channel** — the
same kind of signal as the Z-Wave frames in [doc 7](07-z-wave-gateway.md),
just slower. The hotspot's FSK modem can read them all day, listen-only,
with the same raw-FSK patch. Here it reads a **Fine Offset WH65B** 7-in-1
station (sold as Ecowitt, Ambient Weather, Misol and many store brands):
temperature, humidity, wind, gust, direction, rain, light and UV every
16 seconds. The measurements: the Radio Grid Atlas
[wx-7in1](https://github.com/Felbs/radio-grid-atlas/tree/master/wx-7in1) entry.

## What it does today

- **88 % of all frames verified** over 2.9 hours (572 of ~650 sent), every
  one passing the station's own CRC-8 and checksum, from an attic antenna.
- On the same station, an SDR on a rooftop discone saw the bursts only
  7–8 dB above the noise and **decoded none**. A modem that integrates whole
  bits at the right rate, on an antenna built for the band, wins.
- Runs as a small service that writes one line of JSON per reading.

## Settings for the WH65B

| setting | value | note |
|---|---|---|
| frequency | 915.000 MHz (RF chain 915.2, FSK IF −200 kHz) | our station sat at 915.03 MHz; the 125 kHz channel covers it |
| bit rate | **17,241 bit/s** (58 µs) | at 11,260 or 11,494 bit/s the card hears nothing |
| sync word | **`AA 2D D4`**, 3 bytes | the last preamble byte plus the station's sync, so each block starts at the family byte `0x24` |
| block | 40 bytes, fixed | the 17-byte frame plus spare |
| check | CRC-8 poly 0x31 over bytes 0–14 = byte 15; 8-bit sum of bytes 0–15 = byte 16 | done on the host; the modem cannot |
| polarity | a logical 1 on the **upper** tone (the chip's own) | Z-Wave is the opposite; `wxrx1302 … inv` flips it |

## Doing this with your own hotspot

What you need: a FreedomFi box (or another SX1302/SX1250 card) running Linux
([doc 1](01-freedomfi-to-linux.md)), the raw-FSK patched `sx1302_hal` from
[zwave-sdr](https://github.com/Felbs/zwave-sdr) (`sx1302/libloragw-sx1302-raw-fsk.patch`),
and a 915 MHz weather station within reach. The code is in [`weather/`](../weather/).

1. **Check your station's frequency.** It is printed on the indoor display
   or the outdoor unit, or in the manual: 915 MHz is the one this card can
   hear. (433 MHz stations are common too; the card's filters and antenna
   cannot reach them — use an SDR and rtl_433 for those.)
2. **Build the receiver:** `cd weather && HAL=~/sx1302_hal ./build.sh`.
3. **Stop the LoRa forwarder** so the concentrator is free:
   `sudo systemctl stop lora-pkt-fwd`.
4. **Listen for a few minutes:**
   `WX_DR=17241 WX_SYNC=AA2DD4 ./wxrx1302 120 | python3 decode_wh65.py`.
   A WH65B sends every 16 seconds; each verified frame prints its
   temperature, humidity, wind and light. Compare with your display to find
   *your* station — the ID is only 8 bits and neighbours' stations will
   show up too.
5. **Log it around the clock:** put your station's ID in
   `weather/wxlocal.json` as `{"station_id": 29}`, copy the folder to
   `/opt/helium-upcycle/weather`, then
   `sudo cp weather/systemd/wx-logger@.service /etc/systemd/system/ &&
   sudo systemctl enable --now wx-logger@$USER`. Readings go to
   `~/weather/wxlocal.jsonl` (change with `WX_OUT`).
6. **Going back to Helium/TTN:** `sudo systemctl disable --now wx-logger@$USER`
   and start the forwarder again. The service is marked to conflict with
   the forwarder, so starting one stops the other.

## Things worth knowing

- **One radio, one job.** While it is a weather receiver it is not a
  LoRaWAN gateway (same as doc 7).
- **The RSSI the HAL prints for FSK is a constant** (as in doc 7). Ours
  read −117 dBm on nearly every frame whatever the conditions; it is not a
  signal level.
- **No raw samples.** The modem returns bits or nothing: frequency, tone
  spacing and timing finer than a bit are invisible. If a station is not
  heard, the card cannot tell you why — an SDR can.
- **One setting at a time.** Bit rate, sync word and frequency are fixed per
  run. A 433 MHz Emax-family station (rtl_433 "IMETEO-X6") in the same house
  was never heard at any setting: wrong band.
- **Fixed blocks.** After a sync the modem reads the whole 40-byte block
  (18.6 ms at this rate) before it can catch another; two stations
  transmitting within that window lose one frame.
- **Timestamps are whole seconds** in the log; the 16 s cadence slips one
  second every couple of hours (the station's crystal, ~130 ppm). Normal.
- **Other Fine Offset sensors** on 915 MHz (soil moisture, extra
  thermometers, lightning, rain) use related formats at the same bit rate;
  the decoder here only reads the WH65B frame (family `0x24`), but the
  receiver will print the others' raw bytes.
- **Neighbours' stations** are someone else's data. Keep their IDs and
  readings out of anything you publish.
