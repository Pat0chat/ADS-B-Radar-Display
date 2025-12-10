#!/usr/bin/env python3

import math

# ------------------- Utils -------------------
class Utils:
    """Utils functions."""
    def __init__(self):
        self.zoom = 0
        self.zoom_pixels = 0
        pass


    def haversine_km(self, lat1, lon1, lat2, lon2):
        """Return haversine distance in kilometers between two lat/lon points."""
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
        return 2 * R * math.asin(math.sqrt(a))


    def bearing_deg(self, lat1, lon1, lat2, lon2):
        """Return bearing in degrees from (lat1,lon1) -> (lat2,lon2)."""
        dlon = math.radians(lon2 - lon1)
        lat1r = math.radians(lat1)
        lat2r = math.radians(lat2)
        x = math.sin(dlon) * math.cos(lat2r)
        y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * \
            math.cos(lat2r) * math.cos(dlon)
        brng = math.degrees(math.atan2(x, y))
        return (brng + 360.0) % 360.0


    def compute_zoom(self, lat, max_range, width):
        """Dynamically compute tile zoom level so the displayed map
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
        zoom = (int(zoom))
        zoom = max(6, min(zoom, 18)) # Clamp to OSM valid zoom
        
        self.zoom = zoom
        self.zoom_pixels = 256 * (2 ** self.zoom)
        return self.zoom

    def project(self, lat, lon):
        """Convert lat/lon to Web Mercator tile coordinates."""

        # Global pixel X
        px_center = (lon + 180.0) / 360.0 * self.zoom_pixels

        # Global pixel Y
        lat_rad = math.radians(lat)
        n = math.pi - math.log(math.tan(math.pi/4 + lat_rad/2))
        py_center = (n / math.pi) * (self.zoom_pixels / 2)

        return px_center, py_center

    def km_to_pixels(self, canvas_width, canvas_height, max_range, km):
        """Convert distance in kilometers to canvas pixels given max range."""
        margin = 10   # space between heading rose and border
        radius_px = min(canvas_width, canvas_height) / 2.0 - margin
        if max_range > 0:
            effective_range = max_range
            px_per_km = radius_px / effective_range
            return km * px_per_km
        else:
            return km * radius_px

    def geo_to_canvas(self, center_lat, center_lon, lat, lon, canvas_width, canvas_height, max_range):
        """Transform geographic coordinates to canvas x,y and compute bearing/distance."""
        dkm = self.haversine_km(center_lat, center_lon, lat, lon)
        brg = self.bearing_deg(center_lat, center_lon, lat, lon)

        # polar to cartesian: we use angle where 0=North, 90=East
        angle_rad = math.radians(brg)

        # Convert km to px only using km_to_pixels()
        dist_px = self.km_to_pixels(canvas_width, canvas_height, max_range, dkm)

        x = canvas_width/2 + dist_px * math.sin(angle_rad)
        y = canvas_height/2 - dist_px * math.cos(angle_rad)

        return x, y, dkm, brg
