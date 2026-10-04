# qwen server shortcut -> start-qwen38
sqwen() {
    local mode="${1:-}"
    local gpu="${2:-}"

    if [ -z "$mode" ]; then
        echo "Usage:"
        echo "  sqwen <16|8|4> [gpu]    start the server, e.g. sqwen 16 0  (GPU default: 16/8->0, 4->5)"
        echo "  sqwen stop              stop the server"
        echo "  sqwen status            health, model id, GPU pid"
        echo "  DRYRUN=1 sqwen 16 0    print the command instead of launching"
        echo "Env passthrough: PORT=... MAXLEN=... MAXSEQ=... EFFORT=... WAIT=1 FORCE=1 DRYRUN=1"
        return 1
    fi

    if ! command -v start-qwen38 >/dev/null 2>&1; then
        echo "sqwen: start-qwen38 not found on PATH (~/.local/bin)" >&2
        return 127
    fi

    case "$mode" in
        16|8|4|stop|status)
            if [ -n "$gpu" ]; then
                GPU="$gpu" start-qwen38 "$mode"
            else
                start-qwen38 "$mode"
            fi
            ;;
        *)
            echo "sqwen: unknown mode '$mode' (expected 16, 8, 4, stop or status)" >&2
            return 1
            ;;
    esac
}

# gemma-4 server shortcut -> start-gemma4 (MTP drafter for speculative decoding)
sgemma() {
    local mode="${1:-}"
    local gpu="${2:-}"

    if [ -z "$mode" ]; then
        echo "Usage:"
        echo "  sgemma <16|8> [gpu]     start the server, e.g. sgemma 8 5   (GPU default: 16->0, 8->5)"
        echo "  sgemma stop             stop the server"
        echo "  sgemma status           health, model id, GPU pid"
        echo "  DRYRUN=1 sgemma 8       print the command instead of launching"
        echo "Env passthrough: PORT=... MAXLEN=... MAXSEQ=... SPECS=... THINK=0 WAIT=1 FORCE=1 DRYRUN=1"
        return 1
    fi

    if ! command -v start-gemma4 >/dev/null 2>&1; then
        echo "sgemma: start-gemma4 not found on PATH (~/.local/bin)" >&2
        return 127
    fi

    case "$mode" in
        16|8|stop|status)
            if [ -n "$gpu" ]; then
                GPU="$gpu" start-gemma4 "$mode"
            else
                start-gemma4 "$mode"
            fi
            ;;
        *)
            echo "sgemma: unknown mode '$mode' (expected 16, 8, stop or status)" >&2
            return 1
            ;;
    esac
}
