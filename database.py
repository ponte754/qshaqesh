import sqlite3
import json
from datetime import datetime

DATABASE = 'database.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # جدول المستخدمين
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT,
            auth_type TEXT DEFAULT 'normal',
            google_id TEXT UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول الإعلانات (مع الحقول الجديدة)
    c.execute('''
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            city TEXT NOT NULL,
            price TEXT NOT NULL,
            price_value REAL DEFAULT 0,
            currency TEXT DEFAULT 'ليرة سورية',
            condition TEXT,
            negotiable TEXT DEFAULT 'لا',
            delivery TEXT DEFAULT 'لا',
            brand TEXT,
            model TEXT,
            commission REAL DEFAULT 0,
            description TEXT,
            phone TEXT NOT NULL,
            username TEXT NOT NULL,
            images TEXT,
            date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    
    # جدول الحظر
    c.execute('''
        CREATE TABLE IF NOT EXISTS blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blocker TEXT NOT NULL,
            blocked TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(blocker) REFERENCES users(username),
            FOREIGN KEY(blocked) REFERENCES users(username),
            UNIQUE(blocker, blocked)
        )
    ''')
    
    # جدول الرسائل
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            ad_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sender) REFERENCES users(username),
            FOREIGN KEY(receiver) REFERENCES users(username),
            FOREIGN KEY(ad_id) REFERENCES ads(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# ===== دوال المستخدمين =====
def get_user_by_username(username):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (username,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_email(email):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE email = ?', (email,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_google_id(google_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE google_id = ?', (google_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(username, email, password, auth_type='normal', google_id=None):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO users (username, email, password, auth_type, google_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, email, password, auth_type, google_id))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

# ===== دوال الإعلانات (مع الحقول الجديدة) =====
def create_ad(title, category, city, price, price_value, currency, condition, negotiable, delivery, brand, model, commission, description, phone, username, images):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO ads 
        (title, category, city, price, price_value, currency, condition, negotiable, delivery, brand, model, commission, description, phone, username, images, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    ''', (title, category, city, price, price_value, currency, condition, negotiable, delivery, brand, model, commission, description, phone, username, images))
    conn.commit()
    last_id = c.lastrowid
    conn.close()
    return last_id

def get_ad_by_id(ad_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM ads WHERE id = ?', (ad_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_ads(current_username=None):
    conn = get_db()
    c = conn.cursor()
    query = 'SELECT * FROM ads ORDER BY date DESC'
    if current_username:
        # استثناء الإعلانات من المستخدمين المحظورين
        c.execute('''
            SELECT ads.* FROM ads
            WHERE NOT EXISTS (
                SELECT 1 FROM blocks 
                WHERE blocker = ? AND blocked = ads.username
            )
            ORDER BY date DESC
        ''', (current_username,))
    else:
        c.execute(query)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_ads_by_username(username, current_username=None):
    conn = get_db()
    c = conn.cursor()
    if current_username and current_username != username:
        c.execute('''
            SELECT ads.* FROM ads
            WHERE ads.username = ? AND NOT EXISTS (
                SELECT 1 FROM blocks 
                WHERE blocker = ? AND blocked = ads.username
            )
            ORDER BY date DESC
        ''', (username, current_username))
    else:
        c.execute('SELECT * FROM ads WHERE username = ? ORDER BY date DESC', (username,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_ad(ad_id, title, category, city, price, price_value, currency, condition, negotiable, delivery, brand, model, commission, description, phone, images):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        UPDATE ads SET
            title = ?,
            category = ?,
            city = ?,
            price = ?,
            price_value = ?,
            currency = ?,
            condition = ?,
            negotiable = ?,
            delivery = ?,
            brand = ?,
            model = ?,
            commission = ?,
            description = ?,
            phone = ?,
            images = ?
        WHERE id = ?
    ''', (title, category, city, price, price_value, currency, condition, negotiable, delivery, brand, model, commission, description, phone, images, ad_id))
    conn.commit()
    conn.close()

def delete_ad(ad_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM ads WHERE id = ?', (ad_id,))
    conn.commit()
    conn.close()

def search_ads(query, category, city, current_username=None):
    conn = get_db()
    c = conn.cursor()
    sql = 'SELECT * FROM ads WHERE 1=1'
    params = []
    
    if query:
        sql += ' AND (title LIKE ? OR description LIKE ?)'
        like = f'%{query}%'
        params.extend([like, like])
    if category:
        sql += ' AND category = ?'
        params.append(category)
    if city:
        sql += ' AND city = ?'
        params.append(city)
    
    sql += ' ORDER BY date DESC'
    
    if current_username:
        sql = sql.replace('SELECT * FROM ads', '''
            SELECT ads.* FROM ads
            WHERE NOT EXISTS (
                SELECT 1 FROM blocks 
                WHERE blocker = ? AND blocked = ads.username
            )
        ''')
        params.insert(0, current_username)
    
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ===== دوال الحظر =====
def block_user(blocker, blocked):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO blocks (blocker, blocked) VALUES (?, ?)', (blocker, blocked))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def unblock_user(blocker, blocked):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM blocks WHERE blocker = ? AND blocked = ?', (blocker, blocked))
    conn.commit()
    deleted = c.rowcount
    conn.close()
    return deleted > 0

def is_user_blocked(blocker, blocked):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT 1 FROM blocks WHERE blocker = ? AND blocked = ?', (blocker, blocked))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_blocked_by_count(username):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM blocks WHERE blocked = ?', (username,))
    count = c.fetchone()[0]
    conn.close()
    return count

# ===== دوال الرسائل =====
def create_message(sender, receiver, ad_id, subject, message):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages (sender, receiver, ad_id, subject, message, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    ''', (sender, receiver, ad_id, subject, message))
    conn.commit()
    last_id = c.lastrowid
    conn.close()
    return last_id

def get_user_messages(username):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT m.*, a.title as ad_title, a.images as ad_images
        FROM messages m
        LEFT JOIN ads a ON m.ad_id = a.id
        WHERE m.receiver = ?
        ORDER BY m.created_at DESC
    ''', (username,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_sent_messages(username):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT m.*, a.title as ad_title
        FROM messages m
        LEFT JOIN ads a ON m.ad_id = a.id
        WHERE m.sender = ?
        ORDER BY m.created_at DESC
    ''', (username,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_conversation(user1, user2, ad_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT m.*, a.title as ad_title
        FROM messages m
        LEFT JOIN ads a ON m.ad_id = a.id
        WHERE ((sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?))
        AND m.ad_id = ?
        ORDER BY m.created_at ASC
    ''', (user1, user2, user2, user1, ad_id))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def mark_message_as_read(message_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE messages SET is_read = 1 WHERE id = ?', (message_id,))
    conn.commit()
    conn.close()

def get_unread_count(username):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM messages WHERE receiver = ? AND is_read = 0', (username,))
    count = c.fetchone()[0]
    conn.close()
    return count

def delete_message(message_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM messages WHERE id = ? AND (sender = ? OR receiver = ?)', (message_id, username, username))
    conn.commit()
    deleted = c.rowcount
    conn.close()
    return deleted > 0

def delete_conversation(user1, user2, ad_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        DELETE FROM messages 
        WHERE ((sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?))
        AND ad_id = ?
    ''', (user1, user2, user2, user1, ad_id))
    conn.commit()
    deleted = c.rowcount
    conn.close()
    return deleted > 0
