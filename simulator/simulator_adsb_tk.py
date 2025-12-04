#!/usr/bin/env python3
"""
dump1090 simulator with Tkinter control panel

Features:
   - Serves a JSON array at http://localhost:8080/data.json
   - Simulates moving aircraft with fields similar to dump1090:
    hex, flight, lat, lon, altitude, track, speed, reg, squawk (some may be absent)
   - No external dependencies (uses Python stdlib)

Run: 
    python simulator_adsb_tk.py
"""

import http.server
import socketserver
import json
import threading
import time
import math
import random
import string
import os
import tkinter as tk
from tkinter import ttk

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

EARTH_R = 6371.0


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


def destination_point(lat_deg, lon_deg, bearing_deg, distance_km):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    brng = math.radians(bearing_deg)
    d_div_r = distance_km / EARTH_R

    lat2 = math.asin(math.sin(lat)*math.cos(d_div_r) +
                     math.cos(lat)*math.sin(d_div_r)*math.cos(brng))
    lon2 = lon + math.atan2(
        math.sin(brng)*math.sin(d_div_r)*math.cos(lat),
        math.cos(d_div_r)-math.sin(lat)*math.sin(lat2)
    )
    return math.degrees(lat2), math.degrees(lon2)


def km_from_knots(kts):
    return kts * 1.852 / 3600.0

def gen_category():
    return random.choice([
        "A",   # fixed-wing
        "B",   # rotorcraft
        "C",   # gliders/balloons
        "D"   # UAV / special
    ])

def gen_hex():
    return "".join(random.choice("0123456789abcdef") for _ in range(6))


def gen_callsign():
    return random.choice(["DLH", "KLM", "AFR", "EZY", "RYR", "UAE", "AAL", "SAS"]) + str(random.randint(1, 9999))


def gen_reg():
    return "".join(random.choice(string.ascii_uppercase) for _ in range(5))


# ---------------------------------------------------------
# AIRCRAFT MODEL
# ---------------------------------------------------------

class Aircraft:
    def __init__(self, center_lat, center_lon, radius_km):
        angle = random.random() * 360.0
        r = random.random() * radius_km

        self.lat, self.lon = destination_point(
            center_lat, center_lon, angle, r)
        self.hex = gen_hex()
        self.flight = gen_callsign()
        self.reg = gen_reg()
        self.category = gen_category()

        self.track = random.uniform(0, 360)
        self.speed = random.uniform(150, 480)
        self.altitude = random.uniform(1000, 39000)
        self.vspeed = random.uniform(-1500, 1500)

        self.turn_rate = random.uniform(-3, 3)
        self._last_behavior = time.time()

    def step(self, dt):
        km_s = km_from_knots(self.speed)
        dist = km_s * dt
        self.lat, self.lon = destination_point(
            self.lat, self.lon, self.track, dist)

        self.track = (self.track + self.turn_rate * dt) % 360

        self.altitude += (self.vspeed / 60) * dt
        self.altitude = max(0, min(45000, self.altitude))

        if time.time() - self._last_behavior > random.uniform(10, 25):
            self.turn_rate = random.uniform(-4, 4)
            self.speed = max(150, min(500, self.speed + random.uniform(-40, 40)))
            # Smooth vertical rate change
            delta_vs = random.uniform(-600, 600)
            self.vspeed = max(-2500, min(2500, self.vspeed + delta_vs))
            self._last_behavior = time.time()

    def to_json(self):
        return {
            "hex": self.hex,
            "flight": self.flight,
            "reg": self.reg,
            "category": self.category,
            "lat": round(self.lat, 5),
            "lon": round(self.lon, 5),
            "altitude": int(self.altitude),
            "track": round(self.track, 1),
            "speed": int(self.speed),
            "vert_rate": int(self.vspeed),
            "seen": int(time.time()),
        }


# ---------------------------------------------------------
# SIMULATOR ENGINE
# ---------------------------------------------------------

