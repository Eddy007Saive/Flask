#!/usr/bin/env python3
"""
Serveur de Pointage Unifié
- API REST pour le frontend React (dashboard web)
- WebSocket pour les clients de pointage (communication temps réel)
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime, timedelta
import sqlite3
import os

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Stockage des clients connectés via WebSocket
connected_clients = {}  # {machine_id: {sid: session_id, info: {...}}}

# ==================== BASE DE DONNÉES ====================

def init_db():
    conn = sqlite3.connect('pointages.db')
    c = conn.cursor()
    
    # Table des machines
    c.execute('''
        CREATE TABLE IF NOT EXISTS machines (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ip TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'inactive',
            last_pointage TIMESTAMP,
            last_heartbeat TIMESTAMP,
            email TEXT,
            total_hours_today REAL DEFAULT 0,
            connected INTEGER DEFAULT 0
        )
    ''')
    
    # Table des pointages
    c.execute('''
        CREATE TABLE IF NOT EXISTS pointages (
            id TEXT PRIMARY KEY,
            machine_id TEXT NOT NULL,
            machine_name TEXT NOT NULL,
            type TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            ip TEXT NOT NULL,
            session_duration_seconds INTEGER,
            session_duration_hours REAL,
            FOREIGN KEY (machine_id) REFERENCES machines(id)
        )
    ''')
    
    # Table des alertes
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            machine_name TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            resolved INTEGER DEFAULT 0,
            FOREIGN KEY (machine_id) REFERENCES machines(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    
    # Vérifier et ajouter les colonnes manquantes (migration)
    migrate_db_columns()

def migrate_db_columns():
    """Ajoute les colonnes manquantes dans une base de données existante"""
    conn = sqlite3.connect('pointages.db')
    c = conn.cursor()
    
    print("🔧 Vérification de la structure de la base de données...")
    
    try:
        # Vérifier les colonnes de 'machines'
        c.execute("PRAGMA table_info(machines)")
        machine_columns = [col[1] for col in c.fetchall()]
        
        if 'last_heartbeat' not in machine_columns:
            print("   ➕ Ajout de la colonne 'last_heartbeat' à 'machines'")
            c.execute('ALTER TABLE machines ADD COLUMN last_heartbeat TIMESTAMP')
        
        if 'connected' not in machine_columns:
            print("   ➕ Ajout de la colonne 'connected' à 'machines'")
            c.execute('ALTER TABLE machines ADD COLUMN connected INTEGER DEFAULT 0')
        
        if 'total_hours_today' not in machine_columns:
            print("   ➕ Ajout de la colonne 'total_hours_today' à 'machines'")
            c.execute('ALTER TABLE machines ADD COLUMN total_hours_today REAL DEFAULT 0')
        
        # Vérifier les colonnes de 'pointages'
        c.execute("PRAGMA table_info(pointages)")
        pointage_columns = [col[1] for col in c.fetchall()]
        
        if 'session_duration_seconds' not in pointage_columns:
            print("   ➕ Ajout de la colonne 'session_duration_seconds' à 'pointages'")
            c.execute('ALTER TABLE pointages ADD COLUMN session_duration_seconds INTEGER')
        
        if 'session_duration_hours' not in pointage_columns:
            print("   ➕ Ajout de la colonne 'session_duration_hours' à 'pointages'")
            c.execute('ALTER TABLE pointages ADD COLUMN session_duration_hours REAL')
        
        # S'assurer que total_hours_today n'est pas NULL
        c.execute('UPDATE machines SET total_hours_today = 0 WHERE total_hours_today IS NULL')
        
        conn.commit()
        print("✅ Structure de la base de données vérifiée")
        
    except Exception as e:
        print(f"❌ Erreur lors de la migration: {e}")
    finally:
        conn.close()

def get_db():
    conn = sqlite3.connect('pointages.db')
    conn.row_factory = sqlite3.Row
    return conn

# ==================== WEBSOCKET EVENTS (Clients de pointage) ====================

@socketio.on('connect')
def handle_connect():
    """Un client se connecte"""
    print(f"🔌 Client connecté: {request.sid}")
    emit('connected', {'message': 'Connexion établie', 'sid': request.sid})

@socketio.on('disconnect')
def handle_disconnect():
    """Un client se déconnecte"""
    print(f"❌ Client déconnecté: {request.sid}")
    
    # Trouver et mettre à jour la machine
    machine_id = None
    for mid, info in connected_clients.items():
        if info.get('sid') == request.sid:
            machine_id = mid
            break
    
    if machine_id:
        print(f"   Machine: {machine_id}")
        del connected_clients[machine_id]
        
        # Mettre à jour la base de données
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            UPDATE machines 
            SET connected = 0, status = 'inactive'
            WHERE id = ?
        ''', (machine_id,))
        conn.commit()
        conn.close()
        
        # Notifier tous les dashboards web
        socketio.emit('machine_disconnected', {
            'machineId': machine_id,
            'timestamp': datetime.now().isoformat()
        }, room='dashboard')

@socketio.on('register_machine')
def handle_register_machine(data):
    """Enregistrement d'une machine cliente via WebSocket"""
    machine_id = data.get('machineId')
    machine_name = data.get('machineName')
    machine_ip = data.get('machineIp', request.remote_addr)
    system_info = data.get('systemInfo', {})
    
    if not machine_id:
        emit('error', {'message': 'machineId requis'})
        return
    
    print(f"📝 Enregistrement machine WebSocket: {machine_id} ({machine_name})")
    
    # Stocker dans le dictionnaire des clients connectés
    connected_clients[machine_id] = {
        'sid': request.sid,
        'machine_name': machine_name,
        'machine_ip': machine_ip,
        'system_info': system_info,
        'connected_at': datetime.now().isoformat()
    }
    
    # Mettre à jour la base de données
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT * FROM machines WHERE id = ?', (machine_id,))
    machine = c.fetchone()
    
    is_new_machine = machine is None
    
    if not machine:
        # Créer la machine
        c.execute('''
            INSERT INTO machines (id, name, ip, status, last_heartbeat, connected)
            VALUES (?, ?, ?, 'active', ?, 1)
        ''', (machine_id, machine_name, machine_ip, datetime.now().isoformat()))
        print(f"   🆕 Nouvelle machine créée")
    else:
        # Mettre à jour
        c.execute('''
            UPDATE machines 
            SET connected = 1, status = 'active', last_heartbeat = ?, ip = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), machine_ip, machine_id))
        print(f"   ♻️  Machine existante mise à jour")
    
    conn.commit()
    conn.close()
    
    # Rejoindre une room pour cette machine
    join_room(machine_id)
    
    # Confirmer l'enregistrement au client
    emit('registered', {
        'machineId': machine_id,
        'message': 'Machine enregistrée avec succès',
        'timestamp': datetime.now().isoformat()
    })
    
    # Notifier tous les dashboards web
    socketio.emit('machine_connected', {
        'machineId': machine_id,
        'machineName': machine_name,
        'machineIp': machine_ip,
        'timestamp': datetime.now().isoformat()
    }, room='dashboard')

@socketio.on('heartbeat')
def handle_heartbeat(data):
    """Heartbeat régulier du client"""
    machine_id = data.get('machineId')
    
    if not machine_id:
        return
    
    # Mettre à jour le dernier heartbeat
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        UPDATE machines 
        SET last_heartbeat = ?
        WHERE id = ?
    ''', (datetime.now().isoformat(), machine_id))
    conn.commit()
    conn.close()
    
    # Répondre au heartbeat
    emit('heartbeat_ack', {'timestamp': datetime.now().isoformat()})

