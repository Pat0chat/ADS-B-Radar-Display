"""
ADS-B Radar v2
Fetches data from dump1090 at http://localhost:8080/data.json and
renders a radar-style view using tkinter Canvas.

Features:
    - Real bearing and position of detected planes
    - Symbols colored by altitude (gradient)
    - History trails per aircraft
    - Tkinter GUI controls
    - Click any aircraft icon to open a details popup with full info

Dependencies:
    - requests
    - pillow (PIL)

Run:
    pip install requests pillow
    python adsb_tk_radar_clickable.py
"""

import tkinter as tk
from tkinter import ttk
import math
import time
import json
import os
from PIL import Image, ImageDraw, ImageTk
from collections import deque

from datasource import Dump1090Source

# ------------------- Configuration -------------------


CONFIG_FILE = "./radar/config.json"
DATA_URL = "http://localhost:8080/data.json"
RADAR_LAT = 48.6833   # default receiver latitude
RADAR_LON = 2.1333    # default receiver longitude
REFRESH_MS = 1000     # update interval in milliseconds
MAX_RANGE_KM = 200    # maximum radar range shown (km)
CANVAS_SIZE = 800     # pixels (square canvas)
TRAIL_MAX = 100       # default number of points in trail
PLOT_SIZE = 32        # default size for detected object in radar view

# ------------------- Utilities -------------------


def load_config():
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


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    lat1r = math.radians(lat1)
    lat2r = math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2r)
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * \
        math.cos(lat2r) * math.cos(dlon)
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360.0) % 360.0


def altitude_to_color(alt):
    """
    Map altitude (feet) to an RGB color string.
    Low alt -> green
    medium -> yellow
    high -> red
    unknown -> gray
    """
    if alt is None:
        return "#888888"
    # clamp
    if alt < 0:
        alt = 0
    # define a reasonable scale: 0 ft -> 0 (green) ; 40000 -> 1 (red)
    t = min(max(alt / 40000.0, 0.0), 1.0)
    # produce a gradient green -> yellow -> orange -> red
    if t < 0.5:
        # green to yellow
        r = int(255 * (t * 2))
        g = 255
        b = 0
    else:
        # yellow to red
        r = 255
        g = int(255 * (1 - (t - 0.5) * 2))
        b = 0
    return f"#{r:02x}{g:02x}{b:02x}"


def speed_to_color(speed):
    """
    Map speed (knots) to a distinct RGB color scale.
    Palette is different from altitude_to_color:
    Slow -> Blue
    Moderate -> Cyan
    Fast -> Green
    Very fast -> Orange
    Extremely fast -> Red
    """

    if speed is None:
        return "#8888ff"    # unknown = bluish

    # Clamp speed to reasonable range
    if speed < 0:
        speed = 0
    if speed > 600:
        speed = 600

    # Normalize 0–600 kt → 0.0–1.0
    t = speed / 600.0

    # Segmented gradient:
    # 0.0–0.25: Blue → Cyan
    # 0.25–0.50: Cyan → Green
    # 0.50–0.75: Green → Orange
    # 0.75–1.00: Orange → Red

    if t < 0.25:
        # Blue (0,0,255) -> Cyan (0,255,255)
        f = t / 0.25
        r = 0
        g = int(255 * f)
        b = 255

    elif t < 0.50:
        # Cyan (0,255,255) -> Green (0,255,0)
        f = (t - 0.25) / 0.25
        r = 0
        g = 255
        b = int(255 * (1 - f))

    elif t < 0.75:
        # Green (0,255,0) -> Orange (255,165,0)
        f = (t - 0.50) / 0.25
        r = int(255 * f)
        g = int(255 - (90 * f))   # 255 → 165
        b = 0

    else:
        # Orange (255,165,0) -> Red (255,0,0)
        f = (t - 0.75) / 0.25
        r = 255
        g = int(165 * (1 - f))
        b = 0

    return f"#{r:02x}{g:02x}{b:02x}"