class Simulator:
    def __init__(self):
        self.num_aircraft = DEFAULT_NUM_AIRCRAFT
        self.radius_km = DEFAULT_RADIUS_KM
        self.update_interval = DEFAULT_UPDATE_INTERVAL

        self.aircraft = []
        self.running = True

        for _ in range(self.num_aircraft):
            self.aircraft.append(
                Aircraft(CENTER_LAT, CENTER_LON, self.radius_km))

        self.sim_thread = threading.Thread(target=self.run_loop, daemon=True)
        self.sim_thread.start()

    def run_loop(self):
        last = time.time()
        while True:
            dt = time.time() - last
            last = time.time()

            if self.running:
                with _LOCK:
                    for ac in self.aircraft:
                        ac.step(dt)

                    # keep aircraft count stable
                    if len(self.aircraft) < self.num_aircraft:
                        self.aircraft.append(
                            Aircraft(CENTER_LAT, CENTER_LON, self.radius_km))
                    elif len(self.aircraft) > self.num_aircraft:
                        self.aircraft.pop()

            time.sleep(self.update_interval)

    def snapshot(self):
        with _LOCK:
            return [ac.to_json() for ac in self.aircraft]


# ---------------------------------------------------------
# HTTP SERVER FOR /data.json
# ---------------------------------------------------------

class Dump1090Handler(http.server.BaseHTTPRequestHandler):
    simulator = None

    def do_GET(self):
        if self.path.startswith("/data.json"):
            payload = json.dumps(self.simulator.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, *_):
        pass


def start_http_server(simulator):
    Dump1090Handler.simulator = simulator
    httpd = socketserver.ThreadingTCPServer((HOST, PORT), Dump1090Handler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    return httpd


# ---------------------------------------------------------
# TKINTER CONTROL PANEL
# ---------------------------------------------------------

class ControlPanel(tk.Tk):
    def __init__(self, sim, httpd):
        super().__init__()
        self.title("Simulator Control Panel")

        self.sim = sim
        self.httpd = httpd

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)

        # Number of aircraft
        ttk.Label(frame, text="Aircraft Count").grid(
            row=0, column=0, sticky="w")
        self.aircraft_var = tk.IntVar(value=sim.num_aircraft)
        ac_spin = ttk.Spinbox(frame, from_=1, to=200, textvariable=self.aircraft_var, width=6,
                              command=self.update_aircraft_count)
        ac_spin.grid(row=0, column=1)

        # Update interval
        ttk.Label(frame, text="Update Interval (sec)").grid(
            row=1, column=0, sticky="w")
        self.update_var = tk.DoubleVar(value=sim.update_interval)
        upd_spin = ttk.Spinbox(frame, from_=0.05, to=5.0, increment=0.05,
                               textvariable=self.update_var, width=6,
                               command=self.update_interval)
        upd_spin.grid(row=1, column=1)

        # Radius
        ttk.Label(frame, text="Spawn Radius (km)").grid(
            row=2, column=0, sticky="w")
        self.radius_var = tk.IntVar(value=sim.radius_km)
        r_spin = ttk.Spinbox(frame, from_=20, to=500, textvariable=self.radius_var,
                             width=6, command=self.update_radius)
        r_spin.grid(row=2, column=1)

        # Pause / resume
        self.pause_btn = ttk.Button(
            frame, text="Pause Simulation", command=self.toggle_pause)
        self.pause_btn.grid(row=3, column=0, columnspan=2, pady=10)

        # Status indicators
        ttk.Label(frame, text="HTTP Server:").grid(row=4, column=0, sticky="w")
        self.server_status = ttk.Label(
            frame, text="Running", foreground="green")
        self.server_status.grid(row=4, column=1)

        ttk.Label(frame, text="Aircraft Active:").grid(
            row=5, column=0, sticky="w")
        self.aircraft_status = ttk.Label(frame, text="0", foreground="blue")
        self.aircraft_status.grid(row=5, column=1)

        self.update_status_loop()

    def update_status_loop(self):
        self.aircraft_status.config(text=str(len(self.sim.aircraft)))
        self.after(500, self.update_status_loop)

    def update_aircraft_count(self):
        self.sim.num_aircraft = self.aircraft_var.get()

    def update_interval(self):
        self.sim.update_interval = self.update_var.get()

    def update_radius(self):
        self.sim.radius_km = self.radius_var.get()

    def toggle_pause(self):
        self.sim.running = not self.sim.running
        self.pause_btn.config(
            text="Resume Simulation" if not self.sim.running else "Pause Simulation"
        )


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

        sim = Simulator()
        httpd = start_http_server(sim)
        print(
            f"[ADS-B Simulator] Simulator running at http://{HOST}:{PORT}/data.json")

        ui = ControlPanel(sim, httpd)
        ui.mainloop()

    except Exception as e:
        print("[ADS-B Simulator] Error :", e)
