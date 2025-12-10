#!/usr/bin/env python3

import math
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
        self.label_leaders = {}
    
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

            # Delete canvas_ids
            if hexid in self.canvas_ids:
                del self.canvas_ids[hexid]
            
            # Delete label leaders
            if hexid in self.label_leaders:
                    canvas.delete(self.label_leaders[hexid])
                    del self.label_leaders[hexid]

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
    
    def clear_trails(self, max_trails):
        """Clear all trails."""
        for hexid in self.aircrafts.keys():
            self.aircrafts[hexid].trail.clear()
            self.aircrafts[hexid].set_max_trails(max_trails)
    
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

    def resolve_labels_and_draw_leaders(self, canvas):
        """
        1) Try spiral placement in priority order (closest first).
        2) If overlaps remain, run relaxation.
        3) Draw/update leader-lines.
        """
        # 1) collect labels with priority (distance to center)
        label_data = []
        for hexid, items in self.aircraft_canvas_items.items():
            lbl = items['label']
            outer = items['outer']
            x0, y0, x1, y1 = canvas.coords(outer)
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            aircraft = self.get_aircraft(hexid)
            priority_dist = aircraft.distance_km if aircraft else 99999
            # priority weight: closer => larger priority (so they move less)
            priority = 1.0 / (0.001 + priority_dist)  # small dist -> bigger priority
            label_data.append({'hex': hexid, 'lbl': lbl, 'cx': cx, 'cy': cy, 'priority': priority})

        # sort nearest first (highest priority weight first)
        label_data.sort(key=lambda i: -i['priority'])

        placed_bboxes = []
        placed_bboxes_map = {}  # hex -> bbox
        for info in label_data:
            bbox = self.place_label_spiral(canvas, info['lbl'], info['cx'], info['cy'], placed_bboxes, max_radius=90)
            if bbox:
                placed_bboxes.append(bbox)
                placed_bboxes_map[info['hex']] = bbox

        # 2) if overlaps still exist, relax (use the label_data list)
        # detect if any overlap in placed_bboxes
        need_relax = False
        bboxes = list(placed_bboxes_map.items())
        for i in range(len(bboxes)):
            for j in range(i+1, len(bboxes)):
                if self.bbox_overlap(bboxes[i][1], bboxes[j][1]):
                    need_relax = True
                    break
            if need_relax:
                break

        if need_relax:
            updated_map = self.relax_label_positions(canvas, label_data, placed_bboxes_map, iterations=8, move_limit=10)
            placed_bboxes_map.update(updated_map)

        # 3) draw/update leader-lines (self.label_leaders dict expected)
        if not hasattr(self, "label_leaders"):
            self.label_leaders = {}

        for info in label_data:
            hexid = info['hex']
            lbl = info['lbl']
            # get label bbox (fresh)
            bbox = placed_bboxes_map.get(hexid) or self.canvas.bbox(lbl)
            if bbox is None:
                continue
            # aircraft screen pos
            acx, acy = info['cx'], info['cy']
            # Compute label anchor point on the bbox edge
            label_edge_x, label_edge_y = self.closest_point_on_bbox(acx, acy, bbox)

            # Distance aircraft -> label edge
            px_dist = math.hypot(label_edge_x - acx, label_edge_y - acy)

            # Threshold for drawing leader-line
            if px_dist > 15:
                if hexid not in self.label_leaders:
                    self.label_leaders[hexid] = canvas.create_line(
                        acx, acy,
                        label_edge_x, label_edge_y,
                        fill="#ffffff",
                        width=1,
                        dash=(3, 2),
                        tags=("leader",),
                        smooth=True
                    )
                else:
                    canvas.coords(self.label_leaders[hexid], acx, acy, label_edge_x, label_edge_y)
            else:
                if hexid in self.label_leaders:
                    canvas.delete(self.label_leaders[hexid])
                    del self.label_leaders[hexid]



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

    def set_max_trails(self, max_trails):
        self.trail = deque(self.trail, maxlen=max_trails)

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