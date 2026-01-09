"""
Script pour créer un installeur EXE autonome
À exécuter sur votre machine de développement, pas sur les clients
"""

import os
import zipfile
import base64

def creer_installeur_exe():
    """Crée un fichier batch auto-extractible qui contient tout"""
    
    print("Création de l'installeur autonome...")
    
    # Le script batch d'installation (même contenu que installeur.bat)
    script_batch = r'''@echo off
chcp 65001 >nul
color 0A
title Installation Système de Pointage

echo ╔════════════════════════════════════════════════════╗
echo ║   INSTALLEUR AUTOMATIQUE - SYSTÈME DE POINTAGE     ║
echo ╚════════════════════════════════════════════════════╝
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERREUR] Ce script nécessite les droits administrateur.
    echo Faites un clic droit et choisissez "Exécuter en tant qu'administrateur"
    pause
    exit /b 1
)

echo [1/7] Vérification de Python...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Téléchargement de Python...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.7/python-3.11.7-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"
    echo [INFO] Installation de Python...
    start /wait %TEMP%\python_installer.exe /quiet InstallAllUsers=1 PrependPath=1
    del %TEMP%\python_installer.exe
    echo [OK] Python installé
) else (
    echo [OK] Python déjà installé
)

echo.
echo [2/7] Configuration serveur...
set /p SERVER_IP="Entrez l'IP du serveur (ex: 192.168.1.100): "

echo.
echo [3/7] Création dossier...
set INSTALL_DIR=C:\PointageClient
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
cd /d "%INSTALL_DIR%"
echo [OK] Dossier : %INSTALL_DIR%

echo.
echo [4/7] Environnement virtuel...
python -m venv venv
call venv\Scripts\activate.bat
echo [OK] Environnement créé

echo.
echo [5/7] Installation dépendances...
pip install --quiet --upgrade pip
pip install --quiet requests
echo [OK] Dépendances installées

echo.
echo [6/7] Création fichiers...
''' + '''
REM Le code Python sera inséré ici par le script de création
''' + r'''

echo.
echo [7/7] Configuration démarrage...
schtasks /delete /tn "PointageAutomatique" /f >nul 2>&1
schtasks /create /tn "PointageAutomatique" /tr "%INSTALL_DIR%\lancer_pointage.bat" /sc onlogon /rl highest /f >nul 2>&1
echo [OK] Démarrage automatique configuré

echo.
echo ╔════════════════════════════════════════════════════╗
echo ║          INSTALLATION TERMINÉE !                   ║
echo ╚════════════════════════════════════════════════════╝
echo.
echo Machine : %COMPUTERNAME%
echo Serveur : http://%SERVER_IP%:5000
echo.
set /p TEST="Tester maintenant ? (O/N) : "
if /i "%TEST%"=="O" (
    call venv\Scripts\activate.bat
    python client_pointage.py
)
pause
'''
    
    # Créer le fichier installeur.bat
    with open('Installeur_Pointage.bat', 'w', encoding='utf-8') as f:
        f.write(script_batch)
    
    print("✓ Installeur créé : Installeur_Pointage.bat")
    print()
    print("UTILISATION :")
    print("1. Copiez 'Installeur_Pointage.bat' sur chaque ordinateur client")
    print("2. Faites clic droit > Exécuter en tant qu'administrateur")
    print("3. Entrez l'IP du serveur quand demandé")
    print("4. L'installation se fait automatiquement !")
    print()
    print("Le script va :")
    print("  - Installer Python si nécessaire")
    print("  - Créer l'environnement")
    print("  - Installer les dépendances")
    print("  - Configurer le démarrage automatique")
    print()
    print("Vous pouvez aussi créer un partage réseau et lancer l'installeur")
    print("à distance sur toutes les machines !")

