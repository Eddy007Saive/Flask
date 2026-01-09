@echo off
chcp 65001 >nul
color 0A
title Installation Systeme de Pointage

echo ===================================================
echo    INSTALLEUR AUTOMATIQUE - SYSTEME DE POINTAGE
echo ===================================================
echo.

:: ===== Vérification droits admin =====
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERREUR] Ce script necessite les droits administrateur.
    echo Clic droit > Executer en tant qu'administrateur
    pause
    exit /b 1
)

:: ===== 1. Vérification Python =====
echo [1/7] Verification de Python...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Telechargement de Python...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.7/python-3.11.7-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"
    echo [INFO] Installation de Python...
    start /wait %TEMP%\python_installer.exe /quiet InstallAllUsers=1 PrependPath=1
    del %TEMP%\python_installer.exe
    echo [OK] Python installe
) else (
    echo [OK] Python deja installe
)

:: ===== 2. Configuration serveur =====
echo.
set /p SERVER_IP="Entrez l'IP du serveur (ex: 192.168.88.16): "

:: ===== 3. Dossier installation =====
echo.
echo [3/7] Creation dossier...
set INSTALL_DIR=C:\PointageClient
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
cd /d "%INSTALL_DIR%"
echo [OK] Dossier : %INSTALL_DIR%

:: ===== 4. Environnement virtuel =====
echo.
echo [4/7] Environnement virtuel...
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat
echo [OK] Environnement actif

:: ===== 5. Dépendances =====
echo.
echo [5/7] Installation dependances...
python -m pip install --upgrade pip
python -m pip install requests
echo [OK] Dependances installees

:: ===== 6. Création du script Python (PowerShell SAFE) =====
echo.
echo [6/7] Creation du script client_pointage.py...

powershell -Command ^
"$content = @'
import requests
import socket
import platform
import time
import atexit
import json
import os
from datetime import datetime

SERVEUR_URL = 'http://%SERVER_IP%:5000/pointage'

def obtenir_nom_machine():
    return socket.gethostname()

def envoyer_pointage(type_pointage='allumage'):
    try:
        nom_machine = obtenir_nom_machine()
        data = {
            'nom_machine': nom_machine,
            'systeme': platform.system(),
            'type_pointage': type_pointage
        }
        response = requests.post(SERVEUR_URL, json=data, timeout=10)
        return response.status_code == 201
    except Exception:
        sauvegarder_pointage_local(type_pointage)
        return False

def sauvegarder_pointage_local(type_pointage):
    pointage = {
        'machine': obtenir_nom_machine(),
        'type': type_pointage,
        'date_heure': datetime.now().isoformat()
    }
    try:
        with open('pointages_en_attente.json', 'r') as f:
            pointages = json.load(f)
    except:
        pointages = []
    pointages.append(pointage)
    with open('pointages_en_attente.json', 'w') as f:
        json.dump(pointages, f)

def synchroniser_pointages_locaux():
    if not os.path.exists('pointages_en_attente.json'):
        return
    with open('pointages_en_attente.json', 'r') as f:
        pointages = json.load(f)
    for p in pointages[:]:
        try:
            r = requests.post(
                SERVEUR_URL,
                json={'nom_machine': p['machine'], 'type_pointage': p['type']},
                timeout=5
            )
            if r.status_code == 201:
                pointages.remove(p)
        except:
            pass
    with open('pointages_en_attente.json', 'w') as f:
        json.dump(pointages, f)

def pointage_extinction():
    envoyer_pointage('extinction')

atexit.register(pointage_extinction)

if __name__ == '__main__':
    print('SYSTEME DE POINTAGE DEMARRE')
    time.sleep(10)
    synchroniser_pointages_locaux()
    envoyer_pointage('allumage')
    while True:
        time.sleep(60)
'@
Set-Content -Path 'client_pointage.py' -Value $content -Encoding UTF8"

if exist "client_pointage.py" (
    echo [OK] Script Python cree
) else (
    echo [ERREUR] Creation du script echouee
    pause
    exit /b 1
)

:: ===== 7. Lanceur =====
echo.
echo [7/7] Creation du lanceur...

(
echo @echo off
echo cd /d "%INSTALL_DIR%"
echo call venv\Scripts\activate.bat
echo start /min python client_pointage.py
) > lancer_pointage.bat

:: ===== Tâche planifiée =====
schtasks /delete /tn "PointageAutomatique" /f >nul 2>&1
schtasks /create ^
 /tn "PointageAutomatique" ^
 /tr "\"%INSTALL_DIR%\lancer_pointage.bat\"" ^
 /sc onlogon ^
 /rl highest ^
 /f

echo.
echo ===================================================
echo        INSTALLATION TERMINEE AVEC SUCCES
echo ===================================================
echo.
echo Dossier : %INSTALL_DIR%
echo Serveur : http://%SERVER_IP%:5000
echo Machine : %COMPUTERNAME%
echo.

pause
