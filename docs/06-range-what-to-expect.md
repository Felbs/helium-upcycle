# 6. Range: what to expect

Two drive tests in a suburban neighbourhood (houses and trees, gently rolling). Gateway: the
FreedomFi's SX1302 with an 8 dBi antenna in an attic. Mobile: a Heltec V3 with its stock stub
antenna inside a car, 20 dBm, antenna in a window.

| Distance | Gateway hears the car | Car hears the gateway |
|---|---|---|
| in the driveway | 100 %, −50 to −65 dBm | 100 % |
| 0.3 mi | ~80 %, −96 to −118 dBm | last replies, ~−106 dBm |
| 0.7 mi | yes, −117 dBm (SF7 and SF10) | nothing |
| ~1 mi | SF10 only, −119 dBm | nothing |
| 1.5 mi | two SF10 packets at −119 dBm | nothing |

What it means:
- **The gateway out-hears the handheld by about 15 dB.** Raising the gateway's transmit power
  from 20 to 26 dBm changed nothing for the car: the handheld's antenna and receiver are the
  limit, not the gateway's power.
- **Slower modes reach further.** At the edge, SF7 dropped out first and SF10 kept getting
  through, exactly as LoRa is designed.
- **−117 to −119 dBm is the floor** for these chips: the gateway was decoding at a
  signal-to-noise ratio of −10 to −16 dB.
- The cheapest improvement is on the handheld side: a better antenna (a hotspot's own 5 dBi
  antenna with an SMA-to-N adapter) and getting it **outside the car**. The car body costs
  10 dB or more.

The logs come from `messaging/heltec/rangetest.py` (standalone, no laptop needed) and
`drive_mode.sh` + `loralink beacon` (with a laptop), with the gateway logging every packet's
time and signal strength.
