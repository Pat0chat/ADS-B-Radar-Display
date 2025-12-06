import threading
import time

import requests

class Dump1090Source:

    def __init__(self, url):
        self.url = url
        self.running = False
        self.alive = False
        self.last_seen_time = time.strftime("%H:%M:%S", time.localtime())
        self.latest_data = []
        self.lock = threading.Lock()

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    def last_seen(self):
        return self.last_seen_time
    
    def aircrafts_count(self):
        aircrafts_count = 0

        if self.latest_data:
            aircrafts_count = len(self.latest_data)

        return aircrafts_count

    def _loop(self):
        while self.running:
            try:
                r = requests.get(self.url, timeout=1.0)
                data = r.json()
                self.alive = True if data else False
                self._process(data)
            except:
                self.alive = False
                pass
            time.sleep(1)

    def _process(self, raw_list):
        self.last_seen_time = time.strftime("%H:%M:%S", time.localtime())
        with self.lock:
            self.latest_data = raw_list

    def snapshot(self):
        with self.lock:
            return self.latest_data.copy()