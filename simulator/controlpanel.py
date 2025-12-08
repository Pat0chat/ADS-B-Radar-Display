#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk

# ------------------- ControlPanel -------------------
class ControlPanel(tk.Tk):
    """ControlPanel class for the Dump1090 Simulator.

    This class handles UI and interactions with UI.
    """

    def __init__(self, sim, httpd):
        super().__init__()
        self.title("Simulator Control Panel")

        self.sim = sim
        self.httpd = httpd

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)

        # Number of aircraft
        ttk.Label(frame, text="Aircraft Count").grid(
            row=0, column=0, sticky="w")
        self.aircraft_var = tk.IntVar(value=sim.num_aircraft)
        ac_spin = ttk.Spinbox(frame, from_=1, to=200, textvariable=self.aircraft_var, width=6,
                              command=self.update_aircraft_count)
        ac_spin.grid(row=0, column=1)

        # Update interval
        ttk.Label(frame, text="Update Interval (sec)").grid(
            row=1, column=0, sticky="w")
        self.update_var = tk.DoubleVar(value=sim.update_interval)
        upd_spin = ttk.Spinbox(frame, from_=0.05, to=5.0, increment=0.05,
                               textvariable=self.update_var, width=6,
                               command=self.update_interval)
        upd_spin.grid(row=1, column=1)

        # Radius
        ttk.Label(frame, text="Spawn Radius (km)").grid(
            row=2, column=0, sticky="w")
        self.radius_var = tk.IntVar(value=sim.radius_km)
        r_spin = ttk.Spinbox(frame, from_=20, to=500, textvariable=self.radius_var,
                             width=6, command=self.update_radius)
        r_spin.grid(row=2, column=1)

        # Pause / resume
        self.pause_btn = ttk.Button(
            frame, text="Pause Simulation", command=self.toggle_pause)
        self.pause_btn.grid(row=3, column=0, columnspan=2, pady=10)

        # Status indicators
        ttk.Label(frame, text="HTTP Server:").grid(row=4, column=0, sticky="w")
        self.server_status = ttk.Label(
            frame, text="Running", foreground="green")
        self.server_status.grid(row=4, column=1)

        ttk.Label(frame, text="Aircraft Active:").grid(
            row=5, column=0, sticky="w")
        self.aircraft_status = ttk.Label(frame, text="0", foreground="blue")
        self.aircraft_status.grid(row=5, column=1)

        self.update_status_loop()

    def update_status_loop(self):
        """Update number of aircrafts status."""
        self.aircraft_status.config(text=str(len(self.sim.aircraft)))
        self.after(1000, self.update_status_loop)

    def update_aircraft_count(self):
        """Update simulation number of aircrafts."""
        self.sim.num_aircraft = self.aircraft_var.get()

    def update_interval(self):
        """Update simulation refresh interval."""
        self.sim.update_interval = self.update_var.get()

    def update_radius(self):
        """Update simulation maximum radius."""
        self.sim.radius_km = self.radius_var.get()

    def toggle_pause(self):
        """Play or pause the simulation."""
        self.sim.running = not self.sim.running
        self.pause_btn.config(
            text="Resume Simulation" if not self.sim.running else "Pause Simulation"
        )
