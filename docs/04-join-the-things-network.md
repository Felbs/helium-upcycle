# 4. Join The Things Network too

One radio can serve both networks. The packet forwarder can only talk to one server, so
[`listener.py`](../gateway/listener.py) sits in between and copies every uplink to both:

- Helium gets everything and owns the acknowledgements.
- TTN gets a copy; from TTN only *downlink transmit requests* are passed back to the radio.
- Both can schedule downlinks; the forwarder's just-in-time queue serialises them.

## Register the gateway on TTN
1. Make an account on [The Things Network](https://www.thethingsnetwork.org/) and open the
   console for your region (North America: `nam1`).
2. **Gateways → Register gateway.** Gateway EUI = the `gateway_ID` from your forwarder config
   (`util_chip_id` on SX1302 cards).
3. Frequency plan: **United States 902–928 MHz, FSB 2 (used by TTN)** — the same sub-band the
   forwarder listens on.
4. Leave the gateway's location private if you like; TTN lets you hide it.
5. Set `TTN_SERVER=nam1.cloud.thethings.network:1700` for the listener (the service file
   already does). The console should show the gateway as connected within a minute.

Seeing "something was received" on TTN is a stranger's sensor nearby, now served by you.
