#!/usr/bin/env python3

import random
import math
import string
import time

# ------------------- Variables -------------------
EARTH_R = 6371.0


# ------------------- Utilities -------------------
def destination_point(lat_deg, lon_deg, bearing_deg, distance_km):
    """Generate destination point."""
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
    """Convert kts to km/s."""
    return kts * 1.852 / 3600.0

def gen_category():
    """Generate category."""
    return random.choice([
        "A",   # fixed-wing
        "B",   # rotorcraft
        "C",   # gliders/balloons
        "D"   # UAV / special
    ])

def gen_hex():
    """Generate hexid."""
    return "".join(random.choice("0123456789abcdef") for _ in range(6))

def gen_callsign():
    """Generate callsign."""
    return random.choice(["DLH", "KLM", "AFR", "EZY", "RYR", "UAE", "AAL", "SAS"]) + str(random.randint(1, 9999))

def gen_reg():
    """Generate registration."""
    return "".join(random.choice(string.ascii_uppercase) for _ in range(5))


# ------------------- Aircraft -------------------
class Aircraft:
    """Represent one aircraft in the simulation."""

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
        """Update aircraft parameters (simulation step)."""

        km_s = km_from_knots(self.speed)
        dist = km_s * dt
        self.lat, self.lon = destination_point(
            self.lat, self.lon, self.track, dist)

        self.track = (self.track + self.turn_rate * dt) % 360

        self.altitude += (self.vspeed / 60) * dt
        self.altitude = max(0, min(45000, self.altitude))

        if time.time() - self._last_behavior > random.uniform(10, 25):
            self.turn_rate = random.uniform(-4, 4)
            self.speed = max(
                150, min(500, self.speed + random.uniform(-40, 40)))
            # Smooth vertical rate change
            delta_vs = random.uniform(-600, 600)
            self.vspeed = max(-2500, min(2500, self.vspeed + delta_vs))
            self._last_behavior = time.time()

    def to_json(self):
        """Create json message from aircraft parameters"""
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
            "seen": int(time.time() - self._last_behavior),
        }
