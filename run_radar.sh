#!/bin/bash

###########################################
# ADS-B Radar Launcher
###########################################

# --- CONFIG ---

# Paths
RADAR_SCRIPT_PATH="./radar_adsb_tk.py"
DUMP_CMD="/home/dump1090/prepa/dump1090 --net --interactive"
LOGFILE="radar.log"

echo "----------------------------------------" | tee -a "$LOGFILE"
echo "Starting ADS-B Radar…" | tee -a "$LOGFILE"
echo "Using dump1090 command: $DUMP_CMD" | tee -a "$LOGFILE"
echo "Radar script: $RADAR_SCRIPT" | tee -a "$LOGFILE"

# --- START dump1090 ---

echo "[1/2] Launching dump1090…" | tee -a "$LOGFILE"
$DUMP_CMD &
DUMP_PID=$!

sleep 2

# --- WAIT until dump1090 responds ---

echo -n "Waiting for dump1090 to respond" | tee -a "$LOGFILE"
for i in {1..10}; do
    if curl -s http://localhost:8080/data.json >/dev/null; then
        echo "✔" | tee -a "$LOGFILE"
        break
    fi
    echo -n "." | tee -a "$LOGFILE"
    sleep 1
done

if ! curl -s http://localhost:8080/data.json >/dev/null; then
    echo "❌ dump1090 did not respond — aborting." | tee -a "$LOGFILE"
    kill "$DUMP_PID"
    exit 1
fi

# --- START RADAR SCRIPT ---

echo "[2/2] Starting Python radar…" | tee -a "$LOGFILE"
python3 "$RADAR_SCRIPT"
RADAR_EXIT=$?

echo "Radar script ended (code $RADAR_EXIT)" | tee -a "$LOGFILE"

# --- CLEANUP ---

echo "Stopping dump1090…" | tee -a "$LOGFILE"
kill "$DUMP_PID" 2>/dev/null

echo "Done." | tee -a "$LOGFILE"
