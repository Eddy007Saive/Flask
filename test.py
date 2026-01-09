import os
import subprocess
import sys

INSTALL_DIR = r"C:\PointageClient"
SCRIPT_NAME = "client_pointage.py"
LANCER_NAME = "lancer_pointage.bat"

# Crée le dossier
os.makedirs(INSTALL_DIR, exist_ok=True)

# Écrit le script Python final
client_script = """
import requests
import socket
import platform
import time
import atexit

SERVEUR_URL = "http://192.168.88.16:5000/pointage"

def envoyer_pointage(type_pointage):
    try:
        data = {
            "nom_machine": socket.gethostname(),
            "systeme": platform.system(),
            "type_pointage": type_pointage
        }
        requests.post(SERVEUR_URL, json=data, timeout=10)
    except:
        pass

atexit.register(lambda: envoyer_pointage("extinction"))

if __name__ == "__main__":
    time.sleep(10)
    envoyer_pointage("allumage")
    while True:
        time.sleep(60)
"""

with open(os.path.join(INSTALL_DIR, SCRIPT_NAME), "w", encoding="utf-8") as f:
    f.write(client_script)

# Crée venv
subprocess.run([sys.executable, "-m", "venv", os.path.join(INSTALL_DIR, "venv")])

# Installe requests
pip_exe = os.path.join(INSTALL_DIR, "venv", "Scripts", "pip.exe")
subprocess.run([pip_exe, "install", "requests"])

# Crée le lanceur
lancer_bat = f"""@echo off
cd /d "{INSTALL_DIR}"
call venv\\Scripts\\activate.bat
start /min python {SCRIPT_NAME}
"""
with open(os.path.join(INSTALL_DIR, LANCER_NAME), "w", encoding="utf-8") as f:
    f.write(lancer_bat)

# Crée la tâche planifiée pour démarrage automatique
subprocess.run([
    "schtasks", "/create",
    "/tn", "PointageAutomatique",
    "/tr", os.path.join(INSTALL_DIR, LANCER_NAME),
    "/sc", "onlogon",
    "/rl", "highest",
    "/f"
])
