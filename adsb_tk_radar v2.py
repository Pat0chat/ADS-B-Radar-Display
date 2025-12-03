"""
ADS-B Radar v2
Fetches data from dump1090 at http://localhost:8080/data.json and
renders a radar-style view using tkinter Canvas.

Features:
- Real (generated) airplane icons rotated by track
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
import requests
import math
import time
from PIL import Image, ImageDraw, ImageTk
from collections import deque

# ------------------- Configuration -------------------
DATA_URL = "http://localhost:8080/data.json"
RADAR_LAT = 48.6833   # default receiver latitude
RADAR_LON = 2.1333   # default receiver longitude
REFRESH_MS = 1000  # update interval in milliseconds
MAX_RANGE_KM = 200  # maximum radar range shown (km)
CANVAS_SIZE = 800   # pixels (square canvas)
TRAIL_MAX = 100     # default number of points in trail

# ------------------- Utilities -------------------

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
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360.0) % 360.0


def altitude_to_color(alt):
    """Map altitude (feet) to an RGB color string.
    Low alt -> green, medium -> yellow, high -> red, unknown -> gray.
    """
    if alt is None:
        return "#888888"
    # clamp
    if alt < 0:
        alt = 0
    # define a reasonable scale: 0 ft -> 0 (green) ; 35000+ -> 1 (red)
    t = min(max(alt / 35000.0, 0.0), 1.0)
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

# ------------------- Plane icon generator -------------------

def make_plane_image(size=48, fill="#ffffff", outline="#000000"):
    """Return a PIL Image of a simple plane silhouette pointing up (0 deg).
    We'll draw a stylized aircraft and later rotate it for heading.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = size / 2
    cy = size / 2
    scale = size / 2.6
    # Define polygon relative to center, pointing upward
    pts = [
        (cx, cy - 1.0 * scale),  # nose
        (cx + 0.18 * scale, cy - 0.15 * scale),
        (cx + 0.45 * scale, cy - 0.1 * scale),
        (cx + 0.2 * scale, cy + 0.4 * scale),
        (cx + 0.05 * scale, cy + 0.45 * scale),
        (cx, cy + 0.25 * scale),
        (cx - 0.05 * scale, cy + 0.45 * scale),
        (cx - 0.2 * scale, cy + 0.4 * scale),
        (cx - 0.45 * scale, cy - 0.1 * scale),
        (cx - 0.18 * scale, cy - 0.15 * scale),
    ]
    draw.polygon(pts, fill=fill, outline=outline)
    # add cockpit window
    r = int(size * 0.06)
    draw.ellipse((cx - r, cy - scale * 0.6 - r, cx + r, cy - scale * 0.6 + r), fill=(0, 0, 0, 150))
    return img

# ------------------- Main Application -------------------

