#!/usr/bin/env python3
"""
dump1090 simulator with Tkinter control panel

Features:
   - Serves a JSON array at http://localhost:8080/data.json
   - Simulates moving aircraft with fields similar to dump1090:
    hex, flight, lat, lon, altitude, track, speed, reg, squawk (some may be absent)
   - No external dependencies (uses Python stdlib)

Run: 
    python main.py
"""

import json
import threading
import os

from controlpanel import ControlPanel
from server import start_http_server
from simulator import Simulator


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------


CONFIG_FILE = "./simulator/config.json"
HOST = "0.0.0.0"
PORT = 8080

# Default simulation settings
DEFAULT_NUM_AIRCRAFT = 10
DEFAULT_UPDATE_INTERVAL = 0.5
DEFAULT_RADIUS_KM = 200
CENTER_LAT = 52.0
CENTER_LON = 13.0

_LOCK = threading.Lock()


# ---------------------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------------------


def load_config():
    print(os.path.exists(CONFIG_FILE))
    if os.path.exists(CONFIG_FILE):
        print("[ADS-B Simulator] Reading config file")
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data
        except Exception:
            print("[ADS-B Simulator] Error reading config file")
            return {}
    else:
        print("[ADS-B Simulator] No config file")
    return {}


# ---------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------


if __name__ == "__main__":
    print("[ADS-B Simulator] Launching ADS-B Simulator")

    try:
        print("[ADS-B Simulator] Launching ADS-B simulator")

        # load config.json
        cfg = load_config()
        if "host" in cfg:
            HOST = cfg["host"]
        if "port" in cfg:
            PORT = int(cfg["port"])
        if "default_num_aircraft" in cfg:
            DEFAULT_NUM_AIRCRAFT = int(cfg["default_num_aircraft"])
        if "default_update_interval" in cfg:
            DEFAULT_UPDATE_INTERVAL = int(cfg["default_update_interval"])
        if "default_radius_km" in cfg:
            DEFAULT_RADIUS_KM = int(cfg["default_radius_km"])
        if "center_lat" in cfg:
            CENTER_LAT = float(cfg["center_lat"])
        if "center_lon" in cfg:
            CENTER_LON = float(cfg["center_lon"])

        print("[ADS-B Simulator] **** Setup ****")
        print("[ADS-B Simulator] Host: " + HOST)
        print("[ADS-B Simulator] Port: " + str(PORT))
        print("[ADS-B Simulator] Number of aircraft: " +
              str(DEFAULT_NUM_AIRCRAFT))
        print("[ADS-B Simulator] Update interval: " +
              str(DEFAULT_UPDATE_INTERVAL))
        print("[ADS-B Simulator] Radius (km): " + str(DEFAULT_RADIUS_KM))
        print("[ADS-B Simulator] Center lat: " + str(CENTER_LAT))
        print("[ADS-B Simulator] Center lon: " + str(CENTER_LON))
        print("[ADS-B Simulator] ****")

        sim = Simulator(DEFAULT_NUM_AIRCRAFT, DEFAULT_RADIUS_KM,
                        DEFAULT_UPDATE_INTERVAL, CENTER_LAT, CENTER_LON, _LOCK)
        httpd = start_http_server(sim, HOST, PORT)
        print(
            f"[ADS-B Simulator] Simulator running at http://{HOST}:{PORT}/data.json")

        ui = ControlPanel(sim, httpd)
        ui.mainloop()

    except Exception as e:
        print("[ADS-B Simulator] Error :", e)
