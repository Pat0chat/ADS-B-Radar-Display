#!/bin/bash

###########################################
# ADS-B Simulator and Radar Launcher
###########################################

# --- CONFIG ---

# Paths
RADAR_SCRIPT_PATH="./radar/main.py"
SIMULATOR_SCRIPT_PATH="./simulator/main.py"
LOGFILE="radar.log"

echo "----------------------------------------" | tee -a "$LOGFILE"
echo "Starting ADS-B Radar…" | tee -a "$LOGFILE"
echo "Simulator script: $SIMULATOR_SCRIPT_PATH" | tee -a "$LOGFILE"
echo "Radar script: $RADAR_SCRIPT" | tee -a "$LOGFILE"

# --- START simulator ---

echo "[1/2] Launching simulator" | tee -a "$LOGFILE"
python3 "$SIMULATOR_SCRIPT_PATH" &
SIMULATOR_SCRIPT_PID=$!

sleep 2

# --- WAIT until simulator responds ---

echo -n "Waiting for simulator to respond" | tee -a "$LOGFILE"
for i in {1..10}; do
    if curl -s http://localhost:8080/data.json >/dev/null; then
        echo "✔" | tee -a "$LOGFILE"
        break
    fi
    echo -n "." | tee -a "$LOGFILE"
    sleep 1
done

if ! curl -s http://localhost:8080/data.json >/dev/null; then
    echo "❌ simulator did not respond — aborting." | tee -a "$LOGFILE"
    kill "$SIMULATOR_SCRIPT_PID"
    exit 1
fi

# --- START RADAR SCRIPT ---

echo "[2/2] Starting Python radar…" | tee -a "$LOGFILE"
python3 "$RADAR_SCRIPT"
RADAR_EXIT=$?

echo "Radar script ended (code $RADAR_EXIT)" | tee -a "$LOGFILE"

# --- CLEANUP ---

echo "Stopping simulator" | tee -a "$LOGFILE"
kill "$SIMULATOR_SCRIPT_PID" 2>/dev/null

echo "Done." | tee -a "$LOGFILE"