class ADSBRadarApp:
    def __init__(self, root):
        self.root = root
        root.title("ADS-B Radar")

        self.center_lat = tk.DoubleVar(value=RADAR_LAT)
        self.center_lon = tk.DoubleVar(value=RADAR_LON)
        self.max_range = tk.DoubleVar(value=MAX_RANGE_KM)
        self.zoom = tk.DoubleVar(value=1.0)  # scale multiplier
        self.trail_length = tk.IntVar(value=TRAIL_MAX)
        self.paused = tk.BooleanVar(value=False)
        self.show_labels = tk.BooleanVar(value=True)

        self.canvas = tk.Canvas(root, width=CANVAS_SIZE, height=CANVAS_SIZE, bg="#02121a")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        # side controls
        controls = ttk.Frame(root, padding=(6,6))
        controls.grid(row=0, column=1, sticky="ns")

        ttk.Label(controls, text="Center Latitude:").pack(anchor="w")
        ttk.Entry(controls, textvariable=self.center_lat).pack(fill="x")
        ttk.Label(controls, text="Center Longitude:").pack(anchor="w")
        ttk.Entry(controls, textvariable=self.center_lon).pack(fill="x")

        ttk.Label(controls, text="Range (km):").pack(anchor="w", pady=(6,0))
        ttk.Scale(controls, from_=50, to=500, variable=self.max_range, orient="horizontal").pack(fill="x")

        ttk.Label(controls, text="Zoom: ").pack(anchor="w", pady=(6,0))
        ttk.Scale(controls, from_=0.2, to=3.0, variable=self.zoom, orient="horizontal").pack(fill="x")

        ttk.Label(controls, text="Trail length:").pack(anchor="w", pady=(6,0))
        ttk.Scale(controls, from_=0, to=100, variable=self.trail_length, orient="horizontal").pack(fill="x")

        ttk.Checkbutton(controls, text="Show labels", variable=self.show_labels).pack(anchor="w", pady=(6,0))
        ttk.Checkbutton(controls, text="Pause updates", variable=self.paused).pack(anchor="w", pady=(6,0))

        ttk.Button(controls, text="Center to current vars", command=self.center_to_vars).pack(fill="x", pady=(6,0))
        ttk.Button(controls, text="Refresh now", command=self.refresh_now).pack(fill="x", pady=(6,4))

        ttk.Label(controls, text="Legend:").pack(anchor="w", pady=(6,0))
        legend = tk.Canvas(controls, width=120, height=70, bg="#ffffff")
        legend.pack(pady=(2,0))
        legend.create_rectangle(4,4,116,66, outline="#000")
        legend.create_text(8,12, anchor="w", text="Altitude color", font=(None,8))
        legend.create_rectangle(8,28,40,40, fill=altitude_to_color(0), outline="#000")
        legend.create_text(44,34, anchor="w", text="Ground" , font=(None,8))
        legend.create_rectangle(8,44,40,56, fill=altitude_to_color(20000), outline="#000")
        legend.create_text(44,50, anchor="w", text="20k ft", font=(None,8))

        # layout adjustments
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # state
        self.aircraft_trails = {}  # hex -> deque of (x_pix, y_pix)
        self.aircraft_icons = {}   # cache of rotated PhotoImage keyed by (color, heading_rounded, size)
        self.plane_base_img = make_plane_image(size=64, fill="#ffffff", outline="#000000")
        self.aircraft_items = {}   # canvas item id -> aircraft data dict

        # draw static radar background once
        self.draw_background()

        # schedule updates
        self._after_id = None
        self.running = True
        self.schedule_update()

    def center_to_vars(self):
        # just redraw background to reflect new center/range
        self.draw_background()

    def refresh_now(self):
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.update_frame()
        self.schedule_update()

    def schedule_update(self):
        if not self.running:
            return
        self._after_id = self.root.after(REFRESH_MS, self.update_frame)

    def draw_background(self):
        self.canvas.delete("bg")
        size = CANVAS_SIZE
        cx = size//2
        cy = size//2
        maxr = self.max_range.get()
        # rings and labels
        ring_count = 4
        for i in range(1, ring_count+1):
            r_km = maxr * i / ring_count
            r_pix = self.km_to_pixels(r_km)
            self.canvas.create_oval(cx-r_pix, cy-r_pix, cx+r_pix, cy+r_pix, outline="#2b6d6b", dash=(3,5), tags=("bg",))
            self.canvas.create_text(cx + 5, cy - r_pix + 10, anchor="nw", text=f"{int(r_km)} km", fill="#9be3dc", font=(None,8), tags=("bg",))
        # compass N
        self.canvas.create_text(cx, 10, text="N", fill="#9be3dc", font=(None,12,"bold"), tags=("bg",))

    def km_to_pixels(self, km):
        # converts kilometers (on display) to canvas pixels based on max_range and zoom
        px_per_radius = (CANVAS_SIZE/2.0) / (self.max_range.get() * self.zoom.get())
        return km * px_per_radius

    def geo_to_canvas(self, lat, lon):
        # compute distance and bearing, then convert to canvas coords
        dkm = haversine_km(self.center_lat.get(), self.center_lon.get(), lat, lon)
        brg = bearing_deg(self.center_lat.get(), self.center_lon.get(), lat, lon)
        # polar to cartesian: we use angle where 0=North, 90=East
        angle_rad = math.radians(brg)
        x_km = dkm * math.sin(angle_rad)
        y_km = dkm * math.cos(angle_rad)
        x_pix = CANVAS_SIZE/2 + x_km * (CANVAS_SIZE/2.0) / (self.max_range.get() * self.zoom.get())
        y_pix = CANVAS_SIZE/2 - y_km * (CANVAS_SIZE/2.0) / (self.max_range.get() * self.zoom.get())
        return x_pix, y_pix, dkm, brg

    def fetch_data(self):
        try:
            r = requests.get(DATA_URL, timeout=0.9)
            data = r.json()
            return data
        except Exception as e:
            # print("Fetch error:", e)
            return []

    def get_icon(self, color_hex, heading, size=48):
        # round heading to 5 degrees to limit cache
        heading_r = int(round(heading / 5.0) * 5) % 360
        key = (color_hex, heading_r, size)
        if key in self.aircraft_icons:
            return self.aircraft_icons[key]
        # produce a colored plane silhouette by tinting base image
        base = self.plane_base_img.resize((size, size), resample=Image.LANCZOS)
        # colorize: multiply white silhouette by color
        color_rgb = tuple(int(color_hex[i:i+2], 16) for i in (1,3,5))
        colored = Image.new("RGBA", base.size)
        mask = base.split()[3]
        solid = Image.new("RGBA", base.size, color_rgb + (0,))
        colored.paste(solid, (0,0), mask=mask)
        # overlay outline in black
        colored = Image.alpha_composite(colored, base)
        # rotate so that heading 0 points north -> our plane base points up so rotate by heading
        rotated = colored.rotate(heading_r, resample=Image.BICUBIC, expand=True)
        photo = ImageTk.PhotoImage(rotated)
        self.aircraft_icons[key] = photo
        return photo

    def update_frame(self):
        if self.paused.get():
            self.schedule_update()
            return

        data = self.fetch_data()
        # clear dynamic items
        self.canvas.delete("aircraft")
        self.canvas.delete("trails")

        # reset mapping for this frame
        self.aircraft_items = {}

        seen_hexes = set()
        # process aircraft
        for ac in data:
            if not (ac.get("lat") and ac.get("lon")):
                continue
            hexid = ac.get("hex") or ac.get("icao24") or ac.get("flight") or str(ac.get("id", ""))
            lat = ac.get("lat")
            lon = ac.get("lon")
            # dump1090 fields may vary; try several
            altitude = ac.get("altitude") or ac.get("alt_baro") or ac.get("alt_geom") or ac.get("alt")
            track = ac.get("track") if ac.get("track") is not None else (ac.get("heading") or 0)
            callsign = ac.get("flight") or ac.get("callsign") or ""
            reg = ac.get("reg") or ac.get("registration") or ""

            # attempt to extract speed (kts)
            speed = ac.get("speed") or ac.get("groundspeed") or ac.get("gs") or ac.get("spd")

            x, y, dkm, brg = self.geo_to_canvas(lat, lon)
            # skip outside max range * zoom
            if dkm > self.max_range.get() * self.zoom.get():
                continue

            seen_hexes.add(hexid)

            # update trail
            trail = self.aircraft_trails.get(hexid)
            if trail is None:
                trail = deque(maxlen=self.trail_length.get())
                self.aircraft_trails[hexid] = trail
            trail.append((x, y))

            # draw trail
            if len(trail) > 1 and self.trail_length.get() > 0:
                n = len(trail)
                for idx in range(1, n):
                    ax, ay = trail[idx-1]
                    bx, by = trail[idx]
                    seg_age = idx / max(1, n)
                    width = max(1, int(4 * seg_age))
                    color = altitude_to_color(altitude)
                    self.canvas.create_line(ax, ay, bx, by, fill=color, width=width, tags=("trails",))

            # draw aircraft icon
            color = altitude_to_color(altitude)
            icon = self.get_icon(color, track, size=40)
            # Place image centered
            img_id = self.canvas.create_image(x, y, image=icon, tags=("aircraft",))
            # store aircraft info for click-popup (remember to include reference time)
            ac_data = {
                "hex": hexid,
                "callsign": callsign,
                "registration": reg,
                "lat": lat,
                "lon": lon,
                "altitude_ft": altitude,
                "track_deg": track,
                "distance_km": round(dkm, 2),
                "bearing_deg": round(brg, 1),
                "speed": speed,
                "last_seen": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            }
            self.aircraft_items[img_id] = ac_data

            # attach label (as separate canvas items but tagged 'aircraft' too)
            if self.show_labels.get():
                label = callsign or reg or hexid
                lab_txt = f"{label}\n{int(dkm)} km {altitude or '?'} ft"
                self.canvas.create_text(x + 22, y + 22, text=lab_txt, anchor="nw", fill="#e6ffff", font=(None,8), tags=("aircraft",))

        # cleanup trails for aircraft no longer seen
        to_delete = [h for h in self.aircraft_trails.keys() if h not in seen_hexes]
        for h in to_delete:
            del self.aircraft_trails[h]

        # schedule next
        self.schedule_update()

    def on_canvas_click(self, event):
        # find overlapping items near click
        radius = 8
        items = self.canvas.find_overlapping(event.x - radius, event.y - radius, event.x + radius, event.y + radius)
        # items returned are in stacking order (lowest first). We prefer the topmost match that is in aircraft_items
        for it in reversed(items):
            if it in self.aircraft_items:
                self.show_aircraft_popup(self.aircraft_items[it])
                return
        # fallback: try find closest (if any aircraft exists)
        if items:
            # check closest item
            closest = self.canvas.find_closest(event.x, event.y)
            if closest and closest[0] in self.aircraft_items:
                self.show_aircraft_popup(self.aircraft_items[closest[0]])

    def show_aircraft_popup(self, ac):
        win = tk.Toplevel(self.root)
        title = ac.get("callsign") or ac.get("hex") or "Aircraft"
        win.title(f"Aircraft — {title}")
        win.geometry("360x260")
        frm = ttk.Frame(win, padding=8)
        frm.pack(fill="both", expand=True)

        # Build a read-only multi-line description
        txt = tk.Text(frm, width=44, height=10, wrap="word")
        txt.pack(fill="both", expand=True)
        # insert fields in a helpful order
        lines = []
        lines.append(f"Hex: {ac.get('hex')}")
        if ac.get("callsign"):
            lines.append(f"Callsign: {ac.get('callsign')}")
        if ac.get("registration"):
            lines.append(f"Registration: {ac.get('registration')}")
        lines.append(f"Latitude: {ac.get('lat'):.6f}")
        lines.append(f"Longitude: {ac.get('lon'):.6f}")
        lines.append(f"Altitude: {ac.get('altitude_ft') or '?'} ft")
        lines.append(f"Distance: {ac.get('distance_km')} km")
        lines.append(f"Bearing: {ac.get('bearing_deg')}°")
        if ac.get("track_deg") is not None:
            lines.append(f"Track: {ac.get('track_deg')}°")
        if ac.get("speed") is not None:
            lines.append(f"Speed: {ac.get('speed')} (source units)")
        lines.append(f"Last seen: {ac.get('last_seen')}")
        txt.insert("1.0", "\n".join(lines))
        txt.configure(state="disabled")

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill="x", pady=(6,0))
        ttk.Button(btn_frame, text="Close", command=win.destroy).pack(side="right")

    def stop(self):
        self.running = False
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None


if __name__ == "__main__":
    root = tk.Tk()
    app = ADSBRadarApp(root)

    def on_close():
        app.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
