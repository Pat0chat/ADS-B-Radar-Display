#!/usr/bin/env python3
"""
Radar ADS-B Tkinter complet
- Lecture des avions depuis dump1090 (http://localhost:8080/data.json)
- Animation fluide 30 FPS (interpolation)
- Symbole avion stylé et orienté selon le cap (track)
- Historique des trajectoires
- Clic sur avion -> popup d'infos
- Edition et sauvegarde de la position dans config.json via bouton "Modifier la position"
"""

import tkinter as tk
import requests
import math
import threading
import time
import json
import os
from collections import defaultdict

# ---------------------------
# Configuration par défaut
# ---------------------------
DUMP1090_URL = "http://localhost:8080/data.json"
CONFIG_FILE = "config.json"

# Posision station
LAT = 48.6833
LONG = 2.1333

# Paramètres radar
RANGE_KM = 200
HISTORY_LENGTH = 50
FPS = 25
FRAME_DELAY_MS = int(1000 / FPS)

# Fateur de lissage (0 < alpha <= 1).
# Plus proche de 1 => moins lissage (saut direct), plus petit => très lisse.
SMOOTH_ALPHA = 0.50

# ---------------------------
# Utilitaires : config
# ---------------------------
def load_config():
    if os.path.exists(CONFIG_FILE):
        print("[ADS-B Radar] Reading config file")
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data
        except Exception:
            return {}
    else:
        print("[ADS-B Radar] No config file")
    return {}

# ---------------------------
# Calcul géo
# ---------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def latlon_to_canvas(lat, lon, w, h, station_lat, station_lon, range_km):
    dist = haversine_km(station_lat, station_lon, lat, lon)
    if dist > range_km:
        return None
    dx = lon - station_lon
    dy = lat - station_lat
    angle = math.atan2(dx, dy)  # angle polaire autour du centre
    radius = (dist / range_km) * (min(w, h) / 2 - 40)
    x = w/2 + radius * math.sin(angle)
    y = h/2 - radius * math.cos(angle)
    return x, y, dist, angle

# ---------------------------
# Symbole avion stylé (points de base) -> rotation + translation
# ---------------------------
def airplane_shape_points(x, y, angle_rad, size=14):
    """
    Forme stylisée de l'avion autour de (0,0) avant rotation :
      - nez au y négatif
      - ailes latérales
      - queue simplifiée
    Retourne liste de coords [x1,y1,...].
    """
    # Points avant rotation (relative au centre)
    shape = [
        (0, -size*1.0),         # nez
        (size*0.6, size*0.5),   # aile droite
        (size*0.15, size*0.25), # bas du fuselage
        (-size*0.15, size*0.25),# bas du fuselage gauche
        (-size*0.6, size*0.5),  # aile gauche
    ]
    pts = []
    ca = math.cos(angle_rad)
    sa = math.sin(angle_rad)
    for px, py in shape:
        rx = x + px * ca - py * sa
        ry = y + px * sa + py * ca
        pts.extend((rx, ry))
    return pts

