#!/usr/bin/env python3

import time
import math
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from datasource import Dump1090Source, OSMSource
from aircraft import Aircrafts

# ------------------- Utilities -------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Return haversine distance in kilometers between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Return bearing in degrees from (lat1,lon1) -> (lat2,lon2)."""
    dlon = math.radians(lon2 - lon1)
    lat1r = math.radians(lat1)
    lat2r = math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2r)
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * \
        math.cos(lat2r) * math.cos(dlon)
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360.0) % 360.0


def altitude_to_color(alt):
    """Map altitude (feet) to RGB hex color string.

    Low alt -> green; medium -> yellow; high -> red; unknown -> gray.
    """
    if alt is None:
        return "#888888"

    # Clamp to ground
    if alt < 0:
        alt = 0

    # Normalize 0..40000 ft → 0..1
    t = min(max(alt / 40000.0, 0.0), 1.0)
    
    if t < 0.5:
        r = int(255 * (t * 2))
        g = 255
        b = 0
    else:
        r = 255
        g = int(255 * (1 - (t - 0.5) * 2))
        b = 0
    return f"#{r:02x}{g:02x}{b:02x}"


def speed_to_color(speed):
    """Map speed (knots) to a distinct color palette.

    Slow -> Blue, moderate -> Cyan, fast -> Green, very fast -> Orange,
    extremely fast -> Red. Unknown -> bluish gray.
    """
    if speed is None:
        return "#8888ff"

    # Clamp speed to reasonable range
    if speed < 0:
        speed = 0
    if speed > 600:
        speed = 600

    # Normalize 0–600 kt → 0.0–1.0
    t = speed / 600.0

    if t < 0.25:
        f = t / 0.25
        r = 0
        g = int(255 * f)
        b = 255

    elif t < 0.50:
        f = (t - 0.25) / 0.25
        r = 0
        g = 255
        b = int(255 * (1 - f))

    elif t < 0.75:
        f = (t - 0.50) / 0.25
        r = int(255 * f)
        g = int(255 - (90 * f))   # 255 → 165
        b = 0

    else:
        f = (t - 0.75) / 0.25
        r = 255
        g = int(165 * (1 - f))
        b = 0

    return f"#{r:02x}{g:02x}{b:02x}"


