#!/usr/bin/env bash
# Sample the running daemon's CPU / RAM / temperature over time (run on the Pi).
# Usage: deploy/soak.sh [samples] [interval_sec]   (default 16 x 30s = ~8 min)
N=${1:-16}; IV=${2:-30}
echo "soak: $N samples every ${IV}s"
for i in $(seq 1 "$N"); do
  ts=$(date +%T)
  temp=$(vcgencmd measure_temp 2>/dev/null | sed 's/temp=//')
  thr=$(vcgencmd get_throttled 2>/dev/null | sed 's/.*=//')
  load=$(cut -d' ' -f1 /proc/loadavg)
  memf=$(free -m | awk '/Mem:/{print $4}')
  cpu=$(ps -C nrsc5 -C ffmpeg -C python --no-headers -o %cpu 2>/dev/null | awk '{s+=$1} END{printf "%.1f", s}')
  echo "$ts  temp=$temp  load=$load  memfree=${memf}MB  daemoncpu=${cpu}%  throttled=$thr"
  sleep "$IV"
done
echo "soak done"
