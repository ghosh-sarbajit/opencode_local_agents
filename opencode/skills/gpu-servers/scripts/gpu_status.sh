#!/usr/bin/env bash
# Show GPU, disk and load status for the shared GPU servers.
# Usage: gpu_status.sh [host ...]      (default: bharati kanaada)
set -u
hosts=("$@")
[ ${#hosts[@]} -eq 0 ] && hosts=(bharati kanaada)

for h in "${hosts[@]}"; do
  echo "================ $h ================"
  timeout 45 ssh -o BatchMode=yes -o ConnectTimeout=8 "$h" 'bash -s' <<'EOF' 2>&1 | grep -v 'Pseudo-terminal'
echo "GPU  util  mem_used/total(MiB)  status"
nvidia-smi --query-gpu=index,uuid,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits |
while IFS=', ' read -r idx uuid util used total; do
  if [ "$used" -lt 1024 ] && [ "$util" -lt 5 ]; then st=FREE; else st=BUSY; fi
  printf '%-4s %4s%%  %6s/%-6s          %s\n' "$idx" "$util" "$used" "$total" "$st"
  echo "$idx $uuid" >> /tmp/.gpu_status_map.$$
done
echo
echo "GPU processes (gpu  pid  user  mem  command):"
found=0
while IFS=', ' read -r uuid pid mem; do
  [ -z "$pid" ] && continue
  found=1
  idx=$(awk -v u="$uuid" '$2==u{print $1}' /tmp/.gpu_status_map.$$)
  user=$(ps -o user= -p "$pid" 2>/dev/null || echo '?')
  cmd=$(ps -o args= -p "$pid" 2>/dev/null | cut -c1-70)
  printf '  %-3s %-8s %-10s %-9s %s\n' "$idx" "$pid" "$user" "${mem}MiB" "$cmd"
done < <(nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader,nounits)
[ "$found" = 0 ] && echo "  (none)"
rm -f /tmp/.gpu_status_map.$$
echo
echo "Disk free:"
for d in "$HOME" /data/sarbajit; do
  [ -d "$d" ] && df -h "$d" | awk -v d="$d" 'NR==2{printf "  %-16s %s free of %s (%s used)\n", d, $4, $2, $5}'
done
echo "Load (1/5/15 min): $(cut -d' ' -f1-3 /proc/loadavg)   CPUs: $(nproc)"
echo "My tmux sessions: $(tmux ls 2>/dev/null | cut -d: -f1 | tr '\n' ' ' || true)"
EOF
  if [ "${PIPESTATUS[0]}" -ne 0 ]; then
    echo "!! could not reach $h (VPN/network down, or SSH key not accepted)"
    rc=1
  fi
done
exit "${rc:-0}"
