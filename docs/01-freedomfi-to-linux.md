# 1. FreedomFi gateway → Linux

The FreedomFi FFG-HL-4-64 is a fanless x86 box: Celeron J1900, ~4 GB RAM, 64 GB SATA SSD,
four Intel gigabit ports, a TPM 2.0 holding the Helium key, and a **RAK5146** LoRa
concentrator (SX1302) that shows up as a USB serial device. It has **no video output**:
everything happens over the RJ45 serial console.

## What you need
- a USB-to-RJ45 console cable (FTDI-based, Cisco pinout), 115200 8N1
- a USB stick with the Arch Linux ISO (any distro works; Arch is what was tested)
- `picocom` or `screen` on another computer

## Steps
1. **Console in.** `picocom -b 115200 /dev/ttyUSB0`, then power the box. It powers on as
   soon as it gets 12 V.
2. **Get into the BIOS.** The "Press DEL/ESC" prompt is not always printed. What works: send
   ESC repeatedly from power-on. The BIOS (AMI Aptio) has no password. Input over serial is
   slow (about one key per second), so type deliberately.
3. **Back up the original disk first.** The stock Ubuntu install is LUKS-encrypted and
   unlocks via the TPM *only* with Secure Boot on. Boot the live USB and image the whole disk
   (`dd … | zstd`), plus the LUKS header and partition table. Restoring = write it back and
   turn Secure Boot back on. **Never clear the TPM** — it holds the hotspot's identity key.
4. **Disable Secure Boot** (leave the keys alone), raise "Setup Prompt Timeout" to 5 s.
5. **Boot the installer over serial.** In the boot menu press `e` and append
   `console=ttyS0,115200` to the kernel line (the Arch ISO has no serial console by default).
6. **Install** as usual: EFI partition + root, systemd-boot, SSH with keys only. Add
   `console=ttyS0,115200` permanently.
7. **Watchdog + reboot quirk.** The Intel watchdog (`iTCO_wdt`) works: set
   `RuntimeWatchdogSec=60s` in `/etc/systemd/system.conf.d/`. On this board, once the watchdog
   has run, the default EFI reboot *hangs*; add `reboot=pci` to the kernel line.
8. **Write config files, then `sync`.** A file written seconds before a crash came back empty
   (ext4 delayed allocation).

## The LoRa card
The RAK5146 appears as `/dev/ttyACM0` ("RAKwireless USB Virtual COM", 34e1:1002).
Build Semtech's [sx1302_hal](https://github.com/Lora-net/sx1302_hal) (tag `V2.1.0`) and use
[`gateway/global_conf.us915_fsb2.usb.json`](../gateway/global_conf.us915_fsb2.usb.json):
`com_type` USB, US915 sub-band 2 (903.9–905.3 MHz + 904.6 MHz/500 kHz), transmit allowed on
923–928 MHz. Put your card's EUI in `gateway_ID` (`util_chip_id` prints it).

The forwarder sends to `127.0.0.1:1700`, where [`gateway/listener.py`](../gateway/listener.py)
relays to Helium and TTN (next chapters). Units: [`gateway/systemd/`](../gateway/systemd/).

Check it hears something: `journalctl -u lora-listener -f`. A quiet log is normal where there
are no LoRa sensors; prove the radio with a known transmitter (a Heltec, chapter 5).
