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
| the card's sync detector wants a fixed pattern, Z-Wave's start-of-frame comes after a long 0101… preamble | SX1301: sync on `0x5555` and let a few lines of Python find `0xF0`. SX1302: sync on the start marker itself (`0xAA0F` in the chip's polarity, which the transmitter also uses) and raise `FSK_TIMEOUT` from 128 to 1023 bit-times so a long preamble does not time out |
| the two LoRa chips we own (SX1301, SX1262) both send a logical 1 as the *upper* tone; Z-Wave uses the lower | invert every byte and the sync word on transmit — proven by catching real controller frames and our own in one receive window, all with the same polarity |
| the SPI device and the reset GPIO need root | run `zwrx`/`zwtx` with `sudo`; pulse the reset line first (`gpioset -c gpiochip0 -t 100ms,0 38=1` on the Nebra Outdoor) |
| radio B image-rejection calibration fails about one start in five | start again — the same flake the Helium packet forwarder has |

## What it does today

- **Receives**: 75 checksum-good frames in 50 s of a real alarm-hub network,
  plus ~800 fragments of the 1.1 s wake-up beams a controller sends to a
  sleeping battery device.
- **Transmits**: 15/15 frames received byte-exact on a Heltec V3 (SX1262 in
  raw GFSK mode) at −76 dBm, same room.
- **Acts as a small hub** (SX1302 in the FreedomFi box): added a Z-Wave Plus
  thermostat on its wall, read and set its setpoints, switched its mode,
  changed a configuration parameter, and received the reports it sends on
  its own after a button press. Every step recorded on the air by an SDR.
- **Not yet**: S2 security (the thermostat joined unsecured, which it allows),
  removing a device, and listening around the clock — the concentrator is
  one radio, so while it is a Z-Wave hub it is not a LoRaWAN gateway.

## Doing this with your own hotspot and your own device

What you need: a hotspot running Linux ([doc 1](01-freedomfi-to-linux.md)
or [doc 2](02-nebra-outdoor-to-linux.md)), a Z-Wave device you own, and
ideally an SDR covering 908 MHz to see what is happening. The code and build
steps are in [zwave-sdr](https://github.com/Felbs/zwave-sdr); the commands
below are its `sx1302/zwctl1302` (SX1302/SX1250 cards such as the RAK5146 in
a FreedomFi box; for the SX1301 in a Nebra, `zwrx`/`zwtx` do receive and
transmit and the hub logic is not ported yet).

1. **Release the device from its current hub.** Z-Wave devices belong to one
   network at a time. Use the old hub's "remove / exclude device" function
   and confirm on the device (most have a menu or button for it). Deleting
   it in the old hub's app alone is not enough: the device still believes it
   belongs there and will not join anything else. The device's own status
   screen (ours shows a node ID of 000 when free) tells you it worked.
2. **Stop the LoRa forwarder** so the concentrator is free:
   `sudo systemctl stop lora-pkt-fwd`.
3. **Put the hub into add mode**, then start *include* on the device:
   `./zwctl1302 add 240 2` waits up to four minutes and gives the device
   node ID 2. It prints the device's announcement, its capabilities and the
   list of command classes it supports.
4. **If the device sleeps** (battery devices do), find its wake-up code
   once: `./zwctl1302 scan 2`. It beams each possible code and asks for a
   setpoint; ours answered on the third try.
5. **Talk to it:** `get 2 <code>`, `set 2 70 <code>`, or any command class
   with `cmd 2 <code> <hex>` — `4002` asks the mode, `3104` the room
   temperature, `8002` the battery, `700527` configuration parameter 39.
   Pipe the output through `zwsurvey.py` to read the replies in words.
6. **Make it report on its own:** `cmd 2 <code> 85010101` writes the hub
   into the device's lifeline group; from then on, `listen` shows setpoint
   and mode changes made at the device.
7. **Restart the forwarder** when done: `sudo systemctl start lora-pkt-fwd`.
   To hand the device to another hub later, repeat step 1 with the new hub.

Three things cost us a day and are already fixed in the code, but worth
knowing if you adapt it to another card: a real device's announcement is
longer than a mock's (50 bytes) and wrapped in a hub-search envelope; and
its **preamble is ~170 bits**, longer than the SX1302's default 128-bit
wait for the sync word — the modem gave up just before the start marker on
every attempt, even from a metre away, so the hotspot heard the alarm hub
but never the thermostat until that timeout was raised.

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
