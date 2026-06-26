# Pi 3A+ — DietPi Flash & First-Boot Setup

Goal: flash an SD card so the Pi boots **headless**, joins WiFi, is reachable over SSH,
and comes up with RTL-SDR + audio + mDNS ready — no monitor/keyboard needed (we only have
one USB port, and it's taken by the SDR).

Image used: **`DietPi_RPi234-ARMv8-Trixie.img.xz`** (64-bit / Debian 13).
Config keys verified against the on-card files.

---

## 1. Flash the image

1. Flash `DietPi_RPi234-ARMv8-Trixie.img.xz` with **Raspberry Pi Imager** (write the raw
   image — skip its OS-customization, that's for Pi OS) or **balenaEtcher**.
2. Re-insert the card so your computer mounts the **boot partition** (FAT; mounts as `NO NAME`
   on macOS). All edits below live there.

---

## 2. `dietpi.txt` — unattended first boot

Settings applied (the rest left at defaults):

```ini
AUTO_SETUP_AUTOMATED=1                 # whole first boot runs unattended
AUTO_SETUP_GLOBAL_PASSWORD=<YOURS>     # ◄ root + dietpi login password — SET THIS
AUTO_SETUP_SSH_SERVER_INDEX=-2         # OpenSSH (key auth + scp/sftp)
AUTO_SETUP_NET_HOSTNAME=fmradio        # reachable as fmradio.local
AUTO_SETUP_LOCALE=en_US.UTF-8
AUTO_SETUP_KEYBOARD_LAYOUT=us
AUTO_SETUP_TIMEZONE=America/Denver
AUTO_SETUP_NET_ETHERNET_ENABLED=0
AUTO_SETUP_NET_WIFI_ENABLED=1
AUTO_SETUP_NET_WIFI_COUNTRY_CODE=US
AUTO_SETUP_SWAPFILE_SIZE=1             # auto (matters on 512MB)
CONFIG_SERIAL_CONSOLE_ENABLE=0         # headless, no serial console needed
SURVEY_OPTED_IN=0                      # opt out of telemetry
CONFIG_SOUNDCARD=rpi-bcm2835-3.5mm     # route onboard audio to the 3.5mm jack (DietPi-native)
AUTO_SETUP_CUSTOM_SCRIPT_EXEC=0        # run /boot/Automation_Custom_Script.sh on first boot

# Packages installed automatically on first boot (DietPi-native, before the custom script):
AUTO_SETUP_APT_INSTALLS=rtl-sdr alsa-utils git build-essential python3-pip python3-venv libusb-1.0-0-dev avahi-daemon iw
```

Why these matter:
- **`avahi-daemon`** — DietPi minimal has no mDNS by default, so without this `fmradio.local`
  would not resolve. This is what makes `ssh dietpi@fmradio.local` work.
- **`CONFIG_SOUNDCARD=rpi-bcm2835-3.5mm`** — DietPi ships with the sound card set to `none`;
  this enables the 3.5mm jack (needed for the deferred Phase-3 speaker test).
- **`iw`** — used by the WiFi-power-save fix in the custom script.

---

## 3. `dietpi-wifi.txt` — WiFi credentials

```ini
aWIFI_SSID[0]='Homestead'
aWIFI_KEY[0]='<YOURS>'        # ◄ WiFi password — SET THIS
aWIFI_KEYMGR[0]='WPA-PSK'
```

---

## 4. `config.txt` — display, audio, clocks, thermal

Changes from the DietPi defaults:

```ini
dtparam=spi=on      # was #spi=off — Mini PiTFT (ST7789) is driven over SPI from Python
dtparam=audio=on    # was audio=off — onboard audio device for the 3.5mm jack
enable_uart=0       # was 1 — frees the core clock from the forced core_freq=250 cap
temp_limit=75       # was 65 — DietPi's 65°C throttle could choke the CPU-heavy HD (nrsc5) test
```

(The two GPIO buttons need no overlay — read GPIO 23/24 directly. `arm_64bit=1` confirms the
64-bit image.)

> ⚠️ `temp_limit=75` lets the Pi run a touch warmer to avoid early throttling during HD decode.
> Still well under the 85°C hard limit, but a small heatsink on the SoC is recommended given
> sustained `nrsc5` load. Revert to 65 if you'd rather keep it cool over HD performance.

---

## 5. `Automation_Custom_Script.sh` — runs once on first boot

Lives at the boot-partition root. Packages are handled by `AUTO_SETUP_APT_INSTALLS` (above),
so this script only writes config:

```bash
#!/bin/bash
# fm_radio — first-boot post-setup (runs once, after APT_INSTALLS packages are installed)

# 1) Stop the DVB-T TV-tuner kernel driver from grabbing the RTL-SDR dongle (THE #1 gotcha)
cat > /etc/modprobe.d/blacklist-rtlsdr.conf <<'EOF'
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
EOF

# 2) Let the 'dietpi' user reach the SDR without root
usermod -aG plugdev dietpi || true

# 3) Disable WiFi power saving (prevents periodic SSH/audio-stream stalls)
cat > /etc/systemd/system/wifi-powersave-off.service <<'EOF'
[Unit]
Description=Disable WiFi power saving on wlan0
After=network.target
[Service]
Type=oneshot
ExecStart=/usr/sbin/iw dev wlan0 set power_save off
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
systemctl enable wifi-powersave-off.service
```

We deliberately do **not** build `nrsc5` (HD Radio) here — it's the CPU-risky piece we want to
compile and test interactively in Phase 2, not bake into an unattended boot.

---

## 6. Two passwords to fill before flashing is "done"

| Password | File | Line |
|----------|------|------|
| **Login** (root + dietpi, also your SSH password) | `dietpi.txt` | `AUTO_SETUP_GLOBAL_PASSWORD=` |
| **WiFi** (for `Homestead`)                         | `dietpi-wifi.txt` | `aWIFI_KEY[0]=''` (between the quotes) |

---

## 7. First-boot verification (after it comes up)

```bash
ssh dietpi@fmradio.local          # password = AUTO_SETUP_GLOBAL_PASSWORD
hostname -I                       # the Pi's LAN IP — share this
lsusb | grep -i realtek           # dongle present?
rtl_test -t                       # should detect R820T tuner, no "usb_claim_interface error"
# (if rtl_test says the device is in use, the DVB blacklist needs one reboot to take effect)
```

If `rtl_test` sees the tuner, the Phase 0 foundation is done — all from the desk.

> **Audio-out (3.5mm jack) is deliberately deferred** to Phase 3 — we can't hear the Pi's
> speaker from the desk, so we validate over the web stream first (Phases 1–2). The
> `aplay -l` / `speaker-test` check happens later, *at* the Pi, after the HD test.