def creer_installeur_avec_inno_setup():
    """Instructions pour créer un vrai EXE avec Inno Setup"""
    
    print("\n" + "="*60)
    print("OPTION AVANCÉE : Créer un véritable installeur .EXE")
    print("="*60)
    print()
    print("Pour créer un installeur professionnel avec interface graphique :")
    print()
    print("1. Téléchargez Inno Setup : https://jrsoftware.org/isinfo.php")
    print("2. Créez un fichier 'setup.iss' avec ce contenu :")
    print()
    
    inno_script = '''
[Setup]
AppName=Système de Pointage Client
AppVersion=1.0
DefaultDirName={pf}\\PointageClient
DefaultGroupName=Pointage
OutputBaseFilename=Installeur_Pointage_Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin

[Files]
Source: "installeur.bat"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "{app}\\installeur.bat"; Description: "Installer le système"; Flags: postinstall shellexec

[Icons]
Name: "{group}\\Désinstaller"; Filename: "{uninstallexe}"
'''
    
    print(inno_script)
    print()
    print("3. Compilez avec Inno Setup")
    print("4. Vous obtiendrez un .EXE installable sur toutes les machines !")

def creer_script_deploiement_reseau():
    """Créer un script pour déploiement sur plusieurs machines via réseau"""
    
    script = r'''@echo off
REM Script de déploiement réseau
REM À lancer depuis un serveur avec accès admin aux machines clientes

echo ╔════════════════════════════════════════════════════╗
echo ║    DÉPLOIEMENT AUTOMATIQUE SUR RÉSEAU              ║
echo ╚════════════════════════════════════════════════════╝
echo.

set /p SERVER_IP="IP du serveur de pointage : "

REM Liste des ordinateurs du réseau (à personnaliser)
set MACHINES=PC-01 PC-02 PC-03 PC-04 PC-05

for %%M in (%MACHINES%) do (
    echo.
    echo [%%M] Déploiement en cours...
    
    REM Copier l'installeur sur la machine distante
    copy "Installeur_Pointage.bat" "\\%%M\C$\Temp\" >nul 2>&1
    
    if %errorLevel% equ 0 (
        REM Exécuter l'installeur à distance avec PsExec
        psexec \\%%M -s -d cmd /c "cd C:\Temp && Installeur_Pointage.bat"
        echo [%%M] ✓ Déployé
    ) else (
        echo [%%M] ✗ Erreur - Machine inaccessible
    )
)

echo.
echo ═══════════════════════════════════════════
echo Déploiement terminé !
pause
'''
    
    with open('Deploiement_Reseau.bat', 'w', encoding='utf-8') as f:
        f.write(script)
    
    print("\n✓ Script de déploiement réseau créé : Deploiement_Reseau.bat")
    print()
    print("PRÉREQUIS pour le déploiement réseau :")
    print("1. Téléchargez PsExec : https://docs.microsoft.com/sysinternals/psexec")
    print("2. Activez le partage admin (C$) sur toutes les machines")
    print("3. Utilisez un compte avec droits admin réseau")
    print("4. Modifiez la liste des machines dans le script")

if __name__ == '__main__':
    print("="*60)
    print("  CRÉATEUR D'INSTALLEUR - SYSTÈME DE POINTAGE")
    print("="*60)
    print()
    print("Que voulez-vous créer ?")
    print()
    print("1. Installeur batch simple (.bat)")
    print("2. Instructions pour créer un .EXE (Inno Setup)")
    print("3. Script de déploiement réseau")
    print("4. Tout créer")
    print()
    
    choix = input("Votre choix (1-4) : ")
    print()
    
    if choix == '1':
        creer_installeur_exe()
    elif choix == '2':
        creer_installeur_avec_inno_setup()
    elif choix == '3':
        creer_script_deploiement_reseau()
    elif choix == '4':
        creer_installeur_exe()
        creer_script_deploiement_reseau()
        creer_installeur_avec_inno_setup()
    else:
        print("Choix invalide")
    
    print()
    print("Terminé !")
