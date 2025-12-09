#!/usr/bin/env python3

import time
from collections import deque
from pyproj import Geod
geod = Geod(ellps="WGS84")

# ------------------- Aircrafts -------------------
class Aircrafts:
    """Represent collection of aircrafts"""

    def __init__(self):
        self.aircrafts = {}
        self.canvas_ids = {}
        self.aircraft_canvas_items = {}
        self.aircraft_trails = {}
        self.prediction_lines = {}
    
    def create_canvas_item(self, canvas, hexid, x, y):
        items = {}

        # Outer dot
        id = items["outer"] = canvas.create_oval(
            x-3, y-3, x+3, y+3,
            outline="#ffffff",
            width=2,
            tags=("aircraft",)
        )

        # Inner dot
        items["inner"] = canvas.create_oval(
            x-1, y-1, x+1, y+1,
            fill="#ffffff",
            outline="",
            tags=("aircraft",)
        )

        # Speed vector
        items["vector"] = canvas.create_line(
            x, y, x, y,
            fill="#00ffff",
            width=1,
            tags=("aircraft",),
            smooth=True,
            splinesteps=16
        )

        # Label
        items["label"] = canvas.create_text(
            x+10, y+10,
            text="",
            anchor="nw",
            fill="#e6ffff",
            font=("Consolas", 8),
            tags=("aircraft",)
        )

        self.aircraft_canvas_items[hexid] = items
        self.canvas_ids[hexid] = id

    def update_aircrafts(self, data, max_trails):
        """Update planes from received data."""
        for ac in data:
            if not (ac.get("lat") and ac.get("lon")):
                continue

            hexid = ac.get("hex") or ac.get("icao24") or ac.get("flight") or str(ac.get("id", ""))

            if hexid in self.aircrafts:
                self.aircrafts[hexid].update_from_raw(ac)
            else:
                aircraft = Aircraft(hexid, ac, max_trails)
                self.aircrafts[hexid] = aircraft
    
    def clean_data(self, canvas, max_range):
        """Remove aircraft too old, invalid, or stale."""
        current_hex = list(self.aircrafts.keys())
        existing_hex = list(self.aircraft_canvas_items.keys())

        to_delete = []

        for hexid in existing_hex:
            if hexid not in current_hex:
                to_delete.append(hexid)

        for hexid in current_hex:
            ac = self.aircrafts[hexid]

            # Remove aircraft missing coordinates
            if ac.lat is None or ac.lon is None:
                to_delete.append(hexid)
                continue

            # Remove airplane with no behavior for a long time
            if time.time() - ac.last_behavior > 60:
                to_delete.append(hexid)
                continue

            # Remove airplane outside radar range
            if ac.distance_km > max_range:
                to_delete.append(hexid)
                continue

            # Remove stale / not seen for a long time
            if isinstance(ac.last_seen, (int, float)):
                if ac.last_seen > 60:
                    to_delete.append(hexid)
                    continue

        for hexid in to_delete:
            # Delete aircraft canvas items
            items = self.aircraft_canvas_items.pop(hexid, None)
            if items:
                for item in items.values():
                    try:
                        canvas.delete(item)
                    except:
                        pass

            # Delete trail polyline if exists
            trail_id = self.aircraft_trails.pop(hexid, None)
            if trail_id is not None:
                canvas.delete(trail_id)

            # Delete prediction path if exists
            if hexid in self.prediction_lines:
                canvas.delete(self.prediction_lines[hexid])
                del self.prediction_lines[hexid]

            del self.aircrafts[hexid]

    
    def get_aircrafts(self):
        """Get all aircrafts."""
        return self.aircrafts
    
    def get_aircraft(self, hex):
        """Get aircraft from it's hexid parameter."""
        return self.aircrafts[hex]
    
    def get_canvas_ids(self):
        """Get all canvas ids created in UI."""
        return self.canvas_ids
    
    def clear_trails(self):
        """Clear all trails."""
        for hexid in self.aircrafts.keys():
            self.aircrafts[hexid].trail.clear()


# ------------------- Aircraft -------------------
class Aircraft:
    """Represent one aircraft and its history/trail"""

    def __init__(self, hexid, raw, max_trails):
        self.hex = hexid
        self.callsign = raw.get("flight") or raw.get("callsign") or ""
        self.registration = raw.get("reg") or raw.get("registration") or ""
        self.category = (raw.get("category") or "").upper()

        self.update_from_raw(raw)

        self.distance_km = 0
        self.bearing_deg = 0

        self.trail = deque(maxlen=max_trails)

    def update_from_raw(self, raw):
        """Update airplane data."""
        self.lat = raw.get("lat")
        self.lon = raw.get("lon")
        self.altitude = raw.get("altitude") or raw.get("alt_baro") or raw.get("alt_geom") or raw.get("alt")
        self.speed = raw.get("speed") or raw.get("groundspeed") or raw.get("gs") or raw.get("spd") or 0
        self.track = raw.get("track") or raw.get("heading") or 0
        self.vert_rate = raw.get("vert_rate") or 0
        self.last_seen = raw.get("seen") or raw.get("seen_pos") or 0
        self.last_behavior = time.time()
    
    def update_compute_data(self, bearing, distance):
        """Update computed data."""
        self.bearing_deg = bearing
        self.distance_km = distance
    
    def update_trail(self, x, y):
        """Update plane's trail."""
        self.trail.append((x, y, self.altitude))
    
    def predict_position(self, lat, lon, heading_deg, speed_kt, minutes_ahead):
        """Predict position of the plane x minutes ahead."""
        distance_km = speed_kt * 1.852 * (minutes_ahead / 60.0)
        lon2, lat2, _ = geod.fwd(lon, lat, heading_deg, distance_km * 1000)
        return lat2, lon2