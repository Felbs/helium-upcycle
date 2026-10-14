# 2. Nebra Outdoor hotspot → Linux

The Nebra Outdoor is a Raspberry Pi **Compute Module 3** on a carrier board, an **SX1301**
concentrator on an mPCIe card (SPI), an **ATECC608** crypto chip holding the Helium key, and a
USB hub board. Its operating system lived on a small eMMC "key" module.

## If the eMMC key is dead
Ours was: unreadable in three card readers and via `rpiboot`. The carrier has a microSD slot
(J1, "ONLY USE SD WITH CM LITE"), and an ordinary microSD works there.

- Jumper JP4: pins 1–2 normal boot, 2–3 USB boot (`rpiboot`, for imaging over the micro-USB
  port JP2). Do not touch the power-select jumper (PoE vs DC).
- **Before you plug a hotspot's storage into a desktop:** desktops auto-mount and can write to
  it (replaying a journal is a write). Add a udev rule that marks the device read-only first.

## Arch Linux ARM
- Use the **armv7** image (`rpi-armv7`, classic `kernel7.img`). The aarch64 image with U-Boot
  never reached Linux on the CM3 here.
- Quick check that Linux ever booted: mount the card read-only; an empty `/etc/machine-id` and
  no SSH host keys means it never did.
- In `config.txt` add `dtparam=i2c_arm=on` (key chip) and `dtoverlay=spi1-3cs` (concentrator).

## The concentrator (SX1301)
- Build Semtech's `lora_gateway` (5.0.x) and `packet_forwarder` (4.0.x).
- SPI device `/dev/spidev1.2`, **2 MHz** (8 MHz fails with "failed to start the concentrator").
- Reset: GPIO 38, pulse high before starting. Status LED GPIO 25, button GPIO 24.
- Start from Nebra's US915 sub-band-2 SX1301 config (radio SX1257, `clksrc` 1), send to
  `127.0.0.1:1680` (Helium directly) or `:1700` (through listener.py).
- About one start in five fails radio calibration (image-rejection status 175 instead of 191).
  Wrap the forwarder in a script that exits on that message and let systemd restart it.

## The key chip
gateway-rs reads the ATECC608 at `ecc://i2c-1:96?slot=0`; run it as a user in the `i2c` group.
See chapter 3.
