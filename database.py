import sqlite3
import json
from datetime import datetime

def init_db():
    conn = sqlite3.connect('glow_data.db')
    cursor = conn.cursor()
    # Stores audits for users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT,
            metrics TEXT,
            witty_report TEXT
        )
    ''')
    # Stores automated test results for development
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS test_bench (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name TEXT,
            timestamp TEXT,
            img1_path TEXT,
            img2_path TEXT,
            results TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_audit(user_id, metrics, report):
    conn = sqlite3.connect('glow_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO audits (user_id, timestamp, metrics, witty_report)
        VALUES (?, ?, ?, ?)
    ''', (user_id, datetime.now().isoformat(), json.dumps(metrics), report))
    conn.commit()
    conn.close()

def get_user_history(user_id, limit=5):
    conn = sqlite3.connect('glow_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, metrics FROM audits WHERE user_id = ? 
        ORDER BY timestamp DESC LIMIT ?
    ''', (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    
    # Return in chronological order with the same structure as context.user_data['history']
    return [{
        'date': r[0],
        'metrics': json.loads(r[1])
    } for r in rows][::-1]

def log_test_result(test_name, img1, img2, results):
    conn = sqlite3.connect('glow_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO test_bench (test_name, timestamp, img1_path, img2_path, results)
        VALUES (?, ?, ?, ?, ?)
    ''', (test_name, datetime.now().isoformat(), img1, img2, json.dumps(results)))
    conn.commit()
    conn.close()