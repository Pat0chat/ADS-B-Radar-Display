#!/usr/bin/env python3

import http.server
import socketserver
import threading
import json


class Dump1090Handler(http.server.BaseHTTPRequestHandler):
    simulator = None

    def do_GET(self):
        if self.path.startswith("/data.json"):
            payload = json.dumps(self.simulator.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, *_):
        pass


def start_http_server(simulator, HOST, PORT):
    Dump1090Handler.simulator = simulator
    httpd = socketserver.ThreadingTCPServer((HOST, PORT), Dump1090Handler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    return httpd