# ------------------- ADSBRadarApp -------------------
class ADSBRadarApp:
    """Main application class for the ADS-B radar display.

    This class handles UI creation, periodic updates, rendering and
    interactions with the datasource and aircraft collection.
    """

    def __init__(self, root, DATA_URL, RADAR_LAT, RADAR_LON, MAX_RANGE_KM, CANVAS_SIZE, TRAIL_MAX):
        self.root = root
        root.title("ADS-B Radar")

        # --- UI state variables ---
        self.center_lat = tk.DoubleVar(value=RADAR_LAT)
        self.center_lon = tk.DoubleVar(value=RADAR_LON)
        self.max_range = tk.DoubleVar(value=MAX_RANGE_KM)
        self.trail_length = tk.IntVar(value=TRAIL_MAX)
        self.paused = tk.BooleanVar(value=False)
        self.show_labels = tk.BooleanVar(value=True)
        self.timeline_minutes = tk.IntVar(value=5)
        self.refresh_time = tk.IntVar(value=1000)
        self.show_osm = tk.BooleanVar(value=False)

        # --- Main radar canvas ---
        self.canvas = tk.Canvas(root, width=CANVAS_SIZE,
                                height=CANVAS_SIZE, bg="#02121a")
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        # Internal cached canvas size
        self.canvas_width = CANVAS_SIZE
        self.canvas_height = CANVAS_SIZE
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Make the radar canvas expand when the window is resized
        self.root.grid_rowconfigure(0, weight=1)   # radar row expands
        self.root.grid_rowconfigure(1, weight=0)   # timeline row stays fixed
        self.root.grid_columnconfigure(0, weight=1)  # main canvas expands
        self.root.grid_columnconfigure(1, weight=0)  # controls do not expand

        # Fullscreen keyboard shortcuts
        root.bind("<F11>", lambda e: root.attributes("-fullscreen", True))
        root.bind("<Escape>", lambda e: root.attributes("-fullscreen", False))

        # --- Side controls ---
        self.controls = ttk.Frame(root, padding=(6, 6))
        self.controls.grid(row=0, column=1, sticky="ns")

        ttk.Button(self.controls, text="Show data table",
                   command=self.show_raw_table).pack(fill="x", pady=(6, 0))

        ttk.Label(self.controls, text="Center Latitude:").pack(anchor="w", pady=(6, 0))
        ttk.Entry(self.controls, textvariable=self.center_lat).pack(fill="x")
        ttk.Label(self.controls, text="Center Longitude:").pack(anchor="w", pady=(6, 0))
        ttk.Entry(self.controls, textvariable=self.center_lon).pack(fill="x")

        # Range (km) Spinbox
        ttk.Label(self.controls, text="Range (km):").pack(anchor="w", pady=(6, 0))
        ttk.Spinbox(
            self.controls,
            from_=10, to=500,
            increment=1,
            textvariable=self.max_range,
            width=10,
            command=lambda: self.refresh_now()
        ).pack(fill="x")

        # Trail length Spinbox
        ttk.Label(self.controls, text="Trail length:").pack(anchor="w", pady=(6, 0))
        ttk.Spinbox(
            self.controls,
            from_=0, to=200,
            increment=1,
            textvariable=self.trail_length,
            width=10
        ).pack(fill="x")

        # Timeline (minutes) Spinbox
        ttk.Label(self.controls, text="Timeline (minutes):").pack(anchor="w", pady=(6, 0))
        ttk.Spinbox(
            self.controls,
            from_=1, to=30,
            increment=1,
            textvariable=self.timeline_minutes,
            width=10,
            command=self.update_timeline_max
        ).pack(fill="x")

        # Refresh rate (ms) Spinbox
        ttk.Label(self.controls, text="Refresh rate (ms):").pack(anchor="w", pady=(6, 0))
        ttk.Spinbox(
            self.controls,
            from_=50, to=2000,
            increment=50,
            textvariable=self.refresh_time,
            width=10,
            command=lambda: self.source_dump.update_refresh(self.refresh_time.get())
        ).pack(fill="x")

        ttk.Checkbutton(self.controls, text="Show labels", variable=self.show_labels).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(self.controls, text="Pause updates", variable=self.paused).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(self.controls, text="Show OSM background", variable=self.show_osm, command=self.refresh_now).pack(anchor="w", pady=(6, 0))

        ttk.Button(self.controls, text="Refresh view",
                   command=self.refresh_now).pack(anchor="w", fill="x", pady=(6, 0))
        ttk.Button(self.controls, text='Clear Trails',
                   command=self.clear_trails).pack(anchor="w", fill='x', pady=(6, 0))

        ttk.Label(self.controls, text="Altitude Legend:").pack(
            anchor="w", pady=(6, 0))

        alt_legend = tk.Canvas(self.controls, width=140, height=30,
                               bg="#ffffff", highlightthickness=1, highlightbackground="#000")
        alt_legend.pack(pady=(2, 6))

        # Draw horizontal gradient (0 ft → 40,000 ft)
        for x in range(140):
            alt = (x / 139) * 40000
            c = altitude_to_color(alt)
            alt_legend.create_line(x, 0, x, 30, fill=c)

        alt_legend.create_text(5, 15, anchor="w", text="0 ft", font=(None, 8))
        alt_legend.create_text(135, 15, anchor="e",
                               text="40,000 ft", font=(None, 8))

        ttk.Label(self.controls, text="Speed Legend:").pack(anchor="w", pady=(6, 0))
        spd_legend = tk.Canvas(self.controls, width=140, height=30,
                               bg="#ffffff", highlightthickness=1, highlightbackground="#000")
        spd_legend.pack(pady=(2, 6))

        # Draw horizontal gradient (0 kt → 600 kt)
        for x in range(140):
            spd = (x / 139) * 600
            c = speed_to_color(spd)
            spd_legend.create_line(x, 0, x, 30, fill=c)

        spd_legend.create_text(5, 15, anchor="w", text="0 kt", font=(None, 8))
        spd_legend.create_text(135, 15, anchor="e",
                               text="600 kt", font=(None, 8))

        ttk.Label(self.controls, text="Dump1090 Status:").pack(
            anchor="w", pady=(6, 0))
        self.status_label = ttk.Label(
            self.controls, text="Unknown", foreground="orange")
        self.status_label.pack(anchor="w")
        self.dump1090_alive = False

        ttk.Label(self.controls, text="Last update:").pack(anchor="w", pady=(6, 0))
        self.status_freshness = ttk.Label(
            self.controls, text="N/A", foreground="orange")
        self.status_freshness.pack(anchor="w")

        # ---- Timeline ----
        self.timeline_height = 40
        self.timeline_canvas = tk.Canvas(root, height=self.timeline_height,
                                         bg="#11181c", highlightthickness=0)
        self.timeline_canvas.grid(row=1, column=0, columnspan=2, sticky="ew")

        self.count_history = []     # [(timestamp, count), ...]
        self.max_history = 300      # keep last 300 samples (~5 min)
        self.last_timeline_update = 0
        self.timeline_refresh_sec = 5   # refresh every 5 seconds

        # --- Aircraft collection ---
        self.aircraft_items = Aircrafts()

        # --- Data source ---
        self.source_dump = Dump1090Source(DATA_URL, self.refresh_time.get())
        self.source_dump.start()

        self.source_osm = OSMSource()

        # --- UI ---
        #Toggle button
        self.create_toogle_button()

        # Draw static radar background once
        self.draw_background()
        self.running = True
        self.controls_visible = True

        # Start GUI update loop
        self.schedule_update()

    # ------------------- GUI helpers -------------------
    def create_toogle_button(self):
        # Toggle control button
        bx, by = 30, 30
        radius = 18

        self.hud_circle = self.canvas.create_oval(
            bx - radius, by - radius,
            bx + radius, by + radius,
            fill="#02121a",
            outline="#2b6d6b",
            width=2,
            tags=("hud_btn",)
        )

        self.hud_icon = self.canvas.create_text(
            bx, by - 2,
            text="≡",
            fill="#9be3dc",
            font=("Segoe UI", 14, "bold"),
            tags=("hud_btn",)
        )

        def click_hud_button(event):
            self.toggle_controls()

        self.canvas.tag_bind("hud_btn", "<Button-1>", click_hud_button)

    def toggle_controls(self):
        if self.controls_visible:
            # Hide it
            self.controls.grid_remove()
            self.controls_visible = False
        else:
            # Show it
            self.controls.grid()
            self.controls_visible = True

    def on_canvas_resize(self, event):
        """Handle canvas resize events (debounced redraw)."""
        # update current canvas size
        self.canvas_width = event.width
        self.canvas_height = event.height

        # redraw radar background when canvas changes
        self.draw_background()

    def schedule_update(self):
        """Schedule periodic UI updates using tkinter.after()."""
        if not self.running:
            return
        self.update_frame()
        self.source_dump.update_refresh(self.refresh_time.get())
        self.root.after(self.refresh_time.get(), self.schedule_update)

    def show_raw_table(self):
        """Open a separate window showing raw dump1090 table data."""
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

        def refresh():
            """Refresh the contents of the data table periodically."""
            if not win.winfo_exists():
                return

            # Clear old rows
            for row in tree.get_children():
                tree.delete(row)

            # Insert new rows from dump1090
            data = self.source_dump.snapshot()

            for ac in data:
                row = (
                    ac.get("hex") or ac.get("icao24") or "",
                    ac.get("flight") or ac.get("callsign") or "",
                    ac.get("registration") or ac.get("reg") or "",
                    ac.get("lat") or "",
                    ac.get("lon") or "",
                    ac.get("altitude") or ac.get(
                        "alt_baro") or ac.get("alt_geom") or "",
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
        """Force a redraw of background and frame update."""
        self.draw_background()
        self.update_frame()

    def clear_trails(self):
        """Erase all stored trails and canvas trail objects."""
        self.aircraft_items.clear_trails()
        self.canvas.delete('trails')

    def km_to_pixels(self, km):
        """Convert distance in kilometers to canvas pixels given max range."""
        margin = 10   # space between heading rose and border
        radius_px = min(self.canvas_width, self.canvas_height) / 2.0 - margin
        if self.max_range.get() > 0:
            effective_range = self.max_range.get()
            px_per_km = radius_px / effective_range
            return km * px_per_km
        else:
            return km * radius_px

    def geo_to_canvas(self, lat, lon):
        """Transform geographic coordinates to canvas x,y and compute bearing/distance."""
        dkm = haversine_km(self.center_lat.get(),
                           self.center_lon.get(), lat, lon)
        brg = bearing_deg(self.center_lat.get(),
                          self.center_lon.get(), lat, lon)

        # polar to cartesian: we use angle where 0=North, 90=East
        angle_rad = math.radians(brg)

        # Convert km to px only using km_to_pixels()
        dist_px = self.km_to_pixels(dkm)

        x = self.canvas_width/2 + dist_px * math.sin(angle_rad)
        y = self.canvas_height/2 - dist_px * math.cos(angle_rad)

        return x, y, dkm, brg

    # ------------------- Radar rendering -------------------
    def draw_osm_background(self):
        """Download and draw an OSM tile grid as the radar background."""
        self.canvas.delete("osmbg")

        zoom = 12   # fixed zoom; later we can make this user-adjustable
        lat = self.center_lat.get()
        lon = self.center_lon.get()

        cw, ch = self.canvas_width, self.canvas_height

        # Determine how many tiles we need to cover the canvas
        tiles_x = int(cw / 256) + 2
        tiles_y = int(ch / 256) + 2

        center_xt, center_yt = self.source_osm.latlon_to_tile(lat, lon, zoom)

        # start tile indices
        start_x = center_xt - tiles_x // 2
        start_y = center_yt - tiles_y // 2

        stitched = Image.new("RGB", (tiles_x * 256, tiles_y * 256))

        for ix in range(tiles_x):
            for iy in range(tiles_y):
                tx = start_x + ix
                ty = start_y + iy

                tile = self.source_osm.fetch_osm_tile(zoom, tx, ty)
                if tile:
                    stitched.paste(tile, (ix * 256, iy * 256))

        # resize to canvas
        stitched = stitched.resize((cw, ch), Image.Resampling.LANCZOS)
        self.osm_tk = ImageTk.PhotoImage(stitched)
        self.canvas.create_image(0, 0, anchor="nw", image=self.osm_tk, tags="osmbg")

    def draw_background(self):
        """Draw either radar background or OSM map + rings overlay."""
        self.canvas.delete("bg")
        self.canvas.delete("osmbg")
        self.canvas.delete("hud_btn")

        # Draw OSM map if enabled
        if self.show_osm.get():
            self.draw_osm_background()

        cx = self.canvas_width // 2
        cy = self.canvas_height // 2

        margin = 10   # space between heading rose and border
        radius_px = min(self.canvas_width, self.canvas_height) / 2.0 - margin

        # Range rings and labels
        for i in range(1, 5):
            r = radius_px * (i / 4)
            self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                outline="#2b6d6b", dash=(3, 6),
                tags=("bg",)
            )

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

        # Center marker
        self.canvas.create_oval(
            cx - 4, cy - 4, cx + 4, cy + 4,
            outline="#00ffaa",
            width=2,
            tags=("bg",)
        )

        # Heading rose
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

            self.canvas.create_line(x0, y0, x1, y1,
                                    fill="#3dd6c6" if deg % 30 == 0 else "#1a9494",
                                    width=2 if deg % 30 == 0 else 1, tags=("bg",),
                                    smooth=True, splinesteps=24
                                    )

            # Cardinal letters (N/E/S/W)
            if deg in (0, 90, 180, 270):
                lx = cx + (radius_px * 0.90) * sin_a
                ly = cy - (radius_px * 0.90) * cos_a
                letter = {0: "N", 90: "E", 180: "S", 270: "W"}[deg]

                self.canvas.create_text(
                    lx, ly,
                    text=letter,
                    fill="#9be3dc",
                    font=(None, 14, "bold"),
                    tags=("bg",)
                )
        
        # Toggle button
        self.create_toogle_button()

    def update_frame(self):
        """Update aircraft data and redraw dynamic canvas items."""
        # Connection status
        if self.source_dump.alive:
            self.status_label.configure(text="Connected", foreground="green")
        else:
            self.status_label.configure(text="No response", foreground="red")

        # Last updated
        if self.source_dump.alive:
            self.status_freshness.configure(
                text=self.source_dump.last_seen(), foreground="green")
        else:
            self.status_freshness.configure(text="No data", foreground="red")

        # Pause
        if self.paused.get():
            return

        # Clear view
        self.canvas.delete("aircraft")
        self.canvas.delete("trails")

        # Get data and update aircrafts
        data = self.source_dump.snapshot()
        self.aircraft_items.update_aircrafts(data, self.trail_length.get())
        self.aircraft_items.clean_data()

        # Process aircrafts
        aircrafts = self.aircraft_items.get_aircrafts()
        for hexid in aircrafts:
            aircraft = aircrafts[hexid]
            x, y, dkm, brg = self.geo_to_canvas(aircraft.lat, aircraft.lon)

            aircraft.update_compute_data(brg, dkm)
            aircraft.update_trail(x, y)

            # Draw trail
            trail = aircraft.trail
            n = len(trail)
            if n > 1 and self.trail_length.get() > 0:
                for idx in range(1, n):
                    ax, ay, alt1 = trail[idx-1]
                    bx, by, alt2 = trail[idx]
                    seg_age = idx/max(1, n)
                    width = max(1, int(3*(1-seg_age)))

                    # Interpolate color between start and end of segment
                    col1 = altitude_to_color(alt1)
                    col2 = altitude_to_color(alt2)
                    r = int(int(col1[1:3], 16)*(1-seg_age) +
                            int(col2[1:3], 16)*seg_age)
                    g = int(int(col1[3:5], 16)*(1-seg_age) +
                            int(col2[3:5], 16)*seg_age)
                    b = int(int(col1[5:7], 16)*(1-seg_age) +
                            int(col2[5:7], 16)*seg_age)
                    fade_color = f"#{r:02x}{g:02x}{b:02x}"
                    self.canvas.create_line(ax, ay, bx, by, fill=fade_color,
                                            width=width, smooth=True, splinesteps=24, tags=("trails",))

            # Draw aircraft point
            color_inner = "#ffffff"
            color_outer = "#ffffff"
            if aircraft.category.startswith("A"):     # Fixed-wing
                color_outer = "#ffc400"
            elif aircraft.category.startswith("B"):   # Rotorcraft
                color_outer = "#e5ff00"
            else:                                     # Unknown
                color_outer = "#d3d3d3"    
            canvas_id = self.canvas.create_oval(
                x - 4, y - 4, x + 4, y + 4,
                outline=color_outer,
                width=2,
                tags=("aircraft",)
            )
            self.canvas.create_oval(
                x - 1, y - 1, x + 1, y + 1,
                fill=color_inner,
                outline="",
                tags=("aircraft",)
            )

            self.aircraft_items.set_canvas_id(hexid, canvas_id)

            # Heading / speed vector
            base_len = 10
            spd = (aircraft.speed or 0)
            
            vector_len = base_len + spd * 0.07 # Speed extends line slightly
            vect_speed_color = speed_to_color(spd)

            angle_rad = math.radians(aircraft.track)

            x2 = x + vector_len * math.sin(angle_rad)
            y2 = y - vector_len * math.cos(angle_rad)

            self.canvas.create_line(x, y, x2, y2, fill=vect_speed_color, width=1,
                                    arrow=tk.LAST, arrowshape=(8, 10, 4), tags=("aircraft",),
                                    smooth=True, splinesteps=24)

            # Attach label (as separate canvas items but tagged 'aircraft' too)
            if self.show_labels.get():
                label = aircraft.callsign or aircraft.registration or aircraft.hex
                lab_txt = f"{label}\n{int(dkm)} km {aircraft.altitude or '?'} ft"
                self.canvas.create_text(
                    x + 10, y + 10, text=lab_txt, anchor="nw", fill="#e6ffff", font=(None, 8), tags=("aircraft",))

        # Update timeline count
        aircrafts_count = self.source_dump.aircrafts_count()
        timestamp = time.time()
        self.count_history.append((timestamp, aircrafts_count))
        if len(self.count_history) > self.max_history:
            self.count_history.pop(0)

        if timestamp - self.last_timeline_update >= self.timeline_refresh_sec:
            self.draw_timeline()
            self.last_timeline_update = timestamp

    # ------------------- Timeline Rendering -------------------
    def update_timeline_max(self):
        """Update max history variable to adapt the timeline size and data."""
        minutes = self.timeline_minutes.get()
        # Assuming your update_frame runs once per second:
        self.max_history = minutes * 60

        # Ensure history doesn’t grow too large
        if len(self.count_history) > self.max_history:
            self.count_history = self.count_history[-self.max_history:]

    def draw_timeline(self):
        """Drawing dynamic timeline item."""
        c = self.timeline_canvas
        c.delete("all")

        if not self.count_history:
            return

        # Canvas size
        w = c.winfo_width()
        h = self.timeline_height

        # Extract counts
        counts = [cnt for (_, cnt) in self.count_history]
        max_count = max(counts) if counts else 1
        max_count = max(max_count, 1)

        n = len(counts)
        if n <= 1:
            return

        # Draw markers
        timestamps = [t for (t, _) in self.count_history]
        t_start = timestamps[0]
        t_end = timestamps[-1]
        
        real_duration_sec = max(t_end - t_start, 1)   # avoid zero
        minutes = real_duration_sec / 60

        desired_markers = 7
        step_min = max(1, round(minutes / desired_markers))

        # Recalc number
        num_markers = max(1, int(minutes // step_min))
        for i in range(num_markers + 1):
            # Compute the timestamp this marker represents
            marker_minutes_ago = i * step_min
            marker_time = t_end - marker_minutes_ago * 60

            if marker_time < t_start:
                continue

            # Position of marker on canvas: normalized time
            ratio = (marker_time - t_start) / real_duration_sec
            x = int(ratio * w)

            # Line
            c.create_line(x, 0, x, h, fill="#333", width=1,
                          smooth=True, splinesteps=24)

            # Label
            if marker_minutes_ago == 0:
                label = "now"
            else:
                label = f"{marker_minutes_ago}m"

            c.create_text(
                x + 2, h - 2,
                text=label,
                anchor="se",
                fill="#888",
                font=("Arial", 8)
            )

        # Draw sparkline
        step_x = w / (n - 1)
        points = []

        for i, v in enumerate(counts):
            x = int(i * step_x)
            y = int(h - (v / max_count) * (h - 5))
            points.append((x, y))

        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            c.create_line(x1, y1, x2, y2, fill="#4ebbc9",
                          width=2, smooth=True, splinesteps=24)

        # Latest value label
        now_count = counts[-1]
        c.create_text(5, 5, anchor="nw",
                      text=f"{now_count} aircrafts",
                      fill="#4ebbc9",
                      font=("Arial", 9, "bold"))

    # ------------------- Aircraft click and popup -------------------
    def on_canvas_click(self, event):
        """Handle clicks on the radar canvas and open aircraft popup if clicked."""
        radius = 8
        items = self.canvas.find_overlapping(event.x-radius, event.y-radius,
                                             event.x+radius, event.y+radius)
        canvas_ids = self.aircraft_items.get_canvas_ids()
        for it in reversed(items):
            for hexid in canvas_ids:
                if it == canvas_ids[hexid]:
                    aircraft = self.aircraft_items.get_aircraft(hexid)
                    self.show_aircraft_popup(aircraft)
                    return

    def show_aircraft_popup(self, ac_initial):
        """Open a popup for an aircraft and keep updating its info."""
        hexid = ac_initial.hex

        win = tk.Toplevel(self.root)
        title = ac_initial.callsign or hexid or "Aircraft"
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
            aircrafts = self.aircraft_items.get_aircrafts()
            for hex in aircrafts:
                if hex == hexid:
                    latest = aircrafts[hex]
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
                f"Hex: {latest.hex}",
                f"Callsign: {latest.callsign}",
                f"Registration: {latest.registration}",
                f"Category: {latest.category}",
                f"Latitude: {latest.lat:.6f}",
                f"Longitude: {latest.lon:.6f}",
                f"Altitude: {latest.altitude} ft",
                f"Distance: {latest.distance_km} km",
                f"Bearing: {latest.bearing_deg}°",
                f"Track: {latest.track}°",
                f"Speed: {latest.speed} kts",
                f"Vertical speed: {latest.vert_rate} fpm",
                f"Last seen: {latest.last_seen}",
            ]

            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", "\n".join([l for l in lines if l]))
            txt.configure(state="disabled")

            # Schedule next refresh
            win.after(1000, refresh_popup)

        # Start updating loop
        refresh_popup()

    # ------------------- Stop -------------------
    def stop(self):
        """Stop the app main loop and any background operations."""
        self.running = False
