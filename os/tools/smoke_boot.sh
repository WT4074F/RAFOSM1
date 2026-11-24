#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Boot the ISO in QEMU on a blank disk and take screenshots, so every build shows
# whether it reaches the boot menu and setup. Fails if QEMU dies or the screen stays blank.
#
#   smoke_boot.sh <iso> <output-dir> [seconds]
set -euo pipefail

ISO=$1
OUT=$2
SECS=${3:-240}
mkdir -p "$OUT"
MON="$OUT/qemu-monitor.sock"
rm -f "$MON"

qemu-img create -q -f qcow2 "$OUT/disk.qcow2" 10G

ACCEL=tcg
[ -w /dev/kvm ] && ACCEL=kvm
echo "Booting $ISO for ${SECS}s (accel: $ACCEL)"

# IDE disk + CD and a PCnet card: the same hardware ReactOS supports best, and close to our VirtualBox setup.
qemu-system-i386 -accel "$ACCEL" -m 1024 -vga std \
  -drive file="$OUT/disk.qcow2",if=ide,index=0 \
  -drive file="$ISO",media=cdrom,if=ide,index=2 \
  -boot d -nic user,model=pcnet \
  -display none -serial file:"$OUT/serial.log" \
  -monitor unix:"$MON",server,nowait &
QPID=$!

shot() {
  python3 - "$MON" "$OUT/$1.ppm" <<'EOF'
import socket, sys, time
s = socket.socket(socket.AF_UNIX)
s.connect(sys.argv[1])
s.recv(4096)
s.sendall(f"screendump {sys.argv[2]}\n".encode())
time.sleep(1)
s.close()
EOF
}

# Wait for the monitor socket.
for _ in $(seq 30); do [ -S "$MON" ] && break; sleep 1; done

elapsed=0
for t in 10 30 60 120 $SECS; do
  [ "$t" -gt "$SECS" ] && continue
  sleep $((t - elapsed)); elapsed=$t
  if ! kill -0 "$QPID" 2>/dev/null; then
    echo "::error::QEMU exited after about ${t}s - the ISO didn't stay up"
    exit 1
  fi
  shot "screen-$(printf '%03d' "$t")s" && echo "  screenshot at ${t}s"
done

kill "$QPID" 2>/dev/null || true
wait "$QPID" 2>/dev/null || true

# Convert to PNG and check the last screen isn't blank (a single colour).
python3 - "$OUT" <<'EOF'
import glob, os, sys
from PIL import Image
shots = sorted(glob.glob(os.path.join(sys.argv[1], "*.ppm")))
for p in shots:
    Image.open(p).save(p[:-4] + ".png")
    os.remove(p)
last = Image.open(shots[-1][:-4] + ".png").convert("RGB")
colours = last.getcolors(maxcolors=1 << 16)
if colours is not None and len(colours) <= 1:
    print("::error::Last screenshot is a single solid colour - the OS probably hung or crashed")
    sys.exit(1)
print(f"Boot test passed: {len(shots)} screenshots, last one has {len(colours) if colours else 'many'} colours")
EOF

if grep -q "KeBugCheck\|\*\*\* Fatal System Error" "$OUT/serial.log" 2>/dev/null; then
  echo "::warning::Kernel bugcheck in serial log - see serial.log"
fi
rm -f "$OUT/disk.qcow2"
