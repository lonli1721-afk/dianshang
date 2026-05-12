#!/usr/bin/env bash
set -euo pipefail

log="/home/deploy/game-video-tool/app.log"
max_bytes=$((100 * 1024 * 1024))
keep_bytes=$((20 * 1024 * 1024))

if [ ! -f "$log" ]; then
  exit 0
fi

size=$(stat -c%s "$log" 2>/dev/null || echo 0)
if [ "$size" -le "$max_bytes" ]; then
  exit 0
fi

stamp=$(date +%Y%m%d-%H%M%S)
archive="${log}.${stamp}.tail"
tail -c "$keep_bytes" "$log" > "$archive"
cat "$archive" > "$log"
gzip -f "$archive"
find /home/deploy/game-video-tool -maxdepth 1 -name "app.log.*.tail.gz" -mtime +7 -delete
