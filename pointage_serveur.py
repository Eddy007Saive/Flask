from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import os

app = Flask(__name__)
CORS(app)  # Permet les requêtes cross-origin depuis le frontend

# Initialiser la base de données
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
            email TEXT,
            total_hours_today REAL DEFAULT 0
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

def get_db():
    conn = sqlite3.connect('pointages.db')
    conn.row_factory = sqlite3.Row
    return conn

# ==================== ROUTES MACHINES ====================

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
            result.append({
                'id': m['id'],
                'name': m['name'],
                'ip': m['ip'],
                'status': m['status'],
                'lastPointage': m['last_pointage'],
                'email': m['email'],
                'totalHoursToday': m['total_hours_today']
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
        
        return jsonify({
            'id': machine['id'],
            'name': machine['name'],
            'ip': machine['ip'],
            'status': machine['status'],
            'lastPointage': machine['last_pointage'],
            'email': machine['email'],
            'totalHoursToday': machine['total_hours_today']
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

# ==================== ROUTES POINTAGES ====================

@app.route('/api/pointages', methods=['GET'])
def get_pointages():
    """Récupère tous les pointages avec filtres optionnels"""
    try:
        # Paramètres de filtrage
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
            result.append({
                'id': p['id'],
                'machineId': p['machine_id'],
                'machineName': p['machine_name'],
                'type': p['type'],
                'timestamp': p['timestamp'],
                'ip': p['ip']
            })
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pointages', methods=['POST'])
def create_pointage():
    """Enregistre un nouveau pointage (allumage ou extinction)"""
    try:
        data = request.get_json()
        machine_id = data.get('machineId')
        machine_name = data.get('machineName')  # Nouveau paramètre
        machine_ip = data.get('machineIp')      # Nouveau paramètre
        pointage_type = data.get('type', 'allumage')  # 'allumage' ou 'extinction'
        
        if not machine_id:
            return jsonify({'error': 'machineId requis'}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Vérifier si la machine existe
        c.execute('SELECT * FROM machines WHERE id = ?', (machine_id,))
        machine = c.fetchone()
        
        # ✅ Si la machine n'existe pas, la créer automatiquement
        if not machine:
            # Valeurs par défaut si non fournies
            if not machine_name:
                machine_name = f"Machine-{machine_id}"
            if not machine_ip:
                machine_ip = request.remote_addr  # Utiliser l'IP de la requête
            
            print(f"🆕 Nouvelle machine détectée : {machine_name} ({machine_ip})")
            
            c.execute('''
                INSERT INTO machines (id, name, ip, status, last_pointage)
                VALUES (?, ?, ?, 'inactive', ?)
            ''', (machine_id, machine_name, machine_ip, datetime.now().isoformat()))
            
            # Recharger la machine nouvellement créée
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
        
        return jsonify({
            'message': 'Pointage enregistré',
            'id': pointage_id,
            'machineId': machine_id,
            'machineName': machine['name'],
            'type': pointage_type,
            'timestamp': timestamp,
            'isNewMachine': machine is None  # Indique si c'était une nouvelle machine
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
        result = c.execute('SELECT COUNT(*) as total FROM machines').fetchone()
        total_machines = result['total'] if result else 0
        
        # Machines actives
        result = c.execute('SELECT COUNT(*) as active FROM machines WHERE status = "active"').fetchone()
        active_machines = result['active'] if result else 0
        
        # Machines inactives
        result = c.execute('SELECT COUNT(*) as inactive FROM machines WHERE status = "inactive"').fetchone()
        inactive_machines = result['inactive'] if result else 0
        
        # Total heures aujourd'hui
        result = c.execute('SELECT SUM(total_hours_today) as total FROM machines').fetchone()
        total_hours_today = result['total'] if result and result['total'] else 0
        
        # Pointages aujourd'hui
        today = datetime.now().date().isoformat()
        result = c.execute('SELECT COUNT(*) as count FROM pointages WHERE DATE(timestamp) = ?', (today,)).fetchone()
        pointages_today = result['count'] if result else 0
        
        conn.close()
        
        return jsonify({
            'totalMachines': total_machines,
            'activeMachines': active_machines,
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
                        # Calculer les heures (simplification)
                        daily_details[date]['hoursWorked'] += 8  # Valeur par défaut
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
        
        # Récupérer la machine
        c.execute('SELECT * FROM machines WHERE id = ?', (machine_id,))
        machine = c.fetchone()
        
        if not machine:
            return jsonify({'error': 'Machine non trouvée'}), 404
        
        # Récupérer les pointages
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        c.execute('''
            SELECT *
            FROM pointages
            WHERE machine_id = ? AND timestamp >= ?
            ORDER BY timestamp DESC
        ''', (machine_id, start_date))
        pointages = c.fetchall()
        
        conn.close()
        
        # Formater les pointages
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
        
        # Compter les allumages et extinctions par heure
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
        
        # Trouver les machines inactives depuis plus de 24h
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
            
            # Vérifier si une alerte similaire existe déjà
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
        
        # Nettoyer les tables existantes
        c.execute('DELETE FROM alerts')
        c.execute('DELETE FROM pointages')
        c.execute('DELETE FROM machines')
        
        # Machines de test
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
        
        # Pointages de test (50 derniers pointages)
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
        
        # Alertes de test
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
        
        # Vérifier si des machines existent déjà
        c.execute('SELECT COUNT(*) as count FROM machines')
        count = c.fetchone()['count']
        
        if count == 0:
            print("📦 Base de données vide - Insertion des données de test...")
            conn.close()
            
            # Utiliser la route seed_data
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
    app.run(debug=True)
     # Insérer des données si la DB est vide
    
    print("\n🚀 Serveur API démarré sur http://0.0.0.0:5000")
    print("\n📊 Routes disponibles:")
    print("   Machines:")
    print("   - GET    /api/machines")
    print("   - POST   /api/machines")
    print("   - GET    /api/machines/<id>")
    print("   - PUT    /api/machines/<id>")
    print("   - DELETE /api/machines/<id>")
    print("\n   Pointages:")
    print("   - GET    /api/pointages")
    print("   - POST   /api/pointages")
    print("\n   Alertes:")
    print("   - GET    /api/alerts")
    print("   - PUT    /api/alerts/<id>/resolve")
    print("\n   Statistiques:")
    print("   - GET    /api/statistics")
    print("\n   Rapports:")
    print("   - GET    /api/reports")
    print("   - GET    /api/reports/<machine_id>")
    print("\n   Graphiques:")
    print("   - GET    /api/chart-data")
    print("\n   Test:")
    print("   - POST   /api/seed-data (réinitialiser avec données de test)")
    print("\n💡 Testez avec: curl http://localhost:5000/api/machines")
    
    app.run(host='0.0.0.0', port=5000, debug=True)