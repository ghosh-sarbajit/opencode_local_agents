#!/usr/bin/env bash
# Launch a command on a remote GPU server inside a detached tmux session, pinned to
# the given GPUs, with all output logged to <workdir>/logs/<session>-<timestamp>.log.
#
# Usage: remote_run.sh <host> <session-name> <gpu-ids> <workdir> '<command>'
#   gpu-ids: e.g. 0, 1 or 0,1
#   workdir: remote directory; may start with ~
set -euo pipefail

if [ $# -ne 5 ]; then
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
host=$1 session=$2 gpus=$3 workdir=$4 cmd=$5

if ! [[ "$session" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "session name may contain only letters, digits, _ and -" >&2; exit 2
fi
if ! [[ "$gpus" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
  echo "gpu-ids must look like 0 or 0,1" >&2; exit 2
fi

ts=$(date +%Y%m%d-%H%M%S)
# Expand a leading ~ on the remote side, not locally.
case "$workdir" in
  "~")   rwork='$HOME' ;;
  "~/"*) rwork='$HOME/'"${workdir#\~/}" ;;
  *)     rwork="$workdir" ;;
esac

# Base64 keeps the user's command byte-for-byte intact through ssh and tmux quoting.
cmd_b64=$(printf '%s' "$cmd" | base64 -w0)

ssh -o BatchMode=yes "$host" bash -s <<EOF
set -e
if tmux has-session -t '$session' 2>/dev/null; then
  echo "tmux session '$session' already exists on $host; pick another name or stop it first" >&2
  exit 3
fi
work="$rwork"
mkdir -p "\$work/logs"
log="\$work/logs/$session-$ts.log"
script="\$work/logs/.$session-$ts.sh"
{
  echo '#!/usr/bin/env bash'
  echo "cd \"\$work\""
  echo 'export CUDA_VISIBLE_DEVICES=$gpus'
  echo 'echo "=== start \$(date) host=\$(hostname) CUDA_VISIBLE_DEVICES=\$CUDA_VISIBLE_DEVICES ==="'
  echo '$cmd_b64' | base64 -d
  echo
  echo 'rc=\$?'
  echo 'echo "=== exit code \$rc at \$(date) ==="'
} > "\$script"
chmod +x "\$script"
tmux new-session -d -s '$session' "bash '\$script' 2>&1 | tee -a '\$log'"
echo "started tmux session '$session' on $host (GPUs $gpus)"
echo "log: \$log"
EOF
