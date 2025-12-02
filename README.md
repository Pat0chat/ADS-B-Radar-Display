# ADS-B Radar Display

Affichage radar temps réel utilisant **dump1090**, une clé **RTL-SDR** et une interface graphique Tkinter.

Ce script affiche :  
✔ avions en temps réel  
✔ symbole avion orienté selon le cap  
✔ altitude + vitesse + identification  
✔ historique des trajectoires  
✔ clic sur avion → fenêtre d’informations  

## 📦 1. Prérequis

### Matériel
- Raspberry Pi
- Clé RTL-SDR (RTL2832U)

### Logiciels
- Raspberry Pi OS
- Python 3.7+
- dump1090 (dump1090-fa)

## 📡 2. Installation

### dump1090-fa
```bash
sudo apt-get install build-essential fakeroot debhelper librtlsdr-dev pkg-config libncurses5-dev libbladerf-dev libhackrf-dev liblimesuite-dev libsoapysdr-dev devscripts
git clone https://github.com/flightaware/dump1090.git
./prepare-build.sh bookworm
cd package-bookworm
dpkg-buildpackage -b --no-sign
```

### ADS-B Radar Display
```bash
git clone https://github.com/Pat0chat/ADS-B-Radar-Display.git
cd ADS-B-Radar-Display
pip3 install -r requirements.txt
```

## 🛠️ 3. Configuration
Ouvrir le fichier `config.json` dans le dossier **ADS-B-Radar-Display** et modifier les valeurs :
```json
{
    "dump1090_url": "http://localhost:8080/data.json",
    "radar_range": 200,
    "radar_history": 50,
    "display_fps": 25,
    "display_smooth": 0.50,
    "station_lat": 46.6833,
    "station_lon": 2.1333
}
```

## ▶️ 6. Lancer l’application

### dump1090-fa
```bash
.\dump1090 --interactive --net
```

### ADS-B Radar Display
```bash
python3 radar_adsb_tk.py
```



