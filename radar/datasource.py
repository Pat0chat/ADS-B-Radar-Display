#!/usr/bin/env python3

import io
import threading
import time
import requests
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

    def __init__(self, proxy):
        self.session = requests.Session()
        self.proxy = proxy
        if self.proxy != "":
            self.session.proxies.update({
                "http":  self.proxy,
                "https": self.proxy
            })
        pass

    def fetch_osm_tile(self, z, x, y):
        """Download a single OSM tile. Return PIL image or None."""
        url = f"https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
        try:
            resp = self.session.get(url, timeout=5)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content))
        except Exception as e:
            print(f"OSM tile error: {e}")
            return None
