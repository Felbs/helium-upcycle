# 3. Stay on Helium (data-only)

Helium's gateway software, [gateway-rs](https://github.com/helium/gateway-rs), talks Semtech UDP
to the packet forwarder and uses the hotspot's existing key. Nothing has to be re-onboarded.

1. Download the release build for your box: `x86_64-…-tpm` for FreedomFi, `armv7` (musl) for
   the Nebra. Unpack to `/opt/helium`.
2. Settings: start from the release's `settings.toml` and change only what
   [`gateway/helium_settings.toml`](../gateway/helium_settings.toml) shows:
   - FreedomFi: `keypair = "tpm://esys/0x81000031"` — the key is already in the TPM at that
     persistent handle. Run as a user in group `tss` with `TCTI=device:/dev/tpmrm0`.
   - Nebra: `keypair = "ecc://i2c-1:96?slot=0"`, user in group `i2c`.
   - `listen = "127.0.0.1:1680"`, `region = "US915"`.
   - `[poc] disable = true` — Proof-of-Coverage is retired (HIP 149); this stops pointless
     beacon transmissions.
3. Service: [`gateway/systemd/helium-gateway.service`](../gateway/systemd/helium-gateway.service).
4. Check: `journalctl -u helium-gateway` shows sessions to the router; `listener.py` prints
   `STAT` lines with `ackr 100`.

To confirm the key really is yours before anything else: look up the hotspot by its public key
on the Helium explorer. It will show the name and asserted location. **Don't paste either of
those anywhere public**: the location is your house.
