import sqlite3
import os
import json
import logging
from datetime import datetime, timezone, timedelta
import requests

logger = logging.getLogger(__name__)

# Load .env file if present
ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(ENV_PATH):
    try:
        with open(ENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except Exception as e:
        logger.warning("Error reading .env file: %s", e)

if os.environ.get('VERCEL'):
    DB_PATH = '/tmp/database.db'
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://aitjqnfliraspychotrl.supabase.co").rstrip('/')
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFpdGpxbmZsaXJhc3B5Y2hvdHJsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY5NDgyMzQsImV4cCI6MjEwMjUyNDIzNH0.OqDFSeT2Olj2sAD4_Gh3prtGzvob7EX9xdChXeRVq3M")

def get_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.warning("SQLite connect warning (%s): %s", DB_PATH, e)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn

def is_supabase_enabled():
    return bool(SUPABASE_URL and SUPABASE_KEY)

def _supabase_headers():
    return {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

def _supabase_request(method, endpoint, json_data=None, params=None):
    if not is_supabase_enabled():
        return None
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    try:
        res = requests.request(
            method=method,
            url=url,
            headers=_supabase_headers(),
            json=json_data,
            params=params,
            timeout=4.0
        )
        if res.status_code in (200, 201):
            return res.json()
        elif res.status_code in (204,):
            return True
        else:
            logger.warning("Supabase request failed: %s %s -> %s %s", method, endpoint, res.status_code, res.text)
            return None
    except Exception as ex:
        logger.warning("Supabase request error (%s %s): %s", method, endpoint, ex)
        return None

# ===================================================
# USERS API (SUPABASE + SQLITE DUAL SYNC)
# ===================================================
def create_user(name, email, phone, password_hash):
    now_str = datetime.now(timezone.utc).isoformat()
    user_id = None
    
    # 1. Write to Supabase
    sb_result = _supabase_request('POST', 'vent_users', json_data={
        'name': name,
        'email': email.lower().strip(),
        'phone': phone or '',
        'password_hash': password_hash,
        'created_at': now_str
    })
    if sb_result and isinstance(sb_result, list) and len(sb_result) > 0:
        user_id = sb_result[0].get('id')

    # 2. Sync to local SQLite
    conn = get_db()
    cursor = conn.cursor()
    try:
        if user_id:
            cursor.execute(
                "INSERT OR REPLACE INTO users (id, name, email, phone, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, name, email.lower().strip(), phone or '', password_hash, now_str)
            )
        else:
            cursor.execute(
                "INSERT INTO users (name, email, phone, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (name, email.lower().strip(), phone or '', password_hash, now_str)
            )
            user_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        logger.error("SQLite user write error: %s", e)
    finally:
        conn.close()

    return user_id

def get_user_by_email(email):
    email = email.lower().strip()
    
    # 1. Try Supabase first
    sb_result = _supabase_request('GET', f'vent_users?email=eq.{email}&select=*')
    if sb_result and isinstance(sb_result, list) and len(sb_result) > 0:
        u = sb_result[0]
        # Keep local SQLite in sync
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO users (id, name, email, phone, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (u['id'], u['name'], u['email'], u.get('phone', ''), u['password_hash'], u.get('created_at', ''))
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()
        return u

    # 2. Fall back to local SQLite
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, phone, password_hash, created_at FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_user_by_id(user_id):
    # 1. Try Supabase
    sb_result = _supabase_request('GET', f'vent_users?id=eq.{user_id}&select=*')
    if sb_result and isinstance(sb_result, list) and len(sb_result) > 0:
        return sb_result[0]

    # 2. Fall back to local SQLite
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, phone, password_hash, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

# ===================================================
# ORDERS API (SUPABASE + SQLITE DUAL SYNC)
# ===================================================
def create_order(order_dict):
    # 1. Write to Supabase
    _supabase_request('POST', 'vent_orders', json_data=order_dict)

    # 2. Sync to local SQLite
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        INSERT OR REPLACE INTO orders (
            id, created_at, target_delivery_at, plan_type, plan_name, plan_price,
            business_name, vendor_name, whatsapp_number, email, category, currency,
            tagline, about_text, address, instagram, facebook, tiktok,
            products_json, status, website_url, publish_mode, is_published,
            vendor_admin_url, vendor_admin_user, vendor_admin_pass, admin_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            order_dict['id'],
            order_dict['created_at'],
            order_dict['target_delivery_at'],
            order_dict['plan_type'],
            order_dict['plan_name'],
            order_dict['plan_price'],
            order_dict['business_name'],
            order_dict['vendor_name'],
            order_dict['whatsapp_number'],
            order_dict.get('email', ''),
            order_dict.get('category', ''),
            order_dict.get('currency', '$'),
            order_dict.get('tagline', ''),
            order_dict.get('about_text', ''),
            order_dict.get('address', ''),
            order_dict.get('instagram', ''),
            order_dict.get('facebook', ''),
            order_dict.get('tiktok', ''),
            order_dict.get('products_json', '[]'),
            order_dict.get('status', 'submitted'),
            order_dict.get('website_url', ''),
            order_dict.get('publish_mode', 'countdown'),
            order_dict.get('is_published', 0),
            order_dict.get('vendor_admin_url', ''),
            order_dict.get('vendor_admin_user', ''),
            order_dict.get('vendor_admin_pass', ''),
            order_dict.get('admin_notes', '')
        ))
        conn.commit()
    except Exception as e:
        logger.error("SQLite order write error: %s", e)
    finally:
        conn.close()

def get_order(order_id):
    # 1. Try Supabase
    sb_result = _supabase_request('GET', f'vent_orders?id=eq.{order_id}&select=*')
    if sb_result and isinstance(sb_result, list) and len(sb_result) > 0:
        return sb_result[0]

    # 2. Fall back to local SQLite
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_all_orders():
    # 1. Try Supabase
    sb_result = _supabase_request('GET', 'vent_orders?select=*&order=created_at.desc')
    if sb_result and isinstance(sb_result, list) and len(sb_result) > 0:
        return sb_result

    # 2. Fall back to local SQLite
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_order(order_id, update_dict):
    # 1. Update Supabase
    _supabase_request('PATCH', f'vent_orders?id=eq.{order_id}', json_data=update_dict)

    # 2. Update SQLite
    conn = get_db()
    cursor = conn.cursor()
    set_clauses = [f"{k} = ?" for k in update_dict.keys()]
    values = list(update_dict.values()) + [order_id]
    try:
        cursor.execute(f"UPDATE orders SET {', '.join(set_clauses)} WHERE id = ?", values)
        conn.commit()
    except Exception as e:
        logger.error("SQLite order update error: %s", e)
    finally:
        conn.close()

def search_orders(query):
    query = query.strip()
    if not query:
        return []
    # 1. Try Supabase
    sb_result = _supabase_request('GET', f'vent_orders?or=(id.ilike.*{query}*,whatsapp_number.ilike.*{query}*,email.ilike.*{query}*,business_name.ilike.*{query}*)&select=*&order=created_at.desc')
    if sb_result and isinstance(sb_result, list) and len(sb_result) > 0:
        return sb_result

    # 2. Fall back to SQLite
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM orders 
        WHERE id LIKE ? 
           OR whatsapp_number LIKE ? 
           OR email LIKE ? 
           OR business_name LIKE ? 
        ORDER BY created_at DESC
    """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_order(order_id):
    # 1. Delete from Supabase
    _supabase_request('DELETE', f'vent_orders?id=eq.{order_id}')

    # 2. Delete from SQLite
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

# ===================================================
# SETTINGS API (SUPABASE + SQLITE DUAL SYNC)
# ===================================================
def get_setting(key, default=None):
    # 1. Try Supabase
    sb_result = _supabase_request('GET', f'vent_settings?key=eq.{key}&select=value')
    if sb_result and isinstance(sb_result, list) and len(sb_result) > 0:
        return sb_result[0].get('value', default)

    # 2. Fall back to local SQLite
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['value']
    return default

def set_setting(key, value):
    # 1. Supabase
    _supabase_request('POST', 'vent_settings', json_data={'key': key, 'value': str(value)}, params={'on_conflict': 'key'})

    # 2. SQLite
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def init_db():
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            target_delivery_at TEXT NOT NULL,
            plan_type TEXT NOT NULL,          -- 'basic_2' or 'pro_10'
            plan_name TEXT NOT NULL,
            plan_price REAL NOT NULL,
            business_name TEXT NOT NULL,
            vendor_name TEXT NOT NULL,
            whatsapp_number TEXT NOT NULL,
            email TEXT,
            category TEXT,
            currency TEXT DEFAULT '$',
            tagline TEXT,
            about_text TEXT,
            address TEXT,
            instagram TEXT,
            facebook TEXT,
            tiktok TEXT,
            products_json TEXT,              -- JSON string of products array
            status TEXT DEFAULT 'submitted', -- 'submitted', 'in_progress', 'ready', 'delivered'
            website_url TEXT DEFAULT '',     -- Link submitted by admin
            publish_mode TEXT DEFAULT 'countdown', -- 'countdown' (reveal when 24h expires) or 'immediate' (reveal right away)
            is_published INTEGER DEFAULT 0,  -- 1 if ready to be viewed by vendor
            vendor_admin_url TEXT DEFAULT '',-- Vendor login link for $10 plan
            vendor_admin_user TEXT DEFAULT '',
            vendor_admin_pass TEXT DEFAULT '',
            admin_notes TEXT DEFAULT ''
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT DEFAULT '',
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        ''')

        # Seed default admin password if not present
        cursor.execute("SELECT value FROM settings WHERE key = 'admin_password'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO settings (key, value) VALUES ('admin_password', 'admin123')")
            cursor.execute("INSERT INTO settings (key, value) VALUES ('platform_whatsapp', '+1234567890')")
            cursor.execute("INSERT INTO settings (key, value) VALUES ('site_name', 'Vent Collection')")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("init_db exception (safe to ignore if using Supabase): %s", e)

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully at:", DB_PATH)
    print("Supabase Connected:", is_supabase_enabled())
