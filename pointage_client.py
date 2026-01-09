#!/usr/bin/env python3
"""
Client Pointage avec WebSocket
Communication temps réel avec le serveur
Inclut le calcul de la durée de session
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import socketio
import socket
import platform
import json
import threading
import time
from pathlib import Path
from datetime import datetime

# ==================== CONFIGURATION ====================

class Config:
    SERVEUR_URL = 'http://192.168.88.16:5000'
    CONFIG_DIR = Path.home() / '.pointage_client'
    CONFIG_FILE = CONFIG_DIR / 'config.json'
    LOG_FILE = CONFIG_DIR / 'pointage.log'
    HEARTBEAT_INTERVAL = 30  # secondes
    
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# ==================== CLIENT WEBSOCKET ====================

class WebSocketClient:
    def __init__(self, app_instance):
        self.app = app_instance
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=5)
        self.connected = False
        self.machine_id = None
        self.setup_events()
    
    def setup_events(self):
        """Configuration des événements WebSocket"""
        
        @self.sio.on('connect')
        def on_connect():
            self.connected = True
            self.app.log("🔌 WebSocket connecté")
            self.app.update_ws_status(True)
            
            # Enregistrer la machine
            self.register_machine()
        
        @self.sio.on('disconnect')
        def on_disconnect():
            self.connected = False
            self.app.log("❌ WebSocket déconnecté")
            self.app.update_ws_status(False)
        
        @self.sio.on('registered')
        def on_registered(data):
            self.app.log(f"✅ Machine enregistrée: {data.get('machineId')}")
        
        @self.sio.on('heartbeat_ack')
        def on_heartbeat_ack(data):
            pass  # Heartbeat silencieux
        
        @self.sio.on('pointage_confirmed')
        def on_pointage_confirmed(data):
            pointage_type = data.get('type', 'inconnu')
            self.app.log(f"✅ Pointage {pointage_type} confirmé")
            self.app.log(f"   ID: {data.get('id')}")
            
            # Si c'est une extinction avec durée
            if pointage_type == 'extinction' and 'sessionDuration' in data:
                duration = data['sessionDuration']
                self.app.log(f"   ⏱️  Durée session: {duration.get('formatted', 'N/A')}")
                self.app.log(f"   📊 Total heures: {duration.get('hours', 0):.2f}h")
        
        @self.sio.on('command')
        def on_command(data):
            """Recevoir une commande du serveur"""
            command = data.get('command')
            self.app.log(f"📥 Commande reçue: {command}")
            
            if command == 'request_pointage':
                self.app.log("   → Envoi pointage automatique...")
                self.app.root.after(0, lambda: self.app.envoyer_pointage('allumage'))
            
            elif command == 'shutdown':
                self.app.log("   → Demande d'extinction...")
                self.app.root.after(0, self.app.on_closing)
        
        @self.sio.on('status_update')
        def on_status_update(data):
            """Mise à jour du statut depuis le serveur"""
            self.app.log(f"📊 Statut mis à jour: {data.get('status')}")
        
        @self.sio.on('error')
        def on_error(data):
            self.app.log(f"❌ Erreur serveur: {data.get('message')}")
    
    def connect(self, url):
        """Se connecter au serveur WebSocket"""
        try:
            self.app.log(f"🔗 Connexion à {url}...")
            self.sio.connect(url, wait_timeout=10)
            return True
        except Exception as e:
            self.app.log(f"❌ Erreur connexion: {e}")
            return False
    
    def disconnect(self):
        """Se déconnecter"""
        if self.connected:
            self.sio.disconnect()
    
    def register_machine(self):
        """Enregistrer la machine auprès du serveur"""
        machine_id = self.app.obtenir_id_machine()
        machine_name = self.app.obtenir_nom_machine()
        machine_ip = self.app.obtenir_ip_locale()
        system_info = self.app.obtenir_info_systeme()
        
        self.machine_id = machine_id
        
        self.sio.emit('register_machine', {
            'machineId': machine_id,
            'machineName': machine_name,
            'machineIp': machine_ip,
            'systemInfo': system_info
        })
    
    def send_heartbeat(self):
        """Envoyer un heartbeat"""
        if self.connected and self.machine_id:
            self.sio.emit('heartbeat', {
                'machineId': self.machine_id,
                'timestamp': datetime.now().isoformat()
            })
    
    def send_pointage(self, type_pointage, session_duration_seconds=None):
        """Envoyer un pointage via WebSocket avec durée de session optionnelle"""
        if not self.connected:
            raise Exception("WebSocket non connecté")
        
        pointage_data = {
            'machineId': self.machine_id,
            'machineName': self.app.obtenir_nom_machine(),
            'machineIp': self.app.obtenir_ip_locale(),
            'type': type_pointage,
            'timestamp': datetime.now().isoformat()
        }
        
        # Ajouter la durée de session si c'est une extinction
        if type_pointage == 'extinction' and session_duration_seconds is not None:
            hours = session_duration_seconds / 3600
            pointage_data['sessionDuration'] = {
                'seconds': session_duration_seconds,
                'hours': round(hours, 2),
                'formatted': self._format_duration(session_duration_seconds)
            }
            
            self.app.log(f"⏱️  Durée de la session: {pointage_data['sessionDuration']['formatted']}")
            self.app.log(f"📊 Total: {hours:.2f} heures")
        
        self.sio.emit('pointage', pointage_data)
    
    def _format_duration(self, seconds):
        """Formater la durée en HH:MM:SS"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

