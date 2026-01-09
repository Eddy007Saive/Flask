#!/usr/bin/env python3
"""
Client de Pointage avec Interface Tkinter
Application complète pour gérer les pointages machines
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import socket
import platform
import json
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
import sys

# ==================== CONFIGURATION ====================

class Config:
    """Configuration globale"""
    SERVEUR_URL = 'http://192.168.88.16:5000/api/pointages'
    CONFIG_DIR = Path.home() / '.pointage_client'
    CONFIG_FILE = CONFIG_DIR / 'config.json'
    LOG_FILE = CONFIG_DIR / 'pointage.log'
    
    # Créer le dossier de config
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# ==================== CLASSES UTILITAIRES ====================

class PointageAPI:
    """Gestion des appels API"""
    
    @staticmethod
    def obtenir_id_machine():
        """Génère un ID machine unique"""
        config = PointageAPI.charger_config()
        if 'machine_id' in config:
            return config['machine_id']
        
        hostname = socket.gethostname()
        machine_id = hostname.replace(' ', '-').replace('.', '-').upper()
        
        PointageAPI.sauvegarder_config({'machine_id': machine_id})
        return machine_id
    
    @staticmethod
    def obtenir_nom_machine():
        """Récupère le nom de l'ordinateur"""
        return socket.gethostname()
    
    @staticmethod
    def obtenir_ip_locale():
        """Récupère l'IP locale"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    @staticmethod
    def obtenir_info_systeme():
        """Récupère les informations système"""
        return {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine()
        }
    
    @staticmethod
    def charger_config():
        """Charge la configuration locale"""
        try:
            if Config.CONFIG_FILE.exists():
                with open(Config.CONFIG_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    @staticmethod
    def sauvegarder_config(data):
        """Sauvegarde la configuration"""
        try:
            config = PointageAPI.charger_config()
            config.update(data)
            with open(Config.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Erreur sauvegarde config: {e}")
            return False
    
    @staticmethod
    def envoyer_pointage(type_pointage='allumage'):
        """Envoie un pointage au serveur"""
        machine_id = PointageAPI.obtenir_id_machine()
        machine_name = PointageAPI.obtenir_nom_machine()
        machine_ip = PointageAPI.obtenir_ip_locale()
        system_info = PointageAPI.obtenir_info_systeme()
        
        data = {
            'machineId': machine_id,
            'machineName': machine_name,
            'machineIp': machine_ip,
            'type': type_pointage,
            'systeme': system_info['system'],
            'timestamp': datetime.now().isoformat()
        }
        
        response = requests.post(
            Config.SERVEUR_URL,
            json=data,
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 201:
            result = response.json()
            PointageAPI.sauvegarder_config({
                'last_pointage': datetime.now().isoformat(),
                'last_type': type_pointage,
                'last_status': 'success'
            })
            return True, result
        else:
            return False, {'error': response.text}
    
    @staticmethod
    def tester_connexion():
        """Teste la connexion au serveur"""
        try:
            # Tenter de ping le serveur
            base_url = Config.SERVEUR_URL.rsplit('/api', 1)[0]
            response = requests.get(f"{base_url}/api/machines", timeout=5)
            return response.status_code in [200, 404]  # 404 aussi OK (serveur répond)
        except:
            return False

# ==================== APPLICATION PRINCIPALE ====================

class PointageClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Client Pointage Machine")
        self.root.geometry("700x850")
        self.root.resizable(True, True)  # Permettre le redimensionnement
        
        # Variables
        self.connected = tk.BooleanVar(value=False)
        self.auto_pointage = tk.BooleanVar(value=True)
        self.session_start = None
        self.elapsed_seconds = 0
        self.heartbeat_running = False
        
        # Charger la config
        self.config = PointageAPI.charger_config()
        
        # Setup UI
        self.setup_ui()
        
        # Démarrer les timers
        self.update_elapsed_time()
        self.root.after(1000, self.test_connection_auto)
        
        # Protocole de fermeture
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_ui(self):
        """Construit l'interface"""
        
        # ===== HEADER =====
        header_frame = tk.Frame(self.root, bg="#2563eb", height=80)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text="🖥️ Client Pointage Machine",
            font=("Arial", 18, "bold"),
            bg="#2563eb",
            fg="white"
        ).pack(pady=20)
        
        # ===== INFORMATIONS MACHINE =====
        info_frame = ttk.LabelFrame(self.root, text="📋 Informations Machine", padding=15)
        info_frame.pack(fill=tk.X, padx=20, pady=10)
        
        machine_id = PointageAPI.obtenir_id_machine()
        machine_name = PointageAPI.obtenir_nom_machine()
        machine_ip = PointageAPI.obtenir_ip_locale()
        system_info = PointageAPI.obtenir_info_systeme()
        
        info_data = [
            ("ID Machine:", machine_id),
            ("Nom:", machine_name),
            ("Adresse IP:", machine_ip),
            ("Système:", f"{system_info['system']} {system_info['release']}"),
        ]
        
        for i, (label, value) in enumerate(info_data):
            tk.Label(info_frame, text=label, font=("Arial", 9, "bold")).grid(
                row=i, column=0, sticky="w", pady=3
            )
            tk.Label(info_frame, text=value, font=("Arial", 9)).grid(
                row=i, column=1, sticky="w", padx=10, pady=3
            )
        
        # ===== STATUT CONNEXION =====
        status_frame = ttk.LabelFrame(self.root, text="🌐 Statut Connexion", padding=15)
        status_frame.pack(fill=tk.X, padx=20, pady=10)
        
        status_inner = tk.Frame(status_frame)
        status_inner.pack(fill=tk.X)
        
        self.status_indicator = tk.Canvas(status_inner, width=20, height=20, bg="white", highlightthickness=0)
        self.status_indicator.pack(side=tk.LEFT, padx=5)
        self.status_circle = self.status_indicator.create_oval(2, 2, 18, 18, fill="gray")
        
        self.status_label = tk.Label(status_inner, text="Non connecté", font=("Arial", 10))
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        tk.Button(
            status_inner,
            text="🔄 Tester",
            command=self.test_connection,
            bg="#e5e7eb",
            relief=tk.FLAT,
            padx=10
        ).pack(side=tk.RIGHT)
        
        # ===== CONFIGURATION =====
        config_frame = ttk.LabelFrame(self.root, text="⚙️ Configuration", padding=15)
        config_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(config_frame, text="URL Serveur:", font=("Arial", 9)).grid(
            row=0, column=0, sticky="w", pady=5
        )
        
        self.server_url_entry = tk.Entry(config_frame, font=("Arial", 9), width=40)
        self.server_url_entry.insert(0, Config.SERVEUR_URL)
        self.server_url_entry.grid(row=0, column=1, padx=10, pady=5)
        
        tk.Button(
            config_frame,
            text="💾 Sauvegarder",
            command=self.save_config,
            bg="#10b981",
            fg="white",
            relief=tk.FLAT,
            padx=10
        ).grid(row=0, column=2, padx=5)
        
        tk.Checkbutton(
            config_frame,
            text="Pointage automatique au démarrage",
            variable=self.auto_pointage,
            font=("Arial", 9)
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=5)
        
        # ===== SESSION =====
        session_frame = ttk.LabelFrame(self.root, text="⏱️ Session Actuelle", padding=15)
        session_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.session_label = tk.Label(
            session_frame,
            text="Aucune session active",
            font=("Arial", 12, "bold"),
            fg="#6b7280"
        )
        self.session_label.pack(pady=5)
        
        self.elapsed_label = tk.Label(
            session_frame,
            text="00:00:00",
            font=("Arial", 24, "bold"),
            fg="#2563eb"
        )
        self.elapsed_label.pack(pady=10)
        
        # ===== ACTIONS =====
        actions_frame = ttk.LabelFrame(self.root, text="🎯 Actions", padding=15)
        actions_frame.pack(fill=tk.X, padx=20, pady=10)
        
        btn_frame = tk.Frame(actions_frame)
        btn_frame.pack()
        
        self.btn_allumage = tk.Button(
            btn_frame,
            text="🟢 Pointage Allumage",
            command=lambda: self.envoyer_pointage('allumage'),
            bg="#10b981",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=10,
            width=20
        )
        self.btn_allumage.pack(side=tk.LEFT, padx=5)
        
        self.btn_extinction = tk.Button(
            btn_frame,
            text="🔴 Pointage Extinction",
            command=lambda: self.envoyer_pointage('extinction'),
            bg="#ef4444",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=10,
            width=20
        )
        self.btn_extinction.pack(side=tk.LEFT, padx=5)
        
        # ===== LOGS =====
        logs_frame = ttk.LabelFrame(self.root, text="📝 Logs", padding=10)
        logs_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 20))
        
        self.log_text = scrolledtext.ScrolledText(
            logs_frame,
            height=6,
            font=("Consolas", 9),
            bg="#f9fafb",
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Log initial
        self.log("✨ Application démarrée")
        self.log(f"📍 Machine: {machine_id}")
        self.log(f"🌐 Serveur: {Config.SERVEUR_URL}")
    
    def log(self, message):
        """Ajoute un message dans les logs"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        
        # Écrire dans le fichier log
        try:
            with open(Config.LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except:
            pass
    
    def update_status(self, connected):
        """Met à jour le statut de connexion"""
        self.connected.set(connected)
        if connected:
            self.status_indicator.itemconfig(self.status_circle, fill="#10b981")
            self.status_label.config(text="✅ Connecté au serveur", fg="#10b981")
        else:
            self.status_indicator.itemconfig(self.status_circle, fill="#ef4444")
            self.status_label.config(text="❌ Serveur inaccessible", fg="#ef4444")
    
    def test_connection(self):
        """Test la connexion au serveur (dans un thread)"""
        def _test():
            self.log("🔍 Test de connexion...")
            connected = PointageAPI.tester_connexion()
            self.root.after(0, lambda: self.update_status(connected))
            if connected:
                self.log("✅ Connexion réussie")
            else:
                self.log("❌ Impossible de contacter le serveur")
        
        threading.Thread(target=_test, daemon=True).start()
    
    def test_connection_auto(self):
        """Test automatique au démarrage"""
        self.test_connection()
    
    def save_config(self):
        """Sauvegarde la configuration"""
        new_url = self.server_url_entry.get().strip()
        if not new_url:
            messagebox.showerror("Erreur", "L'URL du serveur ne peut pas être vide")
            return
        
        Config.SERVEUR_URL = new_url
        PointageAPI.sauvegarder_config({
            'server_url': new_url,
            'auto_pointage': self.auto_pointage.get()
        })
        
        self.log(f"💾 Configuration sauvegardée: {new_url}")
        messagebox.showinfo("Succès", "Configuration sauvegardée !")
    
    def envoyer_pointage(self, type_pointage):
        """Envoie un pointage (dans un thread)"""
        def _send():
            self.log(f"📤 Envoi pointage {type_pointage}...")
            self.root.after(0, lambda: self.btn_allumage.config(state=tk.DISABLED))
            self.root.after(0, lambda: self.btn_extinction.config(state=tk.DISABLED))
            
            try:
                success, result = PointageAPI.envoyer_pointage(type_pointage)
                
                if success:
                    self.log(f"✅ Pointage {type_pointage} enregistré !")
                    if result.get('isNewMachine'):
                        self.log("🆕 Nouvelle machine créée automatiquement")
                    
                    # Mettre à jour la session
                    if type_pointage == 'allumage':
                        self.session_start = datetime.now()
                        self.elapsed_seconds = 0
                        self.root.after(0, lambda: self.session_label.config(
                            text="Session active",
                            fg="#10b981"
                        ))
                    else:
                        self.session_start = None
                        self.elapsed_seconds = 0
                        self.root.after(0, lambda: self.session_label.config(
                            text="Aucune session active",
                            fg="#6b7280"
                        ))
                        self.root.after(0, lambda: self.elapsed_label.config(text="00:00:00"))
                    
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Succès",
                        f"Pointage {type_pointage} enregistré avec succès !"
                    ))
                else:
                    error_msg = result.get('error', 'Erreur inconnue')
                    self.log(f"❌ Erreur: {error_msg}")
                    self.root.after(0, lambda: messagebox.showerror(
                        "Erreur",
                        f"Impossible d'envoyer le pointage:\n{error_msg}"
                    ))
            
            except Exception as e:
                self.log(f"💥 Exception: {str(e)}")
                self.root.after(0, lambda: messagebox.showerror(
                    "Erreur",
                    f"Une erreur est survenue:\n{str(e)}"
                ))
            
            finally:
                self.root.after(0, lambda: self.btn_allumage.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.btn_extinction.config(state=tk.NORMAL))
        
        threading.Thread(target=_send, daemon=True).start()
    
    def update_elapsed_time(self):
        """Met à jour le temps écoulé"""
        if self.session_start:
            self.elapsed_seconds = int((datetime.now() - self.session_start).total_seconds())
            hours = self.elapsed_seconds // 3600
            minutes = (self.elapsed_seconds % 3600) // 60
            seconds = self.elapsed_seconds % 60
            self.elapsed_label.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        
        self.root.after(1000, self.update_elapsed_time)
    
    def on_closing(self):
        """Gestion de la fermeture"""
        if self.session_start:
            response = messagebox.askyesnocancel(
                "Session active",
                "Une session est en cours.\n\n"
                "Voulez-vous envoyer un pointage d'extinction ?"
            )
            
            if response is None:  # Annuler
                return
            elif response:  # Oui
                try:
                    PointageAPI.envoyer_pointage('extinction')
                    self.log("✅ Pointage extinction envoyé")
                except:
                    pass
        
        self.log("👋 Fermeture de l'application")
        self.root.destroy()

# ==================== POINT D'ENTRÉE ====================

def main():
    """Lance l'application"""
    root = tk.Tk()
    app = PointageClientApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()