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
        zoom = int(zoom)
        #zoom = math.ceil(zoom)
        #zoom = max(6, min(zoom, 18)) # Clamp to OSM valid zoom

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
    
    def closest_point_on_bbox(self, cx, cy, bbox):
        """
        Compute the point on the rectangle bbox (x0, y0, x1, y1)
        that is closest to the point (cx, cy).
        """
        x0, y0, x1, y1 = bbox

        # Clamp point to bbox edges
        px = min(max(cx, x0), x1)
        py = min(max(cy, y0), y1)

        return px, py

    def bbox_overlap(self, a, b):
        """Return True if two bounding boxes overlap."""
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        return not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)

    def generate_spiral_offsets(self, max_radius=90, angle_steps=16, radial_steps=6):
        """
        Returns a list of (dx, dy) offsets ordered from nearest to furthest.
        - angle_steps: how many angles to try per radius
        - radial_steps: how many rings (increase radius each ring)
        """
        offsets = [(10, 10)]  # keep default near position first
        for r_step in range(1, radial_steps + 1):
            radius = (max_radius / radial_steps) * r_step
            for a in range(angle_steps):
                ang = (2 * math.pi * a) / angle_steps
                dx = int(round(radius * math.cos(ang)))
                dy = int(round(radius * math.sin(ang)))
                offsets.append((dx, dy))
        # remove duplicates while preserving order
        seen = set()
        unique = []
        for o in offsets:
            if o not in seen:
                unique.append(o)
                seen.add(o)
        return unique

    def place_label_spiral(self, canvas, lbl_id, x, y, existing_bboxes, max_radius=90):
        """
        Try many candidate positions in a spiral order. Return final bbox if placed.
        """
        offsets = self.generate_spiral_offsets(max_radius=max_radius, angle_steps=16, radial_steps=6)
        for dx, dy in offsets:
            # place the label candidate
            canvas.coords(lbl_id, x + dx, y + dy)
            bbox = canvas.bbox(lbl_id)
            if bbox is None:
                continue
            # check collision
            collision = False
            for eb in existing_bboxes:
                if self.bbox_overlap(bbox, eb):
                    collision = True
                    break
            if not collision:
                return bbox
        # fallback: return last bbox (may overlap)
        return canvas.bbox(lbl_id)

    def relax_label_positions(self, canvas, label_info, placed_bboxes_map, iterations=6, move_limit=12):
        """
        label_info: list of dicts { 'hex': hexid, 'lbl': canvas_label_id, 'pos': [x, y], 'bbox': bbox, 'priority': priority }
        placed_bboxes_map: hexid -> bbox (initial)
        This moves labels on the canvas (via canvas.move) to reduce overlaps.
        """
        # Build a small structure to track centers and bboxes
        state = {}
        for info in label_info:
            hexid = info['hex']
            bbox = placed_bboxes_map.get(hexid) or canvas.bbox(info['lbl'])
            if bbox is None:
                continue
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            state[hexid] = {
                'lbl': info['lbl'],
                'cx': cx,
                'cy': cy,
                'bbox': bbox,
                'priority': info.get('priority', 1.0)
            }

        for _ in range(iterations):
            moved_any = False
            keys = list(state.keys())
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    a_k = keys[i]; b_k = keys[j]
                    a = state[a_k]; b = state[b_k]
                    if self.bbox_overlap(a['bbox'], b['bbox']):
                        # compute minimal push vector to separate along center-to-center
                        ax0, ay0, ax1, ay1 = a['bbox']
                        bx0, by0, bx1, by1 = b['bbox']
                        # overlap distances
                        overlap_x = min(ax1, bx1) - max(ax0, bx0)
                        overlap_y = min(ay1, by1) - max(ay0, by0)
                        if overlap_x <= 0 or overlap_y <= 0:
                            continue  # no overlap (safety)
                        # push magnitude: proportional to overlap
                        push_x = overlap_x + 2
                        push_y = overlap_y + 2

                        # direction vector from A to B
                        dx = (b['cx'] - a['cx'])
                        dy = (b['cy'] - a['cy'])
                        dist = math.hypot(dx, dy)
                        if dist < 1e-3:
                            # identical center, random small jitter
                            dx, dy = 1.0, 0.5
                            dist = math.hypot(dx, dy)

                        # normalize
                        nx = dx / dist
                        ny = dy / dist

                        # weights by priority (lower priority moves more)
                        wa = 1.0 / (a['priority'] + 1e-6)
                        wb = 1.0 / (b['priority'] + 1e-6)
                        sumw = wa + wb
                        # amount to move each
                        move_ax = -nx * push_x * (wa / sumw)
                        move_ay = -ny * push_y * (wa / sumw)
                        move_bx = nx * push_x * (wb / sumw)
                        move_by = ny * push_y * (wb / sumw)

                        # clamp per-step movement
                        move_ax = max(-move_limit, min(move_limit, move_ax))
                        move_ay = max(-move_limit, min(move_limit, move_ay))
                        move_bx = max(-move_limit, min(move_limit, move_bx))
                        move_by = max(-move_limit, min(move_limit, move_by))

                        # apply to canvas and update local state
                        canvas.move(a['lbl'], move_ax, move_ay)
                        canvas.move(b['lbl'], move_bx, move_by)
                        moved_any = True

                        # recompute bbox/centers
                        a_bbox = canvas.bbox(a['lbl'])
                        b_bbox = canvas.bbox(b['lbl'])
                        if a_bbox:
                            a['bbox'] = a_bbox
                            a['cx'] = (a_bbox[0] + a_bbox[2]) / 2.0
                            a['cy'] = (a_bbox[1] + a_bbox[3]) / 2.0
                        if b_bbox:
                            b['bbox'] = b_bbox
                            b['cx'] = (b_bbox[0] + b_bbox[2]) / 2.0
                            b['cy'] = (b_bbox[1] + b_bbox[3]) / 2.0
            if not moved_any:
                break
        # return updated bboxes
        return {k: state[k]['bbox'] for k in state}