# ==================== APPLICATION TKINTER ====================

class PointageClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Client Pointage Machine - WebSocket")
        self.root.geometry("700x900")
        self.root.resizable(True, True)
        
        # Variables
        self.ws_connected = tk.BooleanVar(value=False)
        self.auto_pointage = tk.BooleanVar(value=True)
        self.session_start = None
        self.elapsed_seconds = 0
        
        # Client WebSocket
        self.ws_client = WebSocketClient(self)
        self.heartbeat_running = False
        
        # Setup UI
        self.setup_ui()
        
        # Timers
        self.update_elapsed_time()
        self.root.after(2000, self.connect_websocket)
        
        # Protocole de fermeture
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_ui(self):
        """Interface utilisateur"""
        
        # Header
        header_frame = tk.Frame(self.root, bg="#2563eb", height=80)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text="🖥️ Client Pointage Machine - WebSocket",
            font=("Arial", 16, "bold"),
            bg="#2563eb",
            fg="white"
        ).pack(pady=25)
        
        # Informations Machine
        info_frame = ttk.LabelFrame(self.root, text="📋 Informations Machine", padding=15)
        info_frame.pack(fill=tk.X, padx=20, pady=10)
        
        machine_id = self.obtenir_id_machine()
        machine_name = self.obtenir_nom_machine()
        machine_ip = self.obtenir_ip_locale()
        system_info = self.obtenir_info_systeme()
        
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
        
        # Statut WebSocket
        status_frame = ttk.LabelFrame(self.root, text="🌐 Statut WebSocket", padding=15)
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
            text="🔄 Reconnecter",
            command=self.reconnect_websocket,
            bg="#e5e7eb",
            relief=tk.FLAT,
            padx=10
        ).pack(side=tk.RIGHT)
        
        # Configuration
        config_frame = ttk.LabelFrame(self.root, text="⚙️ Configuration", padding=15)
        config_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(config_frame, text="URL Serveur:", font=("Arial", 9)).grid(
            row=0, column=0, sticky="w", pady=5
        )
        
        self.server_url_entry = tk.Entry(config_frame, font=("Arial", 9), width=35)
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
        ).grid(row=0, column=2)
        
        # Session
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
        
        # Affichage des heures
        self.hours_label = tk.Label(
            session_frame,
            text="0.00 heures",
            font=("Arial", 11),
            fg="#6b7280"
        )
        self.hours_label.pack(pady=5)
        
        # Actions
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
        
        # Logs
        logs_frame = ttk.LabelFrame(self.root, text="📝 Logs", padding=10)
        logs_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 20))
        
        self.log_text = scrolledtext.ScrolledText(
            logs_frame,
            height=8,
            font=("Consolas", 9),
            bg="#f9fafb",
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Log initial
        self.log("✨ Application démarrée (Mode WebSocket)")
        self.log(f"📍 Machine: {machine_id}")
        self.log(f"🌐 Serveur: {Config.SERVEUR_URL}")
    
    # ==================== MÉTHODES UTILITAIRES ====================
    
    def obtenir_id_machine(self):
        config = self.charger_config()
        if 'machine_id' in config:
            return config['machine_id']
        hostname = socket.gethostname()
        machine_id = hostname.replace(' ', '-').replace('.', '-').upper()
        self.sauvegarder_config({'machine_id': machine_id})
        return machine_id
    
    def obtenir_nom_machine(self):
        return socket.gethostname()
    
    def obtenir_ip_locale(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def obtenir_info_systeme(self):
        return {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine()
        }
    
    def charger_config(self):
        try:
            if Config.CONFIG_FILE.exists():
                with open(Config.CONFIG_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def sauvegarder_config(self, data):
        try:
            config = self.charger_config()
            config.update(data)
            with open(Config.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except:
            return False
    
    def log(self, message):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        
        try:
            with open(Config.LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except:
            pass
    
    # ==================== WEBSOCKET ====================
    
    def connect_websocket(self):
        """Connexion WebSocket dans un thread"""
        def _connect():
            success = self.ws_client.connect(Config.SERVEUR_URL)
            if success:
                self.start_heartbeat()
        
        threading.Thread(target=_connect, daemon=True).start()
    
    def reconnect_websocket(self):
        """Reconnecter WebSocket"""
        self.log("🔄 Tentative de reconnexion...")
        self.ws_client.disconnect()
        time.sleep(1)
        self.connect_websocket()
    
    def update_ws_status(self, connected):
        """Mettre à jour le statut visuel"""
        self.ws_connected.set(connected)
        if connected:
            self.status_indicator.itemconfig(self.status_circle, fill="#10b981")
            self.status_label.config(text="✅ WebSocket connecté", fg="#10b981")
        else:
            self.status_indicator.itemconfig(self.status_circle, fill="#ef4444")
            self.status_label.config(text="❌ WebSocket déconnecté", fg="#ef4444")
    
    def start_heartbeat(self):
        """Démarrer le heartbeat automatique"""
        if self.heartbeat_running:
            return
        
        self.heartbeat_running = True
        self.log(f"💓 Heartbeat démarré ({Config.HEARTBEAT_INTERVAL}s)")
        
        def _heartbeat():
            while self.heartbeat_running:
                if self.ws_client.connected:
                    self.ws_client.send_heartbeat()
                time.sleep(Config.HEARTBEAT_INTERVAL)
        
        threading.Thread(target=_heartbeat, daemon=True).start()
    
    def stop_heartbeat(self):
        """Arrêter le heartbeat"""
        self.heartbeat_running = False
        self.log("💓 Heartbeat arrêté")
    
    # ==================== ACTIONS ====================
    
    def save_config(self):
        new_url = self.server_url_entry.get().strip()
        if not new_url:
            messagebox.showerror("Erreur", "L'URL ne peut pas être vide")
            return
        
        Config.SERVEUR_URL = new_url
        self.sauvegarder_config({'server_url': new_url})
        self.log(f"💾 Configuration sauvegardée")
        messagebox.showinfo("Succès", "Configuration sauvegardée !\nReconnectez pour appliquer.")
    
    def envoyer_pointage(self, type_pointage):
        """Envoyer un pointage via WebSocket avec calcul de durée"""
        def _send():
            self.root.after(0, lambda: self.btn_allumage.config(state=tk.DISABLED))
            self.root.after(0, lambda: self.btn_extinction.config(state=tk.DISABLED))
            
            try:
                self.log(f"📤 Envoi pointage {type_pointage} (WebSocket)...")
                
                # Calculer la durée si c'est une extinction
                session_duration = None
                if type_pointage == 'extinction' and self.session_start:
                    session_duration = int((datetime.now() - self.session_start).total_seconds())
                    self.log(f"⏱️  Calcul durée session: {session_duration} secondes")
                
                # Envoyer le pointage avec la durée
                self.ws_client.send_pointage(type_pointage, session_duration)
                
                # Mettre à jour la session
                if type_pointage == 'allumage':
                    self.session_start = datetime.now()
                    self.elapsed_seconds = 0
                    self.root.after(0, lambda: self.session_label.config(
                        text="Session active", fg="#10b981"
                    ))
                else:
                    self.session_start = None
                    self.elapsed_seconds = 0
                    self.root.after(0, lambda: self.session_label.config(
                        text="Aucune session active", fg="#6b7280"
                    ))
                    self.root.after(0, lambda: self.elapsed_label.config(text="00:00:00"))
                    self.root.after(0, lambda: self.hours_label.config(text="0.00 heures"))
                
                self.root.after(0, lambda: messagebox.showinfo(
                    "Succès", f"Pointage {type_pointage} envoyé !"
                ))
            
            except Exception as e:
                self.log(f"❌ Erreur: {e}")
                self.root.after(0, lambda: messagebox.showerror(
                    "Erreur", f"Impossible d'envoyer le pointage:\n{e}"
                ))
            
            finally:
                self.root.after(0, lambda: self.btn_allumage.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.btn_extinction.config(state=tk.NORMAL))
        
        threading.Thread(target=_send, daemon=True).start()
    
    def update_elapsed_time(self):
        """Mettre à jour le chronomètre"""
        if self.session_start:
            self.elapsed_seconds = int((datetime.now() - self.session_start).total_seconds())
            hours = self.elapsed_seconds // 3600
            minutes = (self.elapsed_seconds % 3600) // 60
            seconds = self.elapsed_seconds % 60
            self.elapsed_label.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            
            # Afficher les heures décimales
            total_hours = self.elapsed_seconds / 3600
            self.hours_label.config(text=f"{total_hours:.2f} heures")
        
        self.root.after(1000, self.update_elapsed_time)
    
    def on_closing(self):
        """Fermeture de l'application"""
        if self.session_start:
            response = messagebox.askyesnocancel(
                "Session active",
                "Envoyer un pointage d'extinction ?"
            )
            
            if response is None:
                return
            elif response:
                try:
                    # Calculer la durée de la session
                    session_duration = int((datetime.now() - self.session_start).total_seconds())
                    self.ws_client.send_pointage('extinction', session_duration)
                    self.log("✅ Pointage extinction envoyé avec durée")
                    time.sleep(0.5)
                except:
                    pass
        
        self.log("👋 Fermeture...")
        self.stop_heartbeat()
        self.ws_client.disconnect()
        self.root.destroy()

# ==================== MAIN ====================

def main():
    root = tk.Tk()
    app = PointageClientApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()