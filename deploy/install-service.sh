#!/usr/bin/env bash
# Install + enable the fmradiod systemd service on the Pi. Run on the Pi (or via
# ssh). Stops the de-risk spike stream and any transient test unit first so they
# can't contend for the single SDR.
set -euo pipefail

install -m 644 /root/fmradio/deploy/fmradiod.service /etc/systemd/system/fmradiod.service
systemctl daemon-reload

# Free the SDR from anything the spikes/tests left running.
systemctl disable --now fmtest.service 2>/dev/null || true
systemctl stop fmradiod-test.service 2>/dev/null || true
systemctl reset-failed fmradiod-test.service 2>/dev/null || true

systemctl enable --now fmradiod.service
sleep 2
systemctl status fmradiod.service --no-pager | head -n 8