# ------------------- Plane icon generator -------------------


def make_mil_triangle(size=32, fill="#ffffff", outline="#000000"):
    """MIL-STD 2525 style fixed-wing triangle symbol (point up)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size/2, size/2
    s = size/2.1
    pts = [
        (cx, cy - s),        # Nose
        (cx + s*0.85, cy + s*0.75),
        (cx - s*0.85, cy + s*0.75),
    ]
    draw.polygon(pts, fill=fill, outline=outline, width=2)
    return img


def make_mil_helicopter(size=32, fill="#ffffff", outline="#000000"):
    """Simple MIL-style helicopter icon."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size/2, size/2
    s = size/2

    # body
    draw.ellipse((cx-s*0.3, cy-s*0.3, cx+s*0.3, cy+s*0.3),
                 fill=fill, outline=outline, width=2)

    # rotor bar
    draw.line([(cx - s*0.9, cy - s*0.8),
               (cx + s*0.9, cy - s*0.8)],
              fill=outline, width=3)

    # tail boom
    draw.line([(cx, cy + s*0.3),
               (cx, cy + s*1.2)],
              fill=outline, width=2)

    return img


def make_mil_unknown(size=32, fill="#ffffff", outline="#000000"):
    """Generic 'unknown' diamond symbol."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size/2, size/2
    s = size/2
    pts = [
        (cx,     cy - s),
        (cx + s, cy),
        (cx,     cy + s),
        (cx - s, cy),
    ]
    draw.polygon(pts, fill=fill, outline=outline, width=2)
    return img

# ------------------- Main Application -------------------


class ADSBRadarApp:
    def __init__(self, root):
        self.root = root
        root.title("ADS-B Radar")

        self.center_lat = tk.DoubleVar(value=RADAR_LAT)
        self.center_lon = tk.DoubleVar(value=RADAR_LON)
        self.max_range = tk.DoubleVar(value=MAX_RANGE_KM)
        self.trail_length = tk.IntVar(value=TRAIL_MAX)
        self.paused = tk.BooleanVar(value=False)
        self.show_labels = tk.BooleanVar(value=True)

        self.canvas = tk.Canvas(root, width=CANVAS_SIZE,
                                height=CANVAS_SIZE, bg="#02121a")
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas_width = CANVAS_SIZE
        self.canvas_height = CANVAS_SIZE
        self.canvas.grid(row=0, column=0, sticky="nsew")
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(0, weight=1)
        root.bind("<F11>", lambda e: root.attributes("-fullscreen", True))
        root.bind("<Escape>", lambda e: root.attributes("-fullscreen", False))

        # side controls
        controls = ttk.Frame(root, padding=(6, 6))
        controls.grid(row=0, column=1, sticky="ns")

        ttk.Button(controls, text="Show data table", command=self.show_raw_table).pack(fill="x", pady=(8, 4))

        ttk.Label(controls, text="Center Latitude:").pack(anchor="w")
        ttk.Entry(controls, textvariable=self.center_lat).pack(fill="x")
        ttk.Label(controls, text="Center Longitude:").pack(anchor="w")
        ttk.Entry(controls, textvariable=self.center_lon).pack(fill="x")

        ttk.Label(controls, text="Range (km):").pack(anchor="w", pady=(6, 0))
        ttk.Scale(controls, from_=10, to=500, variable=self.max_range,
                  orient="horizontal").pack(fill="x")

        ttk.Label(controls, text="Trail length:").pack(anchor="w", pady=(6, 0))
        ttk.Scale(controls, from_=0, to=200, variable=self.trail_length,
                  orient="horizontal").pack(fill="x")

        ttk.Checkbutton(controls, text="Show labels", variable=self.show_labels).pack(
            anchor="w", pady=(6, 0))
        ttk.Checkbutton(controls, text="Pause updates",
                        variable=self.paused).pack(anchor="w", pady=(6, 0))

        ttk.Button(controls, text="Refresh view",
                   command=self.refresh_now).pack(fill="x", pady=(6, 0))
        ttk.Button(controls, text='Clear Trails',
                   command=self.clear_trails).pack(fill='x', pady=(6, 0))

        ttk.Label(controls, text="Altitude Legend:").pack(
            anchor="w", pady=(6, 0))

        alt_legend = tk.Canvas(controls, width=140, height=30,
                               bg="#ffffff", highlightthickness=1, highlightbackground="#000")
        alt_legend.pack(pady=(2, 6))

        # Draw horizontal gradient (0 ft → 40,000 ft)
        for x in range(140):
            # map x (0–139) to altitude (0–40000)
            alt = (x / 139) * 40000
            c = altitude_to_color(alt)
            alt_legend.create_line(x, 0, x, 30, fill=c)

        # Tick labels
        alt_legend.create_text(5, 15, anchor="w", text="0 ft", font=(None, 8))
        alt_legend.create_text(135, 15, anchor="e",
                               text="40,000 ft", font=(None, 8))

        ttk.Label(controls, text="Speed Legend:").pack(anchor="w", pady=(6, 4))
        spd_legend = tk.Canvas(controls, width=140, height=30,
                               bg="#ffffff", highlightthickness=1, highlightbackground="#000")
        spd_legend.pack(pady=(2, 6))

        # Draw horizontal gradient (0 kt → 600 kt)
        for x in range(140):
            spd = (x / 139) * 600
            c = speed_to_color(spd)
            spd_legend.create_line(x, 0, x, 30, fill=c)

        # Tick labels
        spd_legend.create_text(5, 15, anchor="w", text="0 kt", font=(None, 8))
        spd_legend.create_text(135, 15, anchor="e",
                               text="600 kt", font=(None, 8))

        ttk.Label(controls, text="Dump1090 Status:").pack(
            anchor="w", pady=(6, 0))
        self.status_label = ttk.Label(
            controls, text="Unknown", foreground="orange")
        self.status_label.pack(anchor="w")
        self.dump1090_alive = False

        ttk.Label(controls, text="Last update:").pack(anchor="w", pady=(4, 0))
        self.status_freshness = ttk.Label(
            controls, text="N/A", foreground="orange")
        self.status_freshness.pack(anchor="w")

        ttk.Label(controls, text="Aircraft count:").pack(
            anchor="w", pady=(4, 0))
        self.status_count = ttk.Label(controls, text="0", foreground="orange")
        self.status_count.pack(anchor="w")

        # State
        self.aircraft_trails = {}  # hex -> deque of (x,y,alt)
        self.aircraft_icons = {}
        self.symbol_fixedwing = make_mil_triangle(
            size=PLOT_SIZE, fill="#ffffff", outline="#333333")
        self.symbol_helicopter = make_mil_helicopter(
            size=PLOT_SIZE, fill="#ffffff", outline="#333333")
        self.symbol_unknown = make_mil_unknown(
            size=PLOT_SIZE, fill="#ffffff", outline="#333333")
        self.aircraft_items = {}

        # Draw static radar background once
        self.draw_background()
        self.running = True

        # Data source
        self.source = Dump1090Source(DATA_URL)
        self.source.start()

        # Start GUI update loop
        self.schedule_update()

    # ------------------- GUI helpers -------------------
    def on_canvas_resize(self, event):
        # update current canvas size
        self.canvas_width = event.width
        self.canvas_height = event.height

        # redraw radar background when canvas changes
        self.draw_background()

    def schedule_update(self):
        if not self.running:
            return
        self.update_frame()
        self.root.after(REFRESH_MS, self.schedule_update)

    def show_raw_table(self):
        win = tk.Toplevel(self.root)
        win.title("Data Table")
        win.geometry("1000x500")

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True)

        # Scrollbars
        xscroll = ttk.Scrollbar(frame, orient="horizontal")
        yscroll = ttk.Scrollbar(frame, orient="vertical")

        columns = [
            "hex", "callsign", "registration", "lat", "lon",
            "altitude", "speed", "track", "vert_rate", 
            "category", "type", "squawk", "last_seen"
        ]

        tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set
        )

        # Attach scrollbars
        yscroll.config(command=tree.yview)
        xscroll.config(command=tree.xview)

        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        tree.pack(fill="both", expand=True)

        # Configure column headings
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
            tree.column(col, width=80, anchor="center")

        # ---- REFRESH FUNCTION ----
        def refresh():
            if not win.winfo_exists():
                return

            # Clear old rows
            for row in tree.get_children():
                tree.delete(row)

            # Insert new rows from dump1090
            data = self.source.snapshot()

            for ac in data:
                row = (
                    ac.get("hex") or ac.get("icao24") or "",
                    ac.get("flight") or ac.get("callsign") or "",
                    ac.get("registration") or ac.get("reg") or "",
                    ac.get("lat") or "",
                    ac.get("lon") or "",
                    ac.get("altitude") or ac.get("alt_baro") or ac.get("alt_geom") or "",
                    ac.get("speed") or ac.get("groundspeed") or "",
                    ac.get("track") or ac.get("heading") or "",
                    ac.get("vert_rate") or "",
                    ac.get("category") or "",
                    ac.get("type") or "",
                    ac.get("squawk") or "",
                    ac.get("seen") or ac.get("last_seen") or "",
                )
                tree.insert("", "end", values=row)

            win.after(1000, refresh)   # update every second

        refresh()

    def refresh_now(self):
        self.draw_background()
        self.update_frame()

    def clear_trails(self):
        self.aircraft_trails.clear()
        self.canvas.delete('trails')

    def km_to_pixels(self, km):
        # converts kilometers (on display) to canvas pixels based on max_range
        # Use the largest possible radius that fits in the resized canvas
        margin = 10   # space between heading rose and border
        radius_px = min(self.canvas_width, self.canvas_height) / 2.0 - margin
        effective_range = self.max_range.get()
        px_per_km = radius_px / effective_range
        return km * px_per_km

    def geo_to_canvas(self, lat, lon):
        # compute distance and bearing, then convert to canvas coords
        dkm = haversine_km(self.center_lat.get(), self.center_lon.get(), lat, lon)
        brg = bearing_deg(self.center_lat.get(), self.center_lon.get(), lat, lon)
        
        # polar to cartesian: we use angle where 0=North, 90=East
        angle_rad = math.radians(brg)

        # Convert km to px only using km_to_pixels()
        dist_px = self.km_to_pixels(dkm)

        x = self.canvas_width/2  + dist_px * math.sin(angle_rad)
        y = self.canvas_height/2 - dist_px * math.cos(angle_rad)

        return x, y, dkm, brg

    def get_icon(self, base_img, color_hex, heading, size=48):
        heading_r = int(round(heading / 5.0) * 5) % 360
        key = (color_hex, heading_r, size)
        if key in self.aircraft_icons:
            return self.aircraft_icons[key]

        # white template icon
        base = base_img

        # convert hex to RGB tuple
        R = int(color_hex[1:3], 16)
        G = int(color_hex[3:5], 16)
        B = int(color_hex[5:7], 16)

        # tint the white plane
        colored = Image.new("RGBA", base.size, (R, G, B, 255))
        mask = base.split()[3]
        colored.putalpha(mask)

        # rotate final colored icon
        rotated = colored.rotate(
            heading_r, expand=True, resample=Image.BICUBIC)

        # cache final icon
        photo = ImageTk.PhotoImage(rotated)
        self.aircraft_icons[key] = photo
        return photo

    # ------------------- Radar rendering -------------------
    def draw_background(self):
        self.canvas.delete("bg")

        cx = self.canvas_width // 2
        cy = self.canvas_height // 2

        # Use shortest canvas dimension for round radar
        margin = 10   # space between heading rose and border
        radius_px = min(self.canvas_width, self.canvas_height) / 2.0 - margin

        # ----- RANGE RINGS -----
        for i in range(1, 5):
            r = radius_px * (i / 4)
            self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                outline="#2b6d6b", dash=(3, 6),
                tags=("bg",)
            )

            # Range label
            km = int(self.max_range.get() * i / 4)
            self.canvas.create_text(
                cx + 5,
                cy - r + 10,
                anchor="nw",
                text=f"{km} km",
                fill="#9be3dc",
                font=(None, 8),
                tags=("bg",)
            )

        # ----- CENTER MARKER -----
        self.canvas.create_oval(
            cx - 6, cy - 6, cx + 6, cy + 6,
            outline="#00ffaa",
            width=2,
            tags=("bg",)
        )
        self.canvas.create_oval(
            cx - 2, cy - 2, cx + 2, cy + 2,
            fill="#00ffaa",
            outline="",
            tags=("bg",)
        )

        # ----- HEADING ROSE -----
        for deg in range(0, 360, 10):
            angle = math.radians(deg)
            sin_a = math.sin(angle)
            cos_a = math.cos(angle)

            # Minor ticks (10°)
            r0 = radius_px * 0.97
            r1 = radius_px

            # Major ticks (every 30°)
            if deg % 30 == 0:
                r0 = radius_px * 0.93

            x0 = cx + r0 * sin_a
            y0 = cy - r0 * cos_a
            x1 = cx + r1 * sin_a
            y1 = cy - r1 * cos_a

            self.canvas.create_line(
                x0, y0, x1, y1,
                fill="#3dd6c6" if deg % 30 == 0 else "#1a9494",
                width=2 if deg % 30 == 0 else 1,
                tags=("bg",)
            )

            # Cardinal letters (N/E/S/W)
            if deg in (0, 90, 180, 270):
                lx = cx + (radius_px * 0.90) * sin_a
                ly = cy - (radius_px * 0.90) * cos_a
                letter = {0:"N", 90:"E", 180:"S", 270:"W"}[deg]

                self.canvas.create_text(
                    lx, ly,
                    text=letter,
                    fill="#9be3dc",
                    font=(None, 14, "bold"),
                    tags=("bg",)
                )

    def update_frame(self):
        # Connection status
        if self.source.alive:
            self.status_label.configure(text="Connected", foreground="green")
        else:
            self.status_label.configure(text="No response", foreground="red")

        # Last updated
        if self.source.alive:
            self.status_freshness.configure(text=self.source.last_seen(), foreground="green")
        else:
            self.status_freshness.configure(text="No data", foreground="red")

        # Aircraft count
        aircrafts_count = self.source.aircrafts_count()
        if aircrafts_count > 0 :
            self.status_count.configure(text=str(aircrafts_count), foreground="green")
        else:
            self.status_count.configure(text="--", foreground="gray")

        # Pause
        if self.paused.get():
            return

        data = self.source.snapshot()

        self.canvas.delete("aircraft")
        self.canvas.delete("trails")
        self.aircraft_items = {}
        seen_hexes = set()

        # process aircraft
        for ac in data:
            if not (ac.get("lat") and ac.get("lon")):
                continue
            hexid = ac.get("hex") or ac.get("icao24") or ac.get(
                "flight") or str(ac.get("id", ""))
            lat = ac.get("lat")
            lon = ac.get("lon")

            # dump1090 fields may vary; try several
            altitude = ac.get("altitude") or ac.get(
                "alt_baro") or ac.get("alt_geom") or ac.get("alt")

            track = ac.get("track") if ac.get(
                "track") is not None else (ac.get("heading") or 0)
            callsign = ac.get("flight") or ac.get("callsign") or ""
            reg = ac.get("reg") or ac.get("registration") or ""

            # attempt to extract speed (kts) and vertical speed (fpm)
            speed = ac.get("speed") or ac.get(
                "groundspeed") or ac.get("gs") or ac.get("spd")
            vertical_rate = ac.get("vert_rate") or 0

            x, y, dkm, brg = self.geo_to_canvas(lat, lon)

            # skip outside max range
            if dkm > self.max_range.get():
                continue

            seen_hexes.add(hexid)

            # update trail
            trail = self.aircraft_trails.get(hexid)
            if trail is None:
                trail = deque(maxlen=self.trail_length.get())
                self.aircraft_trails[hexid] = trail
            trail.append((x, y, altitude))

            # draw trail
            if len(trail) > 1 and self.trail_length.get() > 0:
                n = len(trail)
                for idx in range(1, n):
                    ax, ay, alt1 = trail[idx-1]
                    bx, by, alt2 = trail[idx]
                    seg_age = idx/max(1, n)
                    width = max(1, int(3*(1-seg_age)))
                    # interpolate color between start and end of segment
                    col1 = altitude_to_color(alt1)
                    col2 = altitude_to_color(alt2)
                    r = int(int(col1[1:3], 16)*(1-seg_age) +
                            int(col2[1:3], 16)*seg_age)
                    g = int(int(col1[3:5], 16)*(1-seg_age) +
                            int(col2[3:5], 16)*seg_age)
                    b = int(int(col1[5:7], 16)*(1-seg_age) +
                            int(col2[5:7], 16)*seg_age)
                    fade_color = f"#{r:02x}{g:02x}{b:02x}"
                    self.canvas.create_line(
                        ax, ay, bx, by, fill=fade_color, width=width, tags=("trails",))

            # draw aircraft icon
            category = ac.get("category") or ""
            category = category.upper()

            base = None
            if category.startswith("A"):     # Fixed-wing
                base = self.symbol_fixedwing
            elif category.startswith("B"):   # Rotorcraft
                base = self.symbol_helicopter
            else:
                base = self.symbol_unknown
            icon = self.get_icon(base, "#ffffff", track, size=40)

            # Place image centered
            img_id = self.canvas.create_image(
                x, y, image=icon, tags=("aircraft",))

            # Heading / speed vector
            base_len = 10
            spd = (speed or 0)

            # speed extends line slightly
            vector_len = base_len + spd * 0.07

            vect_speed_color = speed_to_color(spd)

            angle_rad = math.radians(track)

            x2 = x + vector_len * math.sin(angle_rad)
            y2 = y - vector_len * math.cos(angle_rad)

            self.canvas.create_line(
                x, y, x2, y2,
                fill=vect_speed_color,
                width=1,
                arrow=tk.LAST,
                arrowshape=(8, 10, 4),
                tags=("aircraft",)
            )

            # Store data
            self.aircraft_items[img_id] = {
                "hex": hexid,
                "callsign": callsign,
                "registration": reg,
                "category": category,
                "lat": lat,
                "lon": lon,
                "altitude": altitude,
                "track": track,
                "distance": round(dkm, 2),
                "bearing": round(brg, 1),
                "speed": speed,
                "vert_rate": vertical_rate,
                "last_seen": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            }

            # Attach label (as separate canvas items but tagged 'aircraft' too)
            if self.show_labels.get():
                label = callsign or reg or hexid
                lab_txt = f"{label}\n{int(dkm)} km {altitude or '?'} ft"
                self.canvas.create_text(
                    x + 10, y + 10, text=lab_txt, anchor="nw", fill="#e6ffff", font=(None, 8), tags=("aircraft",))

        for h in list(self.aircraft_trails.keys()):
            if h not in seen_hexes:
                del self.aircraft_trails[h]

    # ------------------- Aircraft click -------------------
    def on_canvas_click(self, event):
        radius = 8
        items = self.canvas.find_overlapping(event.x-radius, event.y-radius,
                                             event.x+radius, event.y+radius)
        for it in reversed(items):
            if it in self.aircraft_items:
                self.show_aircraft_popup(self.aircraft_items[it])
                return

    def show_aircraft_popup(self, ac_initial):
        """Open a popup for an aircraft and keep updating its info."""
        hexid = ac_initial["hex"]

        win = tk.Toplevel(self.root)
        title = ac_initial.get("callsign") or hexid or "Aircraft"
        win.title(f"Aircraft — {title}")
        win.geometry("360x260")

        frm = ttk.Frame(win, padding=8)
        frm.pack(fill="both", expand=True)

        txt = tk.Text(frm, width=44, height=10, wrap="word")
        txt.pack(fill="both", expand=True)

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_frame, text="Close",
                   command=win.destroy).pack(side="right")

        def refresh_popup():
            """Refresh popup every second with latest info."""
            # If window was closed, stop refresh
            if not win.winfo_exists():
                return

            # Find latest data for this aircraft
            latest = None
            for item in self.aircraft_items.values():
                if item["hex"] == hexid:
                    latest = item
                    break

            # If aircraft gone → close popup
            if latest is None:
                txt.configure(state="normal")
                txt.delete("1.0", "end")
                txt.insert("1.0", "Aircraft no longer in range.")
                txt.configure(state="disabled")
                return

            # Build updated text
            lines = [
                f"Hex: {latest.get('hex')}",
                f"Callsign: {latest.get('callsign')}",
                f"Registration: {latest.get('registration')}",
                f"Category: {latest.get('category')}",
                f"Latitude: {latest.get('lat'):.6f}",
                f"Longitude: {latest.get('lon'):.6f}",
                f"Altitude: {latest.get('altitude')} ft",
                f"Distance: {latest.get('distance')} km",
                f"Bearing: {latest.get('bearing')}°",
                f"Track: {latest.get('track')}°",
                f"Speed: {latest.get('speed')} kts",
                f"Vertical speed: {latest.get('vert_rate')} fpm",
                f"Last seen: {latest.get('last_seen')}",
            ]

            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", "\n".join([l for l in lines if l]))
            txt.configure(state="disabled")

            # Schedule next refresh
            win.after(1000, refresh_popup)

        # Start updating loop
        refresh_popup()

    # ------------------- Cleanup -------------------

    def stop(self):
        self.running = False


# ------------------- Run -------------------
if __name__ == "__main__":
    # try:
        print("[ADS-B Radar] Launching ADS-B Radar")

        # load config.json
        cfg = load_config()
        if "data_url" in cfg:
            DATA_URL = cfg["data_url"]
        if "radar_lat" in cfg:
            RADAR_LAT = float(cfg["radar_lat"])
        if "radar_lon" in cfg:
            RADAR_LON = float(cfg["radar_lon"])
        if "refresh_ms" in cfg:
            REFRESH_MS = int(cfg["refresh_ms"])
        if "max_range_km" in cfg:
            MAX_RANGE_KM = int(cfg["max_range_km"])
        if "canvas_size" in cfg:
            CANVAS_SIZE = int(cfg["canvas_size"])
        if "trail_max" in cfg:
            TRAIL_MAX = int(cfg["trail_max"])
        if "plot_size" in cfg:
            PLOT_SIZE = int(cfg["plot_size"])

        print("[ADS-B Radar] **** Setup ****")
        print("[ADS-B Radar] Dump1090 URL: " + DATA_URL)
        print("[ADS-B Radar] Radar lat: " + str(RADAR_LAT))
        print("[ADS-B Radar] Radar long: " + str(RADAR_LON))
        print("[ADS-B Radar] Refresh: " + str(REFRESH_MS))
        print("[ADS-B Radar] Max range (km): " + str(MAX_RANGE_KM))
        print("[ADS-B Radar] Canvas size: " + str(CANVAS_SIZE))
        print("[ADS-B Radar] Trail max: " + str(TRAIL_MAX))
        print("[ADS-B Radar] Plot size: " + str(PLOT_SIZE))
        print("[ADS-B Radar] ****")

        root = tk.Tk()
        app = ADSBRadarApp(root)

        def on_close():
            app.stop()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.mainloop()

    # except Exception as e:
        print("[ADS-B Radar] Error :", e)
