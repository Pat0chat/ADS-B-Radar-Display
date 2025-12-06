#!/usr/bin/env python3


from collections import deque
import time

class Aircrafts:
    """Represents collection of aircrafts"""

    def __init__(self):
        self.seen_hexes = set()
        self.aircrafts = {}
        self.canvas_ids = {}

    def update_aircrafts(self, data, max_trails):
        for ac in data:
            if not (ac.get("lat") and ac.get("lon")):
                continue

            hexid = ac.get("hex") or ac.get("icao24") or ac.get("flight") or str(ac.get("id", ""))
            self.seen_hexes.add(hexid)

            if hexid in self.aircrafts:
                self.aircrafts[hexid].update_from_raw(ac)
            else:
                aircraft = Aircraft(hexid, ac, max_trails)
                self.aircrafts[hexid] = aircraft
    
    def clean_data(self, max_range):
        for hexid in self.aircrafts.keys():
            if hexid not in self.seen_hexes:
                del self.aircrafts[hexid]

                if hexid in self.canvas_ids:
                    del self.canvas_ids[hexid]
            
            if self.aircrafts[hexid].distance_km > max_range:
                del self.aircrafts[hexid]
    
    def get_aircrafts(self):
        return self.aircrafts.copy()
    
    def get_aircraft(self, hex):
        return self.aircrafts[hex]
    
    def get_canvas_ids(self):
        return self.canvas_ids.copy()
    
    def set_canvas_id(self, hex, canvas_id):
        self.canvas_ids[hex] = canvas_id
    
    def clear_trails(self):
        for hexid in self.aircrafts.keys():
            self.aircrafts[hexid].trail.clear()

class Aircraft:
    """Represents one aircraft and its history/trail"""

    def __init__(self, hexid, raw, max_trails):
        self.hex = hexid
        self.callsign = raw.get("flight") or raw.get("callsign") or ""
        self.registration = raw.get("reg") or raw.get("registration") or ""
        self.category = (raw.get("category") or "").upper()

        self.update_from_raw(raw)

        # Renderer-filled values
        self.distance_km = 0
        self.bearing_deg = 0

        # Trail (renderer draws it)
        self.trail = deque(maxlen=max_trails)

    def update_from_raw(self, raw):
        self.lat = raw.get("lat")
        self.lon = raw.get("lon")
        self.altitude = raw.get("altitude") or raw.get("alt_baro") or raw.get("alt_geom") or raw.get("alt")
        self.speed = raw.get("speed") or raw.get("groundspeed") or raw.get("gs") or raw.get("spd") or 0
        self.track = raw.get("track") or raw.get("heading") or 0
        self.vert_rate = raw.get("vert_rate") or 0
        self.last_seen = time.strftime("%H:%M:%S", time.localtime())
    
    def update_compute_data(self, bearing, distance):
        self.bearing_deg = bearing
        self.distance_km = distance
    
    def update_trail(self, x, y):
        self.trail.append((x, y, self.altitude))