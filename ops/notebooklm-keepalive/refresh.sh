#!/bin/bash
export NOTEBOOKLM_HOME=/home/hatch/.notebooklm-kenta
# VM egress requires this proxy; it accepts unauthenticated CONNECT from inside the VM.
export HTTP_PROXY="http://hatch-egress-proxy:3128"
export HTTPS_PROXY="http://hatch-egress-proxy:3128"
export http_proxy="http://hatch-egress-proxy:3128"
export https_proxy="http://hatch-egress-proxy:3128"
# The runtime-default NO_PROXY contains bare IPv6 entries that crash httpx; sanitize.
export NO_PROXY="localhost,127.0.0.1"
export no_proxy="localhost,127.0.0.1"
LOG=/home/hatch/nblm-vm/refresh.log
# Phase 1: never rotate the PSIDTS chain while a Daily GHA run may be using
# the session (hypothesis: the 2026-10-26 refresh at 02:41:45Z killed the
# run's auth 29 seconds later). Skip during the daily-run window JST.
now=$(TZ=Asia/Tokyo date +%H%M)
if [ "$now" -ge 0430 ] && [ "$now" -lt 1000 ]; then
  echo "$(date -Is) skip (daily-run window 04:30-10:00 JST)" >> "$LOG"
  exit 0
fi
out=$(/home/hatch/nblm-vm/.venv/bin/notebooklm auth refresh 2>&1)
code=$?
echo "$(date -Is) exit=$code $out" >> "$LOG"
tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit $code
