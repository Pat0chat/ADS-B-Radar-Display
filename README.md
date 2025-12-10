# ADS-B Radar Simulator and Display

Affichage radar temps réel utilisant **dump1090**, une clé **RTL-SDR** et une interface graphique Tkinter.

Ce script affiche :
- avions en temps réel  
- vecteur vitesse
- altitude + vitesse + identification  
- historique des trajectoires  
- clic sur avion → fenêtre d’informations
- cartography OSM

## 📦 1. Prérequis

### Matériel
- Raspberry Pi / Matériel Linux
- Clé RTL-SDR (RTL2832U)

### Logiciels
- Raspberry Pi OS / Distribution Ubuntu ou Debian 
- Python 3.7+
- dump1090

## 📡 2. Installation

```bash
git clone https://github.com/Pat0chat/ADS-B-Radar-Display.git
cd ADS-B-Radar-Display
pip install requests pillow pyproj
```

## 🛠️ 3. Configuration

### Simulateur
Ouvrir le fichier `config.json` dans le dossier **simulator** et modifier les valeurs :
```json
{
    "host": "0.0.0.0",
    "port": 8080,
    "default_num_aircraft": 10,
    "default_update_interval": 1,
    "default_radius_km": 10,
    "center_lat": 48.6833,
    "center_lon": 2.1333
}
```

### Radar
Ouvrir le fichier `config.json` dans le dossier **radar** et modifier les valeurs :
```json
{
    "data_url": "http://localhost:8080/data.json",
    "radar_lat": 48.6833,
    "radar_lon": 2.1333,
    "max_range_km": 200,
    "canvas_size": 800,
    "trail_max": 120
}
```

## ▶️ 4. Lancement

### Simulateur
```bash
./run_simulator_radar.sh
```

### Radar
```bash
./run_dump1090_radar.sh
```



