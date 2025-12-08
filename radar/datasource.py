#!/usr/bin/env python3

import io
import math
import threading
import time
import requests
import urllib.request
from PIL import Image

# ------------------- Dump1090Source -------------------
class Dump1090Source:
    """Dump1090Source class fetching data from dump1090 API.

    This class handles datasource creation from URL API, periodic updates through separate thread,
    data snapshot, and status indicators.
    """

    def __init__(self, url, refresh):
        self.url = url
        self.running = False
        self.alive = False
        self.last_seen_time = time.strftime("%H:%M:%S", time.localtime())
        self.latest_data = []
        self.refresh = round(refresh / 1000)
        self.lock = threading.Lock()

    def start(self):
        """Start the thread fetching data from dump1090 API."""
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        """Stop the thread fetching data from dump1090 API."""
        self.running = False

    def update_refresh(self, refresh):
        """Update refresh rate of fetching data from dump1090 API."""
        self.refresh = round(refresh / 1000, 2)

    def last_seen(self):
        """Get data last fetching time."""
        return self.last_seen_time
    
    def aircrafts_count(self):
        """Get number of planes received from dump1090 API."""
        aircrafts_count = 0

        if self.latest_data:
            aircrafts_count = len(self.latest_data)

        return aircrafts_count

    def _loop(self):
        """Thread loop fetching data from dump1090 API."""
        while self.running:
            try:
                r = requests.get(self.url, timeout=1.0)
                data = r.json()
                self.alive = True if data else False
                self._process(data)
            except:
                self.alive = False
                pass
            time.sleep(self.refresh)

    def _process(self, raw_list):
        """Store last received data from dump1090 API."""
        self.last_seen_time = time.strftime("%H:%M:%S", time.localtime())
        with self.lock:
            self.latest_data = raw_list

    def snapshot(self):
        """Get last stored data."""
        with self.lock:
            return self.latest_data.copy()


# ------------------- OSMSource -------------------
class OSMSource:
    """OSMSource class fetching data from OSM API."""

    def __init__(self):
        pass

    def fetch_osm_tile(self, z, x, y):
        """Download a single OSM tile. Return PIL image or None."""
        try:
            url = f"https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
            with urllib.request.urlopen(url, timeout=2) as resp:
                data = resp.read()
            return Image.open(io.BytesIO(data))
        except Exception:
            return None
        
    def compute_osm_zoom(self, lat, max_range, width):
        """
        Dynamically compute OSM tile zoom level so the displayed map
        roughly matches the radar max range (km).
        """

        width_px = max(width, 1)

        # Target meters per pixel (map covers full diameter of radar)
        target_mpp = (max_range * 2 * 1000) / width_px

        # OSM base formula
        cos_lat = math.cos(math.radians(lat))
        if cos_lat < 0.01:
            cos_lat = 0.01  # avoid poles

        zoom = math.log2((156543.03392 * cos_lat) / target_mpp)

        # Clamp to OSM valid zoom
        return max(0, min(zoom, 18))