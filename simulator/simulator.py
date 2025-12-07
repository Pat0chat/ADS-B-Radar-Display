#!/usr/bin/env python3

import random
import threading
import time
import math

from aircraft import Aircraft

class Simulator:
    def __init__(self, DEFAULT_NUM_AIRCRAFT, DEFAULT_RADIUS_KM, DEFAULT_UPDATE_INTERVAL, CENTER_LAT, CENTER_LON, _LOCK):
        self.num_aircraft = DEFAULT_NUM_AIRCRAFT
        self.radius_km = DEFAULT_RADIUS_KM
        self.update_interval = DEFAULT_UPDATE_INTERVAL
        self.center_lat = CENTER_LAT
        self.center_lon = CENTER_LON
        self.lock = _LOCK

        self.aircraft = []
        self.running = True

        for _ in range(self.num_aircraft):
            self.aircraft.append(
                Aircraft(self.center_lat, self.center_lon, self.radius_km))

        self.sim_thread = threading.Thread(target=self.run_loop, daemon=True)
        self.sim_thread.start()

    def run_loop(self):
        last = time.time()
        last_change = last
        while True:
            t = time.time()
            dt = t - last
            last = t

            if self.running:
                # every 60 seconds, maybe change aircraft count
                if t - last_change > 60:
                    last_change = t
                    if random.random() < 0.5:
                        self.num_aircraft += 1
                    else:
                        self.num_aircraft = max(1, self.num_aircraft - 1)

                with self.lock:
                    for ac in self.aircraft:
                        ac.step(dt)

                    # keep aircraft count stable
                    if len(self.aircraft) < self.num_aircraft:
                        self.aircraft.append(
                            Aircraft(self.center_lat, self.center_lon, self.radius_km))
                    elif len(self.aircraft) > self.num_aircraft:
                        self.aircraft.pop()

            time.sleep(self.update_interval)

    def snapshot(self):
        with self.lock:
            return [ac.to_json() for ac in self.aircraft]