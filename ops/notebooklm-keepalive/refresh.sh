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
out=$(/home/hatch/nblm-vm/.venv/bin/notebooklm auth refresh 2>&1)
code=$?
echo "$(date -Is) exit=$code $out" >> "$LOG"
tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit $code
