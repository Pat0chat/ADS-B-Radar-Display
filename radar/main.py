#!/usr/bin/env python3
"""
ADS-B Radar
Fetches data from dump1090 and renders a radar-style view.

Dependencies:
    - requests
    - pillow (PIL)

Run:
    pip install requests pillow
    python main.py
"""

import tkinter as tk
import json
import os

from radar import ADSBRadarApp

# ------------------- Configuration -------------------
CONFIG_FILE = "./radar/config.json"
DATA_URL = "http://localhost:8080/data.json"
RADAR_LAT = 48.6833   # default receiver latitude
RADAR_LON = 2.1333    # default receiver longitude
REFRESH_MS = 1000     # update interval in milliseconds
MAX_RANGE_KM = 200    # maximum radar range shown (km)
CANVAS_SIZE = 800     # pixels (square canvas)
TRAIL_MAX = 100       # default number of points in trail


# ------------------- Utilities -------------------
def load_config():
    """Load JSON config if available.

    Returns a dict (possibly empty) with configuration overrides.
    """
    if os.path.exists(CONFIG_FILE):
        print("[ADS-B Radar] Reading config file")
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data
        except Exception:
            print("[ADS-B Radar] Error reading config file")
            return {}
    else:
        print("[ADS-B Radar] No config file")
    return {}


# ------------------- Main -------------------
if __name__ == "__main__":
    try:
        print("[ADS-B Radar] Launching ADS-B Radar")

        # load config.json
        cfg = load_config()
        if "data_url" in cfg:
            DATA_URL = cfg["data_url"]
        if "radar_lat" in cfg:
            RADAR_LAT = float(cfg["radar_lat"])
        if "radar_lon" in cfg:
            RADAR_LON = float(cfg["radar_lon"])
        if "max_range_km" in cfg:
            MAX_RANGE_KM = int(cfg["max_range_km"])
        if "canvas_size" in cfg:
            CANVAS_SIZE = int(cfg["canvas_size"])
        if "trail_max" in cfg:
            TRAIL_MAX = int(cfg["trail_max"])

        print("[ADS-B Radar] **** Setup ****")
        print("[ADS-B Radar] Dump1090 URL: " + DATA_URL)
        print("[ADS-B Radar] Radar lat: " + str(RADAR_LAT))
        print("[ADS-B Radar] Radar long: " + str(RADAR_LON))
        print("[ADS-B Radar] Max range (km): " + str(MAX_RANGE_KM))
        print("[ADS-B Radar] Canvas size: " + str(CANVAS_SIZE))
        print("[ADS-B Radar] Trail max: " + str(TRAIL_MAX))
        print("[ADS-B Radar] ****")

        root = tk.Tk()
        app = ADSBRadarApp(root, DATA_URL, RADAR_LAT, RADAR_LON,
                           MAX_RANGE_KM, CANVAS_SIZE, TRAIL_MAX)

        def on_close():
            app.stop()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.mainloop()

    except Exception as e:
        print("[ADS-B Radar] Error :", e)