# ---------------------------
# Classe principale GUI
# ---------------------------
class RadarApp:
    def __init__(self):
        # position de la station (sera initialisée)
        self.dump1090_url = DUMP1090_URL
        self.station_lat = LAT
        self.station_lon = LONG
        self.radar_range = RANGE_KM
        self.radar_history = HISTORY_LENGTH
        self.display_fps = FPS
        self.display_smooth = SMOOTH_ALPHA
        self.frame_delay_ms = int(1000 / self.display_fps)

        # données aéronefs (dernière récupération brute de dump1090)
        self.aircraft_raw = []   # liste d'obj dicts
        # map icao -> last full aircraft dict
        self.aircraft_map = {}

        # historique (pour tracés)
        self.history = defaultdict(list)  # icao -> list of (x,y)

        # positions visuelles interpolées: icao -> {'x', 'y', 'angle'}
        self.disp = {}

        # GUI init
        self.root = tk.Tk()
        self.root.title("Radar ADS-B - Dump1090")

        # load config.json
        cfg = load_config()
        if "station_lat" in cfg and "station_lon" in cfg:
            try:
                self.dump1090_url = cfg["dump1090_url"]
                self.station_lat = float(cfg["station_lat"])
                self.station_lon = float(cfg["station_lon"])
                self.radar_range = int(cfg["radar_range"])
                self.radar_history = int(cfg["radar_history"])
                self.display_fps = int(cfg["display_fps"])
                self.display_smooth = float(cfg["display_smooth"])
                self.frame_delay_ms = int(1000 / self.display_fps)

                print("[ADS-B Radar] **** Setup ****")
                print("[ADS-B Radar] Dump1090 URL: " + self.dump1090_url)
                print("[ADS-B Radar] Station lat: " + str(self.station_lat))
                print("[ADS-B Radar] Station long: " + str(self.station_lon))
                print("[ADS-B Radar] Radar range: " + str(self.radar_range))
                print("[ADS-B Radar] Radar history: " + str(self.radar_history))
                print("[ADS-B Radar] Display FPS: " + str(self.display_fps))
                print("[ADS-B Radar] Display smooth: " + str(self.display_smooth))
                print("[ADS-B Radar] Display frame delay: " + str(self.frame_delay_ms))
                print("[ADS-B Radar] ****")
            except Exception:
                print("[ADS-B Radar] **** Error in setup file")
                self.dump1090_url = DUMP1090_URL
                self.station_lat = LAT
                self.station_lon = LONG
                self.radar_range = RANGE_KM
                self.radar_history = HISTORY_LENGTH
                self.display_fps = FPS
                self.display_smooth = SMOOTH_ALPHA
                self.frame_delay_ms = int(1000 / FPS)
        else:
            print("[ADS-B Radar] Station position not provided in config file")
            self.root.destroy()

        print("[ADS-B Radar] Build UI")
        self.build_ui()

        # thread pour fetcher les données
        print("[ADS-B Radar] Launching data thread")
        self.fetch_thread = threading.Thread(target=self.fetch_loop, daemon=True)
        self.fetch_thread.start()

        # boucle mainloop
        print("[ADS-B Radar] UI mainloop")
        self.root.mainloop()

    # ---------------------------
    # UI building
    # ---------------------------
    def build_ui(self):
        # Canvas radar
        self.canvas_size = 900
        self.canvas = tk.Canvas(self.root, width=self.canvas_size, height=self.canvas_size, bg="black")
        self.canvas.pack(padx=6, pady=6)

        # Draw fixed background once
        self.draw_background()

        # Info label bottom
        self.status_var = tk.StringVar()
        self.status_var.set("Démarrage...")
        status_label = tk.Label(self.root, textvariable=self.status_var)
        status_label.pack(fill="x")

        # bind click
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        # start animation loop
        self.root.after(self.frame_delay_ms, self.animation_frame)

    # ---------------------------
    # Dessine le fond radar (cercles + axes)
    # ---------------------------
    def draw_background(self):
        w = self.canvas_size
        h = self.canvas_size
        self.canvas.delete("bg")
        # cercles concentriques (5 cercles pour 1..5)
        for i in range(1, 6):
            radius = i * (min(w, h) / 2) / 6
            self.canvas.create_oval(w/2 - radius, h/2 - radius, w/2 + radius, h/2 + radius,
                                    outline="#004400", width=2, tag="bg")
            # label distance
            dist_label = int((i * self.radar_range / 6))
            self.canvas.create_text(w/2 + 4, h/2 - radius - 8, text=f"{dist_label} km",
                                    fill="#00ff88", anchor="w", font=("Arial", 9), tag="bg")
        # axes
        self.canvas.create_line(w/2, 0, w/2, h, fill="#003300", width=2, tag="bg")
        self.canvas.create_line(0, h/2, w, h/2, fill="#003300", width=2, tag="bg")
        # center marker
        self.canvas.create_oval(w/2 - 6, h/2 - 6, w/2 + 6, h/2 + 6, fill="#00ff88", outline="", tag="bg")

    # ---------------------------
    # Thread de récupération des données (1 Hz)
    # ---------------------------
    def fetch_loop(self):
        while True:
            try:
                resp = requests.get(self.dump1090_url, timeout=3)
                data = resp.json()
                # store last raw
                self.aircraft_raw = data
                # build aircraft_map by hex
                amap = {}
                for ac in data:
                    hexid = ac.get("hex")
                    if hexid:
                        amap[hexid] = ac
                self.aircraft_map = amap
                # status
                self.status_var.set(f"{len(data)} targets - station: {self.station_lat}, {self.station_lon}")
            except Exception as e:
                # keep prior data if fetch fails
                self.status_var.set(f"Erreur lecture dump1090: {e}")
            time.sleep(1)

    # ---------------------------
    # Gestion du clic : trouver l'avion cliqué et ouvrir popup info
    # ---------------------------
    def on_canvas_click(self, event):
        # pick nearby items
        x, y = event.x, event.y
        items = self.canvas.find_overlapping(x-6, y-6, x+6, y+6)
        # recherche d'un tag plane_<hex>
        for it in items:
            tags = self.canvas.gettags(it)
            for t in tags:
                if t.startswith("plane_"):
                    icao = t.split("_", 1)[1]
                    ac = self.aircraft_map.get(icao)
                    if ac:
                        self.show_plane_info(ac)
                        return

    def show_plane_info(self, ac):
        win = tk.Toplevel(self.root)
        ident = ac.get("flight") or ac.get("hex", "N/A")
        win.title(f"Info - {ident}")
        win.geometry("360x260")
        txt = tk.Text(win, wrap="word")
        txt.pack(expand=True, fill="both")
        lat = ac.get("lat", "N/A")
        lon = ac.get("lon", "N/A")
        alt = ac.get("altitude", "N/A")
        spd = ac.get("speed", "N/A")
        trk = ac.get("track", "N/A")
        hexid = ac.get("hex", "N/A")
        dist = "N/A"
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and self.station_lat is not None:
            try:
                dist = haversine_km(self.station_lat, self.station_lon, lat, lon)
                dist = f"{dist:.1f} km"
            except:
                pass
        content = (
            f"ICAO hex : {hexid}\n"
            f"Indicatif : {ac.get('flight','N/A')}\n"
            f"Latitude : {lat}\n"
            f"Longitude : {lon}\n"
            f"Altitude : {alt} ft\n"
            f"Vitesse : {spd} kt\n"
            f"Cap (track) : {trk}°\n"
            f"Distance station : {dist}\n"
            f"\nToutes les données proviennent de dump1090."
        )
        txt.insert("1.0", content)
        txt.config(state="disabled")

    # ---------------------------
    # Boucle d'animation (toutes les FRAME_DELAY_MS)
    # ---------------------------
    def animation_frame(self):
        # suppression des avions précédents (mais pas du fond 'bg')
        self.canvas.delete("plane")
        w = self.canvas_size
        h = self.canvas_size

        # convertir chaque avion en coord canvas cible
        targets = {}  # icao -> {'x','y','angle','dist','ac'}
        for ac in self.aircraft_raw:
            if "lat" not in ac or "lon" not in ac:
                continue
            lat = ac.get("lat")
            lon = ac.get("lon")
            hexid = ac.get("hex")
            if not hexid:
                continue
            mapped = latlon_to_canvas(lat, lon, w, h, self.station_lat, self.station_lon, self.radar_range)
            if not mapped:
                continue
            x_t, y_t, dist, polar_angle = mapped
            # cap pour orienter le symbole -> prefers 'track' field (degrees)
            track = ac.get("track")
            try:
                track_deg = float(track)
            except Exception:
                # fallback to computing bearing from station->plane
                track_deg = math.degrees(polar_angle) % 360
            angle_rad = math.radians(track_deg)
            targets[hexid] = {"x": x_t, "y": y_t, "angle": angle_rad, "dist": dist, "ac": ac}

        # update interpolation positions
        # remove disp entries not in targets (we keep them a bit to fade maybe, but here remove)
        for icao in list(self.disp.keys()):
            if icao not in targets:
                # gradually fade out by popping after a while - for simplicity remove immediately
                del self.disp[icao]

        for icao, tgt in targets.items():
            tx, ty = tgt["x"], tgt["y"]
            tangle = tgt["angle"]
            # init if needed
            if icao not in self.disp:
                self.disp[icao] = {"x": tx, "y": ty, "angle": tangle}
            # exponential smoothing (lerp)
            cur = self.disp[icao]
            cur["x"] = cur["x"] + (tx - cur["x"]) * SMOOTH_ALPHA
            cur["y"] = cur["y"] + (ty - cur["y"]) * SMOOTH_ALPHA
            # angle smoothing - handle angle wrap-around properly
            a0 = cur["angle"]
            a1 = tangle
            # compute shortest diff
            diff = (a1 - a0 + math.pi) % (2*math.pi) - math.pi
            cur["angle"] = a0 + diff * SMOOTH_ALPHA

            # update history with displayed pos (for trail)
            self.history[icao].append((cur["x"], cur["y"]))
            if len(self.history[icao]) > self.radar_history:
                self.history[icao].pop(0)

            # draw trajectory
            hist = self.history[icao]
            if len(hist) > 1:
                pts = []
                for px, py in hist:
                    pts.extend((px, py))
                # line slightly transparent-ish via darker color
                self.canvas.create_line(pts, fill="#2f2f2f", width=2, tag=("plane", f"plane_{icao}"))

            # draw airplane symbol
            # color from altitude (0..40000 -> green->yellow)
            alt = tgt["ac"].get("altitude", 0) or 0
            cval = int(min(255, max(0, (alt / 40000.0) * 255)))
            color = f"#{cval:02x}{cval:02x}00"
            pts = airplane_shape_points(cur["x"], cur["y"], cur["angle"], size=14)
            poly = self.canvas.create_polygon(pts, fill=color, outline="#000000", width=1, tag=("plane", f"plane_{icao}"))

            # label (flight + alt)
            flight = tgt["ac"].get("flight", "").strip() or ""
            label = f"{flight} {int(alt)}ft" if flight else f"{int(alt)}ft"
            txt = self.canvas.create_text(cur["x"] + 16, cur["y"] - 12, text=label, fill="white", font=("Arial", 9), tag=("plane", f"plane_{icao}"))

            # update aircraft_map so click shows latest info
            self.aircraft_map[icao] = tgt["ac"]

        # schedule next frame
        self.root.after(self.frame_delay_ms, self.animation_frame)

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    try:
        print("[ADS-B Radar] Launching ADS-B Radar")
        app = RadarApp()
    except Exception as e:
        print("[ADS-B Radar] Error :", e)
