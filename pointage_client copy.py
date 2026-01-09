#!/usr/bin/env python3
"""
Client Pointage WebSocket – Version Pro
Couleurs inspirées de l’image, rectangle centré, sans logs
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
    CONFIG_DIR = Path.home() / '.pointage_client'
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
            self.register_machine()

        @self.sio.on('disconnect')
        def on_disconnect():
            self.connected = False
            self.app.update_ws_status(False)

        @self.sio.on('pointage_confirmed')
        def on_pointage_confirmed(data):
            t = data.get('type')
            if t == 'extinction' and 'sessionDuration' in data:
                d = data['sessionDuration']
                self.app.update_session_duration(d['formatted'], d['hours'])

    def connect(self, url):
        try:
            self.sio.connect(url, wait_timeout=10)
            return True
        except Exception as e:
            self.app.set_status(f"❌ Erreur: {e}")
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
            raise Exception("WebSocket non connecté")
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

# ==================== APPLICATION TKINTER ====================

class PointageClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PointTrack")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        self.root.configure(bg="#e0e7ff")

        self.ws_client = WebSocketClient(self)
        self.session_start = None
        self.elapsed_seconds = 0
        self.heartbeat_running = False

        self.setup_ui()
        self.update_elapsed_time()
        self.root.after(2000, self.connect_websocket)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ---------- UI ----------
    def setup_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#1e3a8a", height=80)
        header.pack(fill=tk.X)
        tk.Label(header, text="PointTrack", font=("Inter", 20, "bold"), bg="#1e3a8a", fg="white").pack(pady=25)

        # Centrage du rectangle principal
        main_frame = tk.Frame(self.root, bg="#ffffff", relief=tk.FLAT, bd=0)
        main_frame.place(relx=0.5, rely=0.5, anchor="center", width=360, height=300)

        # Machine
        info = tk.Frame(main_frame, bg="white")
        info.pack(fill=tk.X, pady=(12, 0))
        tk.Label(info, text=f"Machine: {self.obtenir_id_machine()}", font=("Inter", 11), fg="#1f2937", bg="white").pack(anchor="w", padx=12)
        tk.Label(info, text=f"IP: {self.obtenir_ip_locale()}", font=("Inter", 11), fg="#1f2937", bg="white").pack(anchor="w", padx=12)

        # Session
        session = tk.Frame(main_frame, bg="white")
        session.pack(fill=tk.X, pady=12)
        self.session_label = tk.Label(session, text="Aucune session active", font=("Inter", 12), fg="#6b7280", bg="white")
        self.session_label.pack()
        self.elapsed_label = tk.Label(session, text="00:00:00", font=("Inter", 24, "bold"), fg="#1e3a8a", bg="white")
        self.elapsed_label.pack(pady=6)
        self.hours_label = tk.Label(session, text="0.00 heures", font=("Inter", 11), fg="#9ca3af", bg="white")
        self.hours_label.pack()

        # WebSocket
        ws_frame = tk.Frame(main_frame, bg="white")
        ws_frame.pack(fill=tk.X, pady=12)
        self.ws_indicator = tk.Canvas(ws_frame, width=16, height=16, bg="white", highlightthickness=0)
        self.ws_indicator.pack(side=tk.LEFT, padx=12)
        self.ws_circle = self.ws_indicator.create_oval(2, 2, 14, 14, fill="gray")
        self.ws_label = tk.Label(ws_frame, text="Non connecté", font=("Inter", 10), fg="#6b7280", bg="white")
        self.ws_label.pack(side=tk.LEFT)

        # Boutons
        btn_frame = tk.Frame(main_frame, bg="white")
        btn_frame.pack(pady=12)
        self.btn_allumage = tk.Button(btn_frame, text="🟢 Allumage", command=lambda: self.envoyer_pointage('allumage'), bg="#10b981", fg="white", font=("Inter", 11, "bold"), relief=tk.FLAT, padx=20, pady=8)
        self.btn_extinction = tk.Button(btn_frame, text="🔴 Extinction", command=lambda: self.envoyer_pointage('extinction'), bg="#ef4444", fg="white", font=("Inter", 11, "bold"), relief=tk.FLAT, padx=20, pady=8)
        self.update_button_states()

    # ---------- Méthodes utilitaires ----------
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

    def set_status(self, text):
        self.ws_label.config(text=text)

    def update_ws_status(self, connected):
        color = "#10b981" if connected else "#ef4444"
        text = "Connecté" if connected else "Non connecté"
        self.ws_indicator.itemconfig(self.ws_circle, fill=color)
        self.ws_label.config(text=text, fg=color)

    def update_session_duration(self, formatted, hours):
        self.hours_label.config(text=f"{hours} heures")

    def update_button_states(self):
        if self.session_start:
            self.btn_allumage.pack_forget()
            self.btn_extinction.pack(side=tk.LEFT, padx=(0, 10))
        else:
            self.btn_extinction.pack_forget()
            self.btn_allumage.pack(side=tk.LEFT, padx=(0, 10))

    # ---------- WebSocket ----------
    def connect_websocket(self):
        threading.Thread(target=lambda: self.ws_client.connect(Config.SERVEUR_URL) and self.start_heartbeat(), daemon=True).start()

    def reconnect_websocket(self):
        self.set_status("🔄 Reconnexion...")
        self.ws_client.disconnect()
        time.sleep(1)
        self.connect_websocket()

    def start_heartbeat(self):
        if self.heartbeat_running:
            return
        self.heartbeat_running = True

        def _beat():
            while self.heartbeat_running:
                if self.ws_client.connected:
                    self.ws_client.send_heartbeat()
                time.sleep(Config.HEARTBEAT_INTERVAL)

        threading.Thread(target=_beat, daemon=True).start()

    def stop_heartbeat(self):
        self.heartbeat_running = False

    # ---------- Actions ----------
    def envoyer_pointage(self, type_pointage):
        def _send():
            self.root.after(0, lambda: self.btn_allumage.config(state=tk.DISABLED))
            self.root.after(0, lambda: self.btn_extinction.config(state=tk.DISABLED))
            try:
                duration = None
                if type_pointage == 'extinction' and self.session_start:
                    duration = int((datetime.now() - self.session_start).total_seconds())
                self.ws_client.send_pointage(type_pointage, duration)

                if type_pointage == 'allumage':
                    self.session_start = datetime.now()
                    self.elapsed_seconds = 0
                    self.session_label.config(text="Session active", fg="#10b981")
                else:
                    self.session_start = None
                    self.elapsed_seconds = 0
                    self.session_label.config(text="Aucune session active", fg="#6b7280")
                    self.elapsed_label.config(text="00:00:00")
                    self.hours_label.config(text="0.00 heures")
                self.update_button_states()
                messagebox.showinfo("Succès", f"Pointage {type_pointage} envoyé !")
            except Exception as e:
                messagebox.showerror("Erreur", str(e))
            finally:
                self.root.after(0, lambda: self.btn_allumage.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.btn_extinction.config(state=tk.NORMAL))

        threading.Thread(target=_send, daemon=True).start()

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
            rep = messagebox.askyesnocancel("Session active", "Envoyer un pointage d’extinction ?")
            if rep is None:
                return
            if rep:
                try:
                    dur = int((datetime.now() - self.session_start).total_seconds())
                    self.ws_client.send_pointage('extinction', dur)
                    time.sleep(0.5)
                except:
                    pass
        self.stop_heartbeat()
        self.ws_client.disconnect()
        self.root.destroy()

# ==================== MAIN ====================

def main():
    root = tk.Tk()
    PointageClientApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()