@socketio.on('pointage')
def handle_pointage_ws(data):
    """Réception d'un pointage via WebSocket"""
    machine_id = data.get('machineId')
    machine_name = data.get('machineName')
    machine_ip = data.get('machineIp', request.remote_addr)
    pointage_type = data.get('type', 'allumage')
    session_duration = data.get('sessionDuration')  # Peut être None
    
    if not machine_id:
        emit('error', {'message': 'machineId requis'})
        return
    
    print(f"📊 Pointage WebSocket {pointage_type}: {machine_id}")
    
    conn = get_db()
    c = conn.cursor()
    
    # Créer le pointage
    pointage_id = f"p-{datetime.now().timestamp()}"
    timestamp = datetime.now().isoformat()
    
    # Extraire les données de durée si présentes
    duration_seconds = None
    duration_hours = None
    if session_duration:
        duration_seconds = session_duration.get('seconds')
        duration_hours = session_duration.get('hours')
        print(f"   ⏱️  Durée session: {session_duration.get('formatted')} ({duration_hours:.2f}h)")
    
    c.execute('''
        INSERT INTO pointages (id, machine_id, machine_name, type, timestamp, ip, 
                              session_duration_seconds, session_duration_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (pointage_id, machine_id, machine_name or machine_id, pointage_type, 
          timestamp, machine_ip, duration_seconds, duration_hours))
    
    # Mettre à jour le statut et les heures de la machine
    new_status = 'active' if pointage_type == 'allumage' else 'inactive'
    
    # Si c'est une extinction avec durée, mettre à jour total_hours_today
    if pointage_type == 'extinction' and duration_hours:
        c.execute('''
            UPDATE machines 
            SET status = ?, last_pointage = ?, total_hours_today = total_hours_today + ?
            WHERE id = ?
        ''', (new_status, timestamp, duration_hours, machine_id))
    else:
        c.execute('''
            UPDATE machines 
            SET status = ?, last_pointage = ? 
            WHERE id = ?
        ''', (new_status, timestamp, machine_id))
    
    conn.commit()
    conn.close()
    
    # Confirmer au client (avec la durée si présente)
    confirmation_data = {
        'id': pointage_id,
        'machineId': machine_id,
        'type': pointage_type,
        'timestamp': timestamp
    }
    if session_duration:
        confirmation_data['sessionDuration'] = session_duration
    
    emit('pointage_confirmed', confirmation_data)
    
    # Notifier tous les dashboards web en temps réel
    notification_data = {
        'id': pointage_id,
        'machineId': machine_id,
        'machineName': machine_name or machine_id,
        'type': pointage_type,
        'timestamp': timestamp
    }
    if session_duration:
        notification_data['sessionDuration'] = session_duration
    
    socketio.emit('new_pointage', notification_data, room='dashboard')

@socketio.on('get_status')
def handle_get_status(data):
    """Le client demande son statut"""
    machine_id = data.get('machineId')
    
    if not machine_id:
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM machines WHERE id = ?', (machine_id,))
    machine = c.fetchone()
    conn.close()
    
    if machine:
        emit('status_update', {
            'machineId': machine['id'],
            'status': machine['status'],
            'lastPointage': machine['last_pointage'],
            'totalHoursToday': machine['total_hours_today']
        })

# ==================== WEBSOCKET EVENTS (Dashboard Web) ====================

@socketio.on('dashboard_connected')
def handle_dashboard_connected():
    """Un dashboard web se connecte"""
    print(f"🖥️  Dashboard connecté: {request.sid}")
    join_room('dashboard')
    
    # Envoyer la liste des machines connectées
    emit('connected_machines', {
        'machines': list(connected_clients.keys()),
        'count': len(connected_clients)
    })

# ==================== API REST (Frontend React) ====================

@app.route('/api/machines', methods=['GET'])
def get_machines():
    """Récupère la liste de toutes les machines"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM machines')
        machines = c.fetchall()
        conn.close()
        
        result = []
        for m in machines:
            # Gérer last_heartbeat qui peut ne pas exister dans les anciennes DB
            last_heartbeat = None
            try:
                last_heartbeat = m['last_heartbeat']
            except (KeyError, IndexError):
                pass
            
            # Gérer connected qui peut ne pas exister dans les anciennes DB
            connected = 0
            try:
                connected = m['connected']
            except (KeyError, IndexError):
                pass
            
            result.append({
                'id': m['id'],
                'name': m['name'],
                'ip': m['ip'],
                'status': m['status'],
                'lastPointage': m['last_pointage'],
                'lastHeartbeat': last_heartbeat,
                'email': m['email'],
                'totalHoursToday': m['total_hours_today'],
                'connected': bool(connected),
                'websocketConnected': m['id'] in connected_clients
            })
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/machines/<machine_id>', methods=['GET'])
def get_machine(machine_id):
    """Récupère une machine spécifique"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM machines WHERE id = ?', (machine_id,))
        machine = c.fetchone()
        conn.close()
        
        if not machine:
            return jsonify({'error': 'Machine non trouvée'}), 404
        
        # Gérer last_heartbeat qui peut ne pas exister
        last_heartbeat = None
        try:
            last_heartbeat = machine['last_heartbeat']
        except (KeyError, IndexError):
            pass
        
        # Gérer connected qui peut ne pas exister
        connected = 0
        try:
            connected = machine['connected']
        except (KeyError, IndexError):
            pass
        
        return jsonify({
            'id': machine['id'],
            'name': machine['name'],
            'ip': machine['ip'],
            'status': machine['status'],
            'lastPointage': machine['last_pointage'],
            'lastHeartbeat': last_heartbeat,
            'email': machine['email'],
            'totalHoursToday': machine['total_hours_today'],
            'connected': bool(connected),
            'websocketConnected': machine_id in connected_clients
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/machines', methods=['POST'])
def create_machine():
    """Crée une nouvelle machine"""
    try:
        data = request.get_json()
        
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            INSERT INTO machines (id, name, ip, email, status)
            VALUES (?, ?, ?, ?, 'inactive')
        ''', (data['id'], data['name'], data['ip'], data.get('email')))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Machine créée avec succès'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/machines/<machine_id>', methods=['PUT'])
