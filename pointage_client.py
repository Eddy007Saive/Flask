#!/usr/bin/env python3
"""
PointTrack - Système de Pointage Professionnel
Interface moderne avec gestion avancée
"""

import tkinter as tk
from tkinter import ttk, messagebox
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
    CONFIG_DIR = Path.home() / '.pointtrack'
    CONFIG_FILE = CONFIG_DIR / 'config.json'
    HEARTBEAT_INTERVAL = 30
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# ==================== WEBSOCKET CLIENT ====================

class WebSocketClient:
    def __init__(self, app):
        self.app = app
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=5)
        self.connected = False
        self.machine_id = None
        self.setup_events()

    def setup_events(self):
        @self.sio.on('connect')
        def on_connect():
            self.connected = True
            self.app.update_ws_status(True)
            self.app.show_notification("Connexion établie", "success")
            self.register_machine()

        @self.sio.on('disconnect')
        def on_disconnect():
            self.connected = False
            self.app.update_ws_status(False)
            self.app.show_notification("Connexion perdue", "error")

        @self.sio.on('pointage_confirmed')
        def on_pointage_confirmed(data):
            t = data.get('type')
            msg = f"Pointage {t} enregistré"
            if t == 'extinction' and 'sessionDuration' in data:
                d = data['sessionDuration']
                msg += f"\nDurée: {d['formatted']}"
            self.app.show_notification(msg, "success")

    def connect(self, url):
        try:
            self.sio.connect(url, wait_timeout=10)
            return True
        except Exception as e:
            self.app.show_notification(f"Erreur: {str(e)}", "error")
            return False

    def disconnect(self):
        if self.connected:
            self.sio.disconnect()

    def register_machine(self):
        self.machine_id = self.app.obtenir_id_machine()
        self.sio.emit('register_machine', {
            'machineId': self.machine_id,
            'machineName': self.app.obtenir_nom_machine(),
            'machineIp': self.app.obtenir_ip_locale(),
            'systemInfo': self.app.obtenir_info_systeme()
        })

    def send_heartbeat(self):
        if self.connected and self.machine_id:
            self.sio.emit('heartbeat', {
                'machineId': self.machine_id,
                'timestamp': datetime.now().isoformat()
            })

    def send_pointage(self, type_pointage, session_duration_seconds=None):
        if not self.connected:
            raise Exception("Non connecté au serveur")
        data = {
            'machineId': self.machine_id,
            'machineName': self.app.obtenir_nom_machine(),
            'machineIp': self.app.obtenir_ip_locale(),
            'type': type_pointage,
            'timestamp': datetime.now().isoformat()
        }
        if type_pointage == 'extinction' and session_duration_seconds is not None:
            hours = session_duration_seconds / 3600
            data['sessionDuration'] = {
                'seconds': session_duration_seconds,
                'hours': round(hours, 2),
                'formatted': self._format_duration(session_duration_seconds)
            }
        self.sio.emit('pointage', data)

    def _format_duration(self, seconds):
        h, s = divmod(seconds, 3600)
        m, s = divmod(s, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

# ==================== APPLICATION PRINCIPALE ====================

class PointTrackApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PointTrack")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)
        
        # Couleurs professionnelles
        self.colors = {
            'bg': '#0f172a',
            'card': '#1e293b',
            'accent': '#3b82f6',
            'success': '#10b981',
            'error': '#ef4444',
            'warning': '#f59e0b',
            'text': '#f8fafc',
            'text_dim': '#94a3b8',
            'border': '#334155'
        }
        
        self.root.configure(bg=self.colors['bg'])
        
        self.ws_client = WebSocketClient(self)
        self.session_start = None
        self.elapsed_seconds = 0
        self.heartbeat_running = False
        self.current_view = "main"
        
        self.setup_ui()
        self.update_elapsed_time()
        self.root.after(2000, self.connect_websocket)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        # Container principal
        self.main_container = tk.Frame(self.root, bg=self.colors['bg'])
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Header
        self.create_header()
        
        # Content area
        self.content_frame = tk.Frame(self.main_container, bg=self.colors['bg'])
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Vue principale
        self.main_view = tk.Frame(self.content_frame, bg=self.colors['bg'])
        self.main_view.pack(fill=tk.BOTH, expand=True)
        
        # Vue paramètres
        self.settings_view = tk.Frame(self.content_frame, bg=self.colors['bg'])
        
        self.create_main_view()
        self.create_settings_view()
        self.show_view("main")

    def create_header(self):
        header = tk.Frame(self.main_container, bg=self.colors['card'], height=70)
        header.pack(fill=tk.X, padx=20, pady=(20, 10))
        header.pack_propagate(False)
        
        # Logo et titre
        left_frame = tk.Frame(header, bg=self.colors['card'])
        left_frame.pack(side=tk.LEFT, padx=20)
        
        tk.Label(left_frame, text="⚡", font=("Segoe UI", 28), 
                bg=self.colors['card'], fg=self.colors['accent']).pack(side=tk.LEFT)
        tk.Label(left_frame, text="PointTrack", font=("Segoe UI", 18, "bold"), 
                bg=self.colors['card'], fg=self.colors['text']).pack(side=tk.LEFT, padx=10)
        
        # Navigation
        nav_frame = tk.Frame(header, bg=self.colors['card'])
        nav_frame.pack(side=tk.RIGHT, padx=20)
        
        self.btn_main = tk.Button(nav_frame, text="🏠 Accueil", 
                                  command=lambda: self.show_view("main"),
                                  bg=self.colors['accent'], fg=self.colors['text'],
                                  font=("Segoe UI", 10), relief=tk.FLAT, 
                                  padx=15, pady=8, cursor="hand2")
        self.btn_main.pack(side=tk.LEFT, padx=5)
        
        self.btn_settings = tk.Button(nav_frame, text="⚙️ Paramètres", 
                                      command=lambda: self.show_view("settings"),
                                      bg=self.colors['border'], fg=self.colors['text'],
                                      font=("Segoe UI", 10), relief=tk.FLAT, 
                                      padx=15, pady=8, cursor="hand2")
        self.btn_settings.pack(side=tk.LEFT, padx=5)
        
        # Status indicator
        self.status_frame = tk.Frame(header, bg=self.colors['card'])
        self.status_frame.pack(side=tk.RIGHT, padx=20)
        
        self.status_dot = tk.Canvas(self.status_frame, width=12, height=12, 
                                    bg=self.colors['card'], highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=5)
        self.status_circle = self.status_dot.create_oval(2, 2, 10, 10, fill="#6b7280")
        
        self.status_text = tk.Label(self.status_frame, text="Déconnecté", 
                                   font=("Segoe UI", 9), bg=self.colors['card'], 
                                   fg=self.colors['text_dim'])
        self.status_text.pack(side=tk.LEFT)

    def create_main_view(self):
        # Info machine card
        info_card = self.create_card(self.main_view, "📋 Informations Machine")
        info_card.pack(fill=tk.X, pady=(0, 15))
        
        info_grid = tk.Frame(info_card, bg=self.colors['card'])
        info_grid.pack(fill=tk.X, padx=20, pady=15)
        
        machine_data = [
            ("ID Machine", self.obtenir_id_machine()),
            ("Nom", self.obtenir_nom_machine()),
            ("Adresse IP", self.obtenir_ip_locale()),
            ("Système", f"{platform.system()} {platform.release()}")
        ]
        
        for i, (label, value) in enumerate(machine_data):
            row = i // 2
            col = i % 2
            
            item_frame = tk.Frame(info_grid, bg=self.colors['card'])
            item_frame.grid(row=row, column=col, sticky="ew", padx=10, pady=8)
            info_grid.columnconfigure(col, weight=1)
            
            tk.Label(item_frame, text=label, font=("Segoe UI", 9), 
                    fg=self.colors['text_dim'], bg=self.colors['card'], 
                    anchor="w").pack(anchor="w")
            tk.Label(item_frame, text=value, font=("Segoe UI", 11, "bold"), 
                    fg=self.colors['text'], bg=self.colors['card'], 
                    anchor="w").pack(anchor="w")
        
        # Session card
        session_card = self.create_card(self.main_view, "⏱️ Session de Travail")
        session_card.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        session_content = tk.Frame(session_card, bg=self.colors['card'])
        session_content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        self.session_status = tk.Label(session_content, text="Aucune session active",
                                      font=("Segoe UI", 12), fg=self.colors['text_dim'],
                                      bg=self.colors['card'])
        self.session_status.pack(pady=(10, 5))
        
        self.elapsed_label = tk.Label(session_content, text="00:00:00",
                                     font=("Segoe UI", 48, "bold"), 
                                     fg=self.colors['accent'], bg=self.colors['card'])
        self.elapsed_label.pack(pady=10)
        
        self.hours_label = tk.Label(session_content, text="0.00 heures",
                                   font=("Segoe UI", 14), fg=self.colors['text_dim'],
                                   bg=self.colors['card'])
        self.hours_label.pack(pady=5)
        
        # Actions
        actions_frame = tk.Frame(session_content, bg=self.colors['card'])
        actions_frame.pack(pady=20)
        
        self.btn_allumage = tk.Button(actions_frame, text="🟢 Démarrer Session",
                                      command=lambda: self.envoyer_pointage('allumage'),
                                      bg=self.colors['success'], fg="white",
                                      font=("Segoe UI", 12, "bold"), relief=tk.FLAT,
                                      padx=30, pady=15, cursor="hand2",
                                      activebackground="#059669")
        
        self.btn_extinction = tk.Button(actions_frame, text="🔴 Terminer Session",
                                        command=lambda: self.envoyer_pointage('extinction'),
                                        bg=self.colors['error'], fg="white",
                                        font=("Segoe UI", 12, "bold"), relief=tk.FLAT,
                                        padx=30, pady=15, cursor="hand2",
                                        activebackground="#dc2626")
        
        # Notification area
        self.notification_frame = tk.Frame(self.main_view, bg=self.colors['card'], 
                                          height=0)
        self.notification_frame.pack(fill=tk.X)
        self.notification_label = tk.Label(self.notification_frame, text="",
                                          font=("Segoe UI", 10), bg=self.colors['card'],
                                          fg=self.colors['text'], pady=10)
        
        self.update_action_buttons()

    def create_settings_view(self):
        settings_card = self.create_card(self.settings_view, "⚙️ Configuration")
        settings_card.pack(fill=tk.BOTH, expand=True)
        
        content = tk.Frame(settings_card, bg=self.colors['card'])
        content.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)
        
        # URL Serveur
        tk.Label(content, text="URL du Serveur", font=("Segoe UI", 11, "bold"),
                fg=self.colors['text'], bg=self.colors['card'], anchor="w").pack(anchor="w", pady=(0, 5))
        
        url_frame = tk.Frame(content, bg=self.colors['bg'], highlightbackground=self.colors['border'],
                            highlightthickness=1)
        url_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.url_entry = tk.Entry(url_frame, font=("Segoe UI", 11), bg=self.colors['bg'],
                                 fg=self.colors['text'], relief=tk.FLAT, 
                                 insertbackground=self.colors['text'])
        self.url_entry.pack(fill=tk.X, padx=10, pady=10)
        self.url_entry.insert(0, self.charger_config().get('server_url', Config.SERVEUR_URL))
        
        # Boutons
        btn_frame = tk.Frame(content, bg=self.colors['card'])
        btn_frame.pack(fill=tk.X, pady=20)
        
        tk.Button(btn_frame, text="💾 Enregistrer",
                 command=self.save_settings,
                 bg=self.colors['success'], fg="white",
                 font=("Segoe UI", 11, "bold"), relief=tk.FLAT,
                 padx=25, pady=12, cursor="hand2").pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(btn_frame, text="🔄 Tester Connexion",
                 command=self.test_connection,
                 bg=self.colors['accent'], fg="white",
                 font=("Segoe UI", 11, "bold"), relief=tk.FLAT,
                 padx=25, pady=12, cursor="hand2").pack(side=tk.LEFT)
        
        # Info
        info_frame = tk.Frame(content, bg=self.colors['bg'], 
                             highlightbackground=self.colors['border'], highlightthickness=1)
        info_frame.pack(fill=tk.X, pady=20)
        
        tk.Label(info_frame, text="ℹ️ Les modifications seront appliquées après redémarrage",
                font=("Segoe UI", 9), fg=self.colors['text_dim'],
                bg=self.colors['bg']).pack(padx=15, pady=15)

    def create_card(self, parent, title):
        card = tk.Frame(parent, bg=self.colors['card'], 
                       highlightbackground=self.colors['border'], highlightthickness=1)
        
        title_frame = tk.Frame(card, bg=self.colors['card'])
        title_frame.pack(fill=tk.X, padx=20, pady=(15, 10))
        
        tk.Label(title_frame, text=title, font=("Segoe UI", 13, "bold"),
                fg=self.colors['text'], bg=self.colors['card']).pack(anchor="w")
        
        return card

    def show_view(self, view_name):
        self.current_view = view_name
        
        if view_name == "main":
            self.settings_view.pack_forget()
            self.main_view.pack(fill=tk.BOTH, expand=True)
            self.btn_main.config(bg=self.colors['accent'])
            self.btn_settings.config(bg=self.colors['border'])
        else:
            self.main_view.pack_forget()
            self.settings_view.pack(fill=tk.BOTH, expand=True)
            self.btn_settings.config(bg=self.colors['accent'])
            self.btn_main.config(bg=self.colors['border'])

    def update_action_buttons(self):
        if self.session_start:
            self.btn_allumage.pack_forget()
            self.btn_extinction.pack()
        else:
            self.btn_extinction.pack_forget()
            self.btn_allumage.pack()

    def show_notification(self, message, type="info"):
        colors = {
            "success": self.colors['success'],
            "error": self.colors['error'],
            "warning": self.colors['warning'],
            "info": self.colors['accent']
        }
        
        self.notification_label.config(text=message, fg=colors.get(type, self.colors['text']))
        self.notification_frame.config(bg=colors.get(type, self.colors['card']))
        self.notification_label.config(bg=colors.get(type, self.colors['card']))
        self.notification_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.root.after(4000, lambda: self.notification_frame.pack_forget())

    def update_ws_status(self, connected):
        if connected:
            self.status_dot.itemconfig(self.status_circle, fill=self.colors['success'])
            self.status_text.config(text="Connecté", fg=self.colors['success'])
        else:
            self.status_dot.itemconfig(self.status_circle, fill=self.colors['error'])
            self.status_text.config(text="Déconnecté", fg=self.colors['error'])

    def save_settings(self):
        new_url = self.url_entry.get().strip()
        if not new_url.startswith('http'):
            messagebox.showerror("Erreur", "L'URL doit commencer par http:// ou https://")
            return
        
        config = self.charger_config()
        config['server_url'] = new_url
        self.sauvegarder_config(config)
        Config.SERVEUR_URL = new_url
        
        self.show_notification("Configuration enregistrée", "success")
        messagebox.showinfo("Succès", "Redémarrez l'application pour appliquer les changements")

    def test_connection(self):
        url = self.url_entry.get().strip()
        self.show_notification("Test de connexion...", "info")
        
        def test():
            try:
                test_client = socketio.Client()
                test_client.connect(url, wait_timeout=5)
                test_client.disconnect()
                self.root.after(0, lambda: self.show_notification("Connexion réussie !", "success"))
            except Exception as e:
                self.root.after(0, lambda: self.show_notification(f"Échec: {str(e)}", "error"))
        
        threading.Thread(target=test, daemon=True).start()

    def connect_websocket(self):
        threading.Thread(target=lambda: self.ws_client.connect(Config.SERVEUR_URL) 
                        and self.start_heartbeat(), daemon=True).start()

    def start_heartbeat(self):
        if self.heartbeat_running:
            return
        self.heartbeat_running = True
        
        def beat():
            while self.heartbeat_running:
                if self.ws_client.connected:
                    self.ws_client.send_heartbeat()
                time.sleep(Config.HEARTBEAT_INTERVAL)
        
        threading.Thread(target=beat, daemon=True).start()

    def envoyer_pointage(self, type_pointage):
        def send():
            try:
                duration = None
                if type_pointage == 'extinction' and self.session_start:
                    duration = int((datetime.now() - self.session_start).total_seconds())
                
                self.ws_client.send_pointage(type_pointage, duration)
                
                if type_pointage == 'allumage':
                    self.session_start = datetime.now()
                    self.elapsed_seconds = 0
                    self.root.after(0, lambda: self.session_status.config(
                        text="Session active", fg=self.colors['success']))
                else:
                    self.session_start = None
                    self.elapsed_seconds = 0
                    self.root.after(0, lambda: self.session_status.config(
                        text="Aucune session active", fg=self.colors['text_dim']))
                    self.root.after(0, lambda: self.elapsed_label.config(text="00:00:00"))
                    self.root.after(0, lambda: self.hours_label.config(text="0.00 heures"))
                
                self.root.after(0, self.update_action_buttons)
                
            except Exception as e:
                self.root.after(0, lambda: self.show_notification(str(e), "error"))
        
        threading.Thread(target=send, daemon=True).start()

    def update_elapsed_time(self):
        if self.session_start:
            self.elapsed_seconds = int((datetime.now() - self.session_start).total_seconds())
            h, s = divmod(self.elapsed_seconds, 3600)
            m, s = divmod(s, 60)
            self.elapsed_label.config(text=f"{h:02d}:{m:02d}:{s:02d}")
            self.hours_label.config(text=f"{self.elapsed_seconds / 3600:.2f} heures")
        self.root.after(1000, self.update_elapsed_time)

    def on_closing(self):
        if self.session_start:
            rep = messagebox.askyesnocancel("Session active", 
                                           "Voulez-vous terminer la session ?")
            if rep is None:
                return
            if rep:
                try:
                    dur = int((datetime.now() - self.session_start).total_seconds())
                    self.ws_client.send_pointage('extinction', dur)
                    time.sleep(0.5)
                except:
                    pass
        
        self.heartbeat_running = False
        self.ws_client.disconnect()
        self.root.destroy()

    # Méthodes utilitaires
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
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except:
            return "127.0.0.1"

    def obtenir_info_systeme(self):
        return {'system': platform.system(), 'release': platform.release()}

    def charger_config(self):
        try:
            if Config.CONFIG_FILE.exists():
                with open(Config.CONFIG_FILE) as f:
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
        except:
            pass

# ==================== MAIN ====================

def main():
    root = tk.Tk()
    PointTrackApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()