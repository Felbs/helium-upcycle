# 7. The concentrator as a Z-Wave radio

The SX1301 in a Nebra (and the SX1302 in a FreedomFi box) has an FSK modem next
to its LoRa demodulators: 500 bit/s to 250 kbit/s, up to 8 sync bytes, a
deviation setting. US Z-Wave at 40 kbit/s is two-tone FSK with ±20 kHz
deviation on 908.4 MHz — inside the card's band and inside those limits. So a
retired hotspot can listen to, and talk to, the Z-Wave devices in its own
house. Code and build script: [zwave-sdr](https://github.com/Felbs/zwave-sdr);
the measurements: the Radio Grid Atlas
[zwave-908](https://github.com/Felbs/radio-grid-atlas/tree/master/zwave-908) entry.

## What stood in the way, and what fixed it

| problem | fix |
|---|---|
| the stock HAL frames every FSK packet the LoRaWAN way (length byte, whitening, CRC) | a 20-line patch: a global `lgw_fsk_raw` makes `lgw_send` emit fixed-length raw bytes; on receive, write `FSK_PKT_MODE=0, CRC_EN=0, DCFREE_ENC=0, PKT_LENGTH=80` after `lgw_start()` |
| the card's sync detector wants a fixed pattern, Z-Wave's start-of-frame comes after a long 0101… preamble | sync on `0x5555` (same in either bit polarity) and let a few lines of Python find `0xF0` and check the XOR checksum |
| the two LoRa chips we own (SX1301, SX1262) both send a logical 1 as the *upper* tone; Z-Wave uses the lower | invert every byte and the sync word on transmit — proven by catching real controller frames and our own in one receive window, all with the same polarity |
| the SPI device and the reset GPIO need root | run `zwrx`/`zwtx` with `sudo`; pulse the reset line first (`gpioset -c gpiochip0 -t 100ms,0 38=1` on the Nebra Outdoor) |
| radio B image-rejection calibration fails about one start in five | start again — the same flake the Helium packet forwarder has |

## What it does today

- **Receives**: 75 checksum-good frames in 50 s of a real alarm-hub network,
  plus ~800 fragments of the 1.1 s wake-up beams a controller sends to a
  sleeping battery device. It heard the battery thermostat directly, which an
  SDR two rooms away never did.
- **Transmits**: 15/15 frames received byte-exact on a Heltec V3 (SX1262 in
  raw GFSK mode) at −76 dBm, same room. The SDR was a poor referee for this —
  on the antennas to hand the hotspot's signal was only a few dB over its
  floor — so the second LoRa chip became the independent receiver.
- **Not yet**: answering a frame within the 0.6 ms a mains-powered controller
  manages (a battery device takes 3.3 ms, and controllers retry after 40–75 ms,
  so there is some slack); pairing; the S2 security layer. Every command on
  our network was S2-encrypted, so a controller built on this must do S2 to
  be useful with modern devices.

## Things worth knowing before you try

- The concentrator is one radio with one job at a time: while it is a Z-Wave
  receiver it is not a Helium or TTN gateway. Our Nebra's Helium services are
  disabled now (the other box mines); yours can be stopped for the experiment
  and restarted after.
- The HAL's FSK RSSI figure is a constant — ignore it. Use the Heltec, or an
  SDR, to measure levels.
- The hotspot's transmit level looked ~18 dB below expectation on both
  receivers we tried (a −6 dBm frame arrived at −76 dBm across a room). Not
  yet explained — the TX gain table, the antenna port the card actually
  drives, or a connector — and worth checking before expecting the hotspot
  to reach a device at the far end of the house.
- A Home ID identifies a network. The tools print it (you need it to build a
  controller for your own devices); keep captures and logs out of anything
  public.

## Why bother, when a $30 USB stick does this properly

It does — and if you want a working thermostat controller this week, buy the
stick and plug it into the box. The point here is the other one: the radio
in a box that was headed for e-waste can speak a protocol it was never sold
for, and finding out exactly where the chip's assumptions end (framing,
polarity, timing) is the kind of measurement nobody publishes.