def update_machine(machine_id):
    """Met à jour une machine"""
    try:
        data = request.get_json()
        
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            UPDATE machines 
            SET name = ?, ip = ?, email = ?
            WHERE id = ?
        ''', (data['name'], data['ip'], data.get('email'), machine_id))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Machine mise à jour'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/machines/<machine_id>', methods=['DELETE'])
def delete_machine(machine_id):
    """Supprime une machine"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM machines WHERE id = ?', (machine_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Machine supprimée'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/machines/<machine_id>/command', methods=['POST'])
def send_machine_command(machine_id):
    """Envoie une commande à une machine via WebSocket"""
    try:
        data = request.get_json()
        command = data.get('command')
        
        if not command:
            return jsonify({'error': 'command requis'}), 400
        
        if machine_id not in connected_clients:
            return jsonify({'error': 'Machine non connectée via WebSocket'}), 404
        
        # Envoyer via WebSocket
        socketio.emit('command', {
            'command': command,
            'data': data.get('data', {}),
            'timestamp': datetime.now().isoformat()
        }, room=machine_id)
        
        return jsonify({
            'message': 'Commande envoyée',
            'machineId': machine_id,
            'command': command
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== ROUTES POINTAGES ====================

@app.route('/api/pointages', methods=['GET'])
def get_pointages():
    """Récupère tous les pointages avec filtres optionnels"""
    try:
        machine_id = request.args.get('machineId')
        start_date = request.args.get('startDate')
        end_date = request.args.get('endDate')
        limit = request.args.get('limit', 100)
        
        conn = get_db()
        c = conn.cursor()
        
        query = 'SELECT * FROM pointages WHERE 1=1'
        params = []
        
        if machine_id:
            query += ' AND machine_id = ?'
            params.append(machine_id)
        
        if start_date:
            query += ' AND timestamp >= ?'
            params.append(start_date)
        
        if end_date:
            query += ' AND timestamp <= ?'
            params.append(end_date)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        c.execute(query, params)
        pointages = c.fetchall()
        conn.close()
        
        result = []
        for p in pointages:
            pointage_dict = {
                'id': p['id'],
                'machineId': p['machine_id'],
                'machineName': p['machine_name'],
                'type': p['type'],
                'timestamp': p['timestamp'],
                'ip': p['ip']
            }
            
            # Ajouter la durée si présente
            try:
                if p['session_duration_seconds']:
                    pointage_dict['sessionDuration'] = {
                        'seconds': p['session_duration_seconds'],
                        'hours': p['session_duration_hours']
                    }
            except (KeyError, IndexError):
                pass
            
            result.append(pointage_dict)
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pointages', methods=['POST'])
def create_pointage():
    """Enregistre un nouveau pointage (fallback HTTP si pas de WebSocket)"""
    try:
        data = request.get_json()
        machine_id = data.get('machineId')
        machine_name = data.get('machineName')
        machine_ip = data.get('machineIp') or request.remote_addr
        pointage_type = data.get('type', 'allumage')
        
        if not machine_id:
            return jsonify({'error': 'machineId requis'}), 400
        
        print(f"📊 Pointage HTTP {pointage_type}: {machine_id}")
        
        conn = get_db()
        c = conn.cursor()
        
        # Vérifier si la machine existe
        c.execute('SELECT * FROM machines WHERE id = ?', (machine_id,))
        machine = c.fetchone()
        
        # Si la machine n'existe pas, la créer automatiquement
        if not machine:
            if not machine_name:
                machine_name = f"Machine-{machine_id}"
            
            print(f"🆕 Nouvelle machine détectée : {machine_name} ({machine_ip})")
            
            c.execute('''
                INSERT INTO machines (id, name, ip, status, last_pointage)
                VALUES (?, ?, ?, 'inactive', ?)
            ''', (machine_id, machine_name, machine_ip, datetime.now().isoformat()))
            
            c.execute('SELECT * FROM machines WHERE id = ?', (machine_id,))
            machine = c.fetchone()
        
        # Créer le pointage
        pointage_id = f"p-{datetime.now().timestamp()}"
        timestamp = datetime.now().isoformat()
        
        c.execute('''
            INSERT INTO pointages (id, machine_id, machine_name, type, timestamp, ip)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (pointage_id, machine_id, machine['name'], pointage_type, timestamp, machine['ip']))
        
        # Mettre à jour le statut de la machine
        new_status = 'active' if pointage_type == 'allumage' else 'inactive'
        c.execute('''
            UPDATE machines 
            SET status = ?, last_pointage = ? 
            WHERE id = ?
        ''', (new_status, timestamp, machine_id))
        
        conn.commit()
        conn.close()
        
        # Notifier les dashboards web en temps réel
        socketio.emit('new_pointage', {
            'id': pointage_id,
            'machineId': machine_id,
            'machineName': machine['name'],
            'type': pointage_type,
            'timestamp': timestamp
        }, room='dashboard')
        
        return jsonify({
            'message': 'Pointage enregistré',
            'id': pointage_id,
            'machineId': machine_id,
            'machineName': machine['name'],
            'type': pointage_type,
            'timestamp': timestamp,
            'isNewMachine': machine is None
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== ROUTES ALERTES ====================

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Récupère toutes les alertes"""
    try:
        resolved = request.args.get('resolved')
        
        conn = get_db()
        c = conn.cursor()
        
        query = 'SELECT * FROM alerts WHERE 1=1'
        params = []
        
        if resolved is not None:
            query += ' AND resolved = ?'
            params.append(1 if resolved == 'true' else 0)
        
        query += ' ORDER BY timestamp DESC'
        
        c.execute(query, params)
        alerts = c.fetchall()
        conn.close()
        
        result = []
        for a in alerts:
            result.append({
                'id': a['id'],
                'type': a['type'],
                'machineId': a['machine_id'],
                'machineName': a['machine_name'],
                'message': a['message'],
                'timestamp': a['timestamp'],
                'resolved': bool(a['resolved'])
            })
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts/<alert_id>/resolve', methods=['PUT'])
def resolve_alert(alert_id):
    """Marque une alerte comme résolue"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE alerts SET resolved = 1 WHERE id = ?', (alert_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Alerte résolue'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== ROUTES STATISTIQUES ====================

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """Récupère les statistiques globales"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Total machines
        c.execute('SELECT COUNT(*) as total FROM machines')
        result = c.fetchone()
        total_machines = result['total'] if result else 0
        
        # Machines actives
        c.execute('SELECT COUNT(*) as active FROM machines WHERE status = "active"')
        result = c.fetchone()
        active_machines = result['active'] if result else 0
        
        # Machines connectées via WebSocket
        c.execute('SELECT COUNT(*) as connected FROM machines WHERE connected = 1')
        result = c.fetchone()
        connected_machines = result['connected'] if result else 0
        
        # Machines inactives
        c.execute('SELECT COUNT(*) as inactive FROM machines WHERE status = "inactive"')
        result = c.fetchone()
        inactive_machines = result['inactive'] if result else 0
        
        # Total heures aujourd'hui
        c.execute('SELECT SUM(total_hours_today) as total FROM machines')
        result = c.fetchone()
        total_hours_today = result['total'] if result and result['total'] else 0
        
        # Pointages aujourd'hui
        today = datetime.now().date().isoformat()
        c.execute('SELECT COUNT(*) as count FROM pointages WHERE DATE(timestamp) = ?', (today,))
        result = c.fetchone()
        pointages_today = result['count'] if result else 0
        
        conn.close()
        
        return jsonify({
            'totalMachines': total_machines,
            'activeMachines': active_machines,
            'connectedMachines': connected_machines,
            'websocketClients': len(connected_clients),
            'inactiveMachines': inactive_machines,
            'totalHoursToday': round(total_hours_today, 2),
            'averageHoursPerMachine': round(total_hours_today / total_machines, 2) if total_machines > 0 else 0,
            'pointagesToday': pointages_today
        }), 200
        
    except Exception as e:
        app.logger.error(f"Erreur dans get_statistics: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==================== ROUTES RAPPORTS ====================

@app.route('/api/reports', methods=['GET'])
def get_reports():
    """Génère des rapports pour toutes les machines"""
    try:
        days = int(request.args.get('days', 7))
        
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM machines')
        machines = c.fetchall()
        
        reports = []
        for machine in machines:
            machine_id = machine['id']
            
            # Récupérer les pointages des X derniers jours
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            c.execute('''
                SELECT DATE(timestamp) as date, type
                FROM pointages
                WHERE machine_id = ? AND timestamp >= ?
                ORDER BY timestamp
            ''', (machine_id, start_date))
            pointages = c.fetchall()
            
            # Calculer les heures par jour
            daily_details = {}
            for i in range(days):
                date = (datetime.now() - timedelta(days=i)).date().isoformat()
                daily_details[date] = {'hoursWorked': 0, 'pointages': []}
            
            # Calculer les heures travaillées (simplification)
            current_allumage = None
            for p in pointages:
                date = p['date']
                if date in daily_details:
                    if p['type'] == 'allumage':
                        current_allumage = p
                    elif p['type'] == 'extinction' and current_allumage:
                        daily_details[date]['hoursWorked'] += 8
                        current_allumage = None
            
            total_hours = sum(d['hoursWorked'] for d in daily_details.values())
            days_worked = sum(1 for d in daily_details.values() if d['hoursWorked'] > 0)
            
            reports.append({
                'machineId': machine_id,
                'machineName': machine['name'],
                'daysWorked': days_worked,
                'totalHours': round(total_hours, 1),
                'averageHoursPerDay': round(total_hours / days, 1) if days > 0 else 0,
                'dailyDetails': [
                    {
                        'date': date,
                        'hoursWorked': details['hoursWorked'],
                        'pointages': details['pointages']
                    }
                    for date, details in sorted(daily_details.items(), reverse=True)
                ]
            })
        
        conn.close()
        return jsonify(reports), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/<machine_id>', methods=['GET'])
def get_machine_report(machine_id):
    """Génère un rapport détaillé pour une machine spécifique"""
    try:
        days = int(request.args.get('days', 30))
        
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM machines WHERE id = ?', (machine_id,))
        machine = c.fetchone()
        
        if not machine:
            return jsonify({'error': 'Machine non trouvée'}), 404
        
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        c.execute('''
            SELECT *
            FROM pointages
            WHERE machine_id = ? AND timestamp >= ?
            ORDER BY timestamp DESC
        ''', (machine_id, start_date))
        pointages = c.fetchall()
        
        conn.close()
        
        pointages_list = []
        for p in pointages:
            pointages_list.append({
                'id': p['id'],
                'type': p['type'],
                'timestamp': p['timestamp']
            })
        
        return jsonify({
            'machineId': machine_id,
            'machineName': machine['name'],
            'pointages': pointages_list,
            'totalPointages': len(pointages_list)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== ROUTES GRAPHIQUES ====================

@app.route('/api/chart-data', methods=['GET'])
def get_chart_data():
    """Génère les données pour les graphiques d'allumages/extinctions"""
    try:
        date = request.args.get('date', datetime.now().date().isoformat())
        
        conn = get_db()
        c = conn.cursor()
        
        c.execute('''
            SELECT 
                strftime('%H:00', timestamp) as time,
                SUM(CASE WHEN type = 'allumage' THEN 1 ELSE 0 END) as allumages,
                SUM(CASE WHEN type = 'extinction' THEN 1 ELSE 0 END) as extinctions
            FROM pointages
            WHERE DATE(timestamp) = ?
            GROUP BY strftime('%H:00', timestamp)
            ORDER BY time
        ''', (date,))
        
        data = c.fetchall()
        conn.close()
        
        result = []
        for row in data:
            result.append({
                'time': row['time'],
                'allumages': row['allumages'],
                'extinctions': row['extinctions']
            })
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== TÂCHES AUTOMATIQUES ====================

@app.route('/api/check-alerts', methods=['POST'])
def check_alerts():
    """Vérifie et crée des alertes pour les machines inactives"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        threshold_24h = (datetime.now() - timedelta(hours=24)).isoformat()
        threshold_72h = (datetime.now() - timedelta(hours=72)).isoformat()
        
        c.execute('''
            SELECT * FROM machines 
            WHERE last_pointage < ? OR last_pointage IS NULL
        ''', (threshold_24h,))
        
        inactive_machines = c.fetchall()
        alerts_created = 0
        
        for machine in inactive_machines:
            last_pointage = machine['last_pointage']
            
            if not last_pointage or last_pointage < threshold_72h:
                alert_type = 'inactive'
                message = f"Machine inactive depuis plus de 72h"
            else:
                alert_type = 'warning'
                message = f"Machine inactive depuis plus de 24h"
            
            c.execute('''
                SELECT * FROM alerts 
                WHERE machine_id = ? AND resolved = 0 AND type = ?
            ''', (machine['id'], alert_type))
            
            existing_alert = c.fetchone()
            
            if not existing_alert:
                alert_id = f"a-{datetime.now().timestamp()}-{machine['id']}"
                c.execute('''
                    INSERT INTO alerts (id, type, machine_id, machine_name, message, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (alert_id, alert_type, machine['id'], machine['name'], message, datetime.now().isoformat()))
                alerts_created += 1
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': f'{alerts_created} alerte(s) créée(s)',
            'alertsCreated': alerts_created
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== DONNÉES DE TEST ====================

@app.route('/api/seed-data', methods=['POST'])
def seed_data():
    """Insère des données de test dans la base de données"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('DELETE FROM alerts')
        c.execute('DELETE FROM pointages')
        c.execute('DELETE FROM machines')
        
        machines_test = [
            ('1', 'PC-Bureau-01', '192.168.1.101', 'active', 'user1@company.com', 7.5),
            ('2', 'PC-Bureau-02', '192.168.1.102', 'active', 'user2@company.com', 6.2),
            ('3', 'PC-Accueil', '192.168.1.103', 'inactive', None, 0),
            ('4', 'PC-Salle-Reunion', '192.168.1.104', 'warning', 'salle@company.com', 3.1),
            ('5', 'PC-Direction', '192.168.1.105', 'active', 'direction@company.com', 8.0),
            ('6', 'PC-Comptabilite', '192.168.1.106', 'active', 'compta@company.com', 7.8),
            ('7', 'PC-RH', '192.168.1.107', 'inactive', 'rh@company.com', 0),
            ('8', 'PC-Marketing', '192.168.1.108', 'active', 'marketing@company.com', 5.5),
        ]
        
        for machine in machines_test:
            last_pointage = datetime.now() - timedelta(hours=2) if machine[3] == 'active' else datetime.now() - timedelta(days=2)
            c.execute('''
                INSERT INTO machines (id, name, ip, status, email, total_hours_today, last_pointage)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (*machine, last_pointage.isoformat()))
        
        print("✅ Machines insérées")
        
        pointage_types = ['allumage', 'extinction']
        for i in range(50):
            machine = machines_test[i % len(machines_test)]
            pointage_type = pointage_types[i % 2]
            timestamp = datetime.now() - timedelta(hours=i, minutes=i*3)
            
            c.execute('''
                INSERT INTO pointages (id, machine_id, machine_name, type, timestamp, ip)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                f'p-{i}',
                machine[0],
                machine[1],
                pointage_type,
                timestamp.isoformat(),
                machine[2]
            ))
        
        print("✅ Pointages insérés")
        
        alertes_test = [
            ('a1', 'inactive', '3', 'PC-Accueil', 'Machine inactive depuis plus de 24h', (datetime.now() - timedelta(hours=1)).isoformat(), 0),
            ('a2', 'inactive', '7', 'PC-RH', 'Machine inactive depuis plus de 72h', (datetime.now() - timedelta(hours=2)).isoformat(), 0),
            ('a3', 'warning', '4', 'PC-Salle-Reunion', 'Pas de pointage depuis 12h', (datetime.now() - timedelta(minutes=30)).isoformat(), 0),
            ('a4', 'error', '2', 'PC-Bureau-02', 'Erreur de connexion détectée', (datetime.now() - timedelta(days=1)).isoformat(), 1),
        ]
        
        for alerte in alertes_test:
            c.execute('''
                INSERT INTO alerts (id, type, machine_id, machine_name, message, timestamp, resolved)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', alerte)
        
        print("✅ Alertes insérées")
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Données de test insérées avec succès',
            'machines': len(machines_test),
            'pointages': 50,
            'alertes': len(alertes_test)
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def insert_sample_data():
    """Fonction pour insérer des données au démarrage si la DB est vide"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT COUNT(*) as count FROM machines')
        count = c.fetchone()['count']
        
        if count == 0:
            print("📦 Base de données vide - Insertion des données de test...")
            conn.close()
            
            with app.test_client() as client:
                response = client.post('/api/seed-data')
                if response.status_code == 201:
                    print("✅ Données de test insérées avec succès!")
                else:
                    print("❌ Erreur lors de l'insertion des données de test")
        else:
            print(f"✅ Base de données contient déjà {count} machine(s)")
            conn.close()
            
    except Exception as e:
        print(f"❌ Erreur: {e}")

# ==================== DÉMARRAGE ====================

if __name__ == '__main__':
    init_db()
    insert_sample_data()
    
    print("\n" + "="*70)
    print("🚀 SERVEUR DE POINTAGE UNIFIÉ DÉMARRÉ")
    print("="*70)
    print(f"\n📡 HTTP API:      http://0.0.0.0:5000")
    print(f"🔌 WebSocket:     ws://0.0.0.0:5000")
    print(f"\n💡 Architecture:")
    print(f"   • Frontend React    → API REST (HTTP)")
    print(f"   • Clients pointage  → WebSocket (temps réel)")
    print(f"   • Dashboard web     → API REST + WebSocket (notifications)")
    
    print(f"\n📊 Routes API disponibles:")
    print(f"\n   Machines:")
    print(f"   • GET    /api/machines")
    print(f"   • POST   /api/machines")
    print(f"   • GET    /api/machines/<id>")
    print(f"   • PUT    /api/machines/<id>")
    print(f"   • DELETE /api/machines/<id>")
    print(f"   • POST   /api/machines/<id>/command (envoie commande via WebSocket)")
    
    print(f"\n   Pointages:")
    print(f"   • GET    /api/pointages")
    print(f"   • POST   /api/pointages (fallback HTTP)")
    
    print(f"\n   Alertes:")
    print(f"   • GET    /api/alerts")
    print(f"   • PUT    /api/alerts/<id>/resolve")
    
    print(f"\n   Statistiques:")
    print(f"   • GET    /api/statistics")
    
    print(f"\n   Rapports:")
    print(f"   • GET    /api/reports")
    print(f"   • GET    /api/reports/<machine_id>")
    
    print(f"\n   Graphiques:")
    print(f"   • GET    /api/chart-data")
    
    print(f"\n   Utilitaires:")
    print(f"   • POST   /api/check-alerts")
    print(f"   • POST   /api/seed-data (données de test)")
    
    print(f"\n🔌 Événements WebSocket:")
    print(f"\n   Clients de pointage:")
    print(f"   • register_machine   (enregistrement)")
    print(f"   • pointage           (envoi pointage)")
    print(f"   • heartbeat          (keep-alive)")
    print(f"   • get_status         (demande statut)")
    
    print(f"\n   Dashboard web:")
    print(f"   • dashboard_connected (connexion dashboard)")
    print(f"   • machine_connected   (notification nouvelle machine)")
    print(f"   • machine_disconnected (notification déconnexion)")
    print(f"   • new_pointage        (notification nouveau pointage)")
    
    print(f"\n💡 Test rapide:")
    print(f"   curl http://localhost:5000/api/machines")
    print("="*70 + "\n")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)