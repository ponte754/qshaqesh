import sqlite3
from datetime import datetime
import json

DB_NAME = 'qashqish.db'

def get_db():
    """الحصول على اتصال قاعدة البيانات"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """إنشاء الجداول في قاعدة البيانات"""
    conn = get_db()
    cursor = conn.cursor()
    
    # جدول المستخدمين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT,
            login_type TEXT DEFAULT 'normal',
            google_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول الإعلانات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            city TEXT NOT NULL,
            price TEXT,
            price_value REAL DEFAULT 0,
            commission REAL DEFAULT 0,
            description TEXT NOT NULL,
            phone TEXT NOT NULL,
            username TEXT NOT NULL,
            images TEXT DEFAULT '[]',
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (username) REFERENCES users (username)
        )
    ''')
    
    # جدول الحظر (منع البائع)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blocker_username TEXT NOT NULL,
            blocked_username TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (blocker_username) REFERENCES users (username),
            FOREIGN KEY (blocked_username) REFERENCES users (username),
            UNIQUE(blocker_username, blocked_username)
        )
    ''')
    
    # جدول الرسائل الخاصة
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_username TEXT NOT NULL,
            receiver_username TEXT NOT NULL,
            ad_id INTEGER,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_username) REFERENCES users (username),
            FOREIGN KEY (receiver_username) REFERENCES users (username),
            FOREIGN KEY (ad_id) REFERENCES ads (id) ON DELETE SET NULL
        )
    ''')
    
    # إضافة فهارس لتحسين الأداء
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver_username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_ad ON messages(ad_id)')
    
    # التحقق من وجود عمود images وإضافته إذا لم يكن موجوداً (للترقية)
    try:
        cursor.execute('ALTER TABLE ads ADD COLUMN images TEXT DEFAULT "[]"')
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

# ===== دوال المستخدمين =====
def create_user(username, email, password=None, login_type='normal', google_id=None):
    """إنشاء مستخدم جديد"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, email, password, login_type, google_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, email, password, login_type, google_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_user_by_username(username):
    """الحصول على مستخدم حسب اسم المستخدم"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_email(email):
    """الحصول على مستخدم حسب البريد الإلكتروني"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_google_id(google_id):
    """الحصول على مستخدم حسب Google ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE google_id = ?', (google_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

# ===== دوال الإعلانات =====
def create_ad(title, category, city, price, price_value, commission, description, phone, username, images='[]'):
    """إنشاء إعلان جديد مع دعم عدة صور"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ads (title, category, city, price, price_value, commission, description, phone, username, images)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, category, city, price, price_value, commission, description, phone, username, images))
    conn.commit()
    ad_id = cursor.lastrowid
    conn.close()
    return ad_id

def get_all_ads(current_username=None):
    """جلب جميع الإعلانات مع تصفية المحظورين"""
    conn = get_db()
    cursor = conn.cursor()
    
    if current_username:
        blocked_users = get_blocked_users(current_username)
        if blocked_users:
            placeholders = ','.join(['?' for _ in blocked_users])
            cursor.execute(f'''
                SELECT * FROM ads 
                WHERE username NOT IN ({placeholders})
                ORDER BY id DESC
            ''', blocked_users)
        else:
            cursor.execute('SELECT * FROM ads ORDER BY id DESC')
    else:
        cursor.execute('SELECT * FROM ads ORDER BY id DESC')
    
    ads = cursor.fetchall()
    conn.close()
    return [dict(ad) for ad in ads]

def get_ad_by_id(ad_id):
    """جلب إعلان حسب المعرف"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM ads WHERE id = ?', (ad_id,))
    ad = cursor.fetchone()
    conn.close()
    if ad:
        ad_dict = dict(ad)
        ad_dict['images_list'] = json.loads(ad_dict.get('images', '[]'))
        return ad_dict
    return None

def get_ads_by_username(username, current_username=None):
    """جلب إعلانات مستخدم معين مع مراعاة الحظر"""
    conn = get_db()
    cursor = conn.cursor()
    
    if current_username == username:
        cursor.execute('SELECT * FROM ads WHERE username = ? ORDER BY id DESC', (username,))
    else:
        if current_username and is_user_blocked(username, current_username):
            cursor.execute('SELECT * FROM ads WHERE 1=0')
        else:
            cursor.execute('SELECT * FROM ads WHERE username = ? ORDER BY id DESC', (username,))
    
    ads = cursor.fetchall()
    conn.close()
    return [dict(ad) for ad in ads]

def update_ad(ad_id, title, category, city, price, price_value, commission, description, phone, images=None):
    """تحديث إعلان"""
    conn = get_db()
    cursor = conn.cursor()
    if images is not None:
        cursor.execute('''
            UPDATE ads 
            SET title=?, category=?, city=?, price=?, price_value=?, commission=?, description=?, phone=?, images=?, date=CURRENT_TIMESTAMP
            WHERE id=?
        ''', (title, category, city, price, price_value, commission, description, phone, images, ad_id))
    else:
        cursor.execute('''
            UPDATE ads 
            SET title=?, category=?, city=?, price=?, price_value=?, commission=?, description=?, phone=?, date=CURRENT_TIMESTAMP
            WHERE id=?
        ''', (title, category, city, price, price_value, commission, description, phone, ad_id))
    conn.commit()
    conn.close()

def delete_ad(ad_id):
    """حذف إعلان"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ads WHERE id = ?', (ad_id,))
    conn.commit()
    conn.close()

def search_ads(query, category, city, current_username=None):
    """البحث في الإعلانات مع تصفية المحظورين"""
    conn = get_db()
    cursor = conn.cursor()
    
    sql = 'SELECT * FROM ads WHERE 1=1'
    params = []
    
    if current_username:
        blocked_users = get_blocked_users(current_username)
        if blocked_users:
            placeholders = ','.join(['?' for _ in blocked_users])
            sql += f' AND username NOT IN ({placeholders})'
            params.extend(blocked_users)
    
    if query:
        sql += ' AND (title LIKE ? OR description LIKE ?)'
        params.extend([f'%{query}%', f'%{query}%'])
    
    if category and category != '':
        sql += ' AND category = ?'
        params.append(category)
    
    if city and city != '':
        sql += ' AND city = ?'
        params.append(city)
    
    sql += ' ORDER BY id DESC'
    
    cursor.execute(sql, params)
    ads = cursor.fetchall()
    conn.close()
    return [dict(ad) for ad in ads]

# ===== دوال الحظر (Block System) =====
def block_user(blocker_username, blocked_username):
    """حظر مستخدم بواسطة مستخدم آخر"""
    if blocker_username == blocked_username:
        return False
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO blocks (blocker_username, blocked_username)
            VALUES (?, ?)
        ''', (blocker_username, blocked_username))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def unblock_user(blocker_username, blocked_username):
    """إلغاء حظر مستخدم"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM blocks
        WHERE blocker_username = ? AND blocked_username = ?
    ''', (blocker_username, blocked_username))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def is_user_blocked(blocker_username, blocked_username):
    """التحقق مما إذا كان المستخدم محظوراً"""
    if not blocker_username or not blocked_username:
        return False
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 1 FROM blocks
        WHERE blocker_username = ? AND blocked_username = ?
    ''', (blocker_username, blocked_username))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_blocked_users(blocker_username):
    """الحصول على قائمة المستخدمين الذين قام بحظرهم مستخدم معين"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT blocked_username FROM blocks
        WHERE blocker_username = ?
    ''', (blocker_username,))
    blocked = [row['blocked_username'] for row in cursor.fetchall()]
    conn.close()
    return blocked

def get_users_who_blocked(blocked_username):
    """الحصول على قائمة المستخدمين الذين قاموا بحظر مستخدم معين"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT blocker_username FROM blocks
        WHERE blocked_username = ?
    ''', (blocked_username,))
    blockers = [row['blocker_username'] for row in cursor.fetchall()]
    conn.close()
    return blockers

def get_blocked_by_count(username):
    """الحصول على عدد المستخدمين الذين حظروا مستخدماً معيناً"""
    return len(get_users_who_blocked(username))

# ===== دوال نظام الرسائل (Messaging System) =====
def create_message(sender_username, receiver_username, ad_id, subject, message):
    """إنشاء رسالة جديدة"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO messages (sender_username, receiver_username, ad_id, subject, message, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
        ''', (sender_username, receiver_username, ad_id, subject, message))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error creating message: {e}")
        return None
    finally:
        conn.close()

def get_user_messages(username, include_read=True):
    """الحصول على جميع رسائل المستخدم (الواردة)"""
    conn = get_db()
    cursor = conn.cursor()
    
    if include_read:
        cursor.execute('''
            SELECT m.*, a.title as ad_title, a.images as ad_images
            FROM messages m
            LEFT JOIN ads a ON m.ad_id = a.id
            WHERE m.receiver_username = ?
            ORDER BY m.created_at DESC
        ''', (username,))
    else:
        cursor.execute('''
            SELECT m.*, a.title as ad_title, a.images as ad_images
            FROM messages m
            LEFT JOIN ads a ON m.ad_id = a.id
            WHERE m.receiver_username = ? AND m.is_read = 0
            ORDER BY m.created_at DESC
        ''', (username,))
    
    messages = cursor.fetchall()
    conn.close()
    return [dict(msg) for msg in messages]

def get_sent_messages(username):
    """الحصول على جميع الرسائل المرسلة من المستخدم"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.*, a.title as ad_title
        FROM messages m
        LEFT JOIN ads a ON m.ad_id = a.id
        WHERE m.sender_username = ?
        ORDER BY m.created_at DESC
    ''', (username,))
    messages = cursor.fetchall()
    conn.close()
    return [dict(msg) for msg in messages]

def get_conversation(user1, user2, ad_id=None):
    """الحصول على محادثة بين مستخدمين"""
    conn = get_db()
    cursor = conn.cursor()
    
    if ad_id:
        cursor.execute('''
            SELECT * FROM messages 
            WHERE ((sender_username = ? AND receiver_username = ?) OR (sender_username = ? AND receiver_username = ?))
            AND ad_id = ?
            ORDER BY created_at ASC
        ''', (user1, user2, user2, user1, ad_id))
    else:
        cursor.execute('''
            SELECT * FROM messages 
            WHERE (sender_username = ? AND receiver_username = ?) OR (sender_username = ? AND receiver_username = ?)
            ORDER BY created_at ASC
        ''', (user1, user2, user2, user1))
    
    messages = cursor.fetchall()
    conn.close()
    return [dict(msg) for msg in messages]

def mark_message_as_read(message_id):
    """تحديد رسالة كمقروءة"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE messages SET is_read = 1 WHERE id = ?', (message_id,))
    conn.commit()
    conn.close()

def mark_all_messages_as_read(username):
    """تحديد جميع رسائل المستخدم كمقروءة"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE messages SET is_read = 1 WHERE receiver_username = ?', (username,))
    conn.commit()
    conn.close()

def get_unread_count(username):
    """الحصول على عدد الرسائل غير المقروءة للمستخدم"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM messages WHERE receiver_username = ? AND is_read = 0', (username,))
    count = cursor.fetchone()['count']
    conn.close()
    return count

def delete_message(message_id, username):
    """حذف رسالة (فقط للمستلم)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE id = ? AND receiver_username = ?', (message_id, username))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def delete_conversation(user1, user2, ad_id=None):
    """حذف محادثة كاملة بين مستخدمين"""
    conn = get_db()
    cursor = conn.cursor()
    
    if ad_id:
        cursor.execute('''
            DELETE FROM messages 
            WHERE ((sender_username = ? AND receiver_username = ?) OR (sender_username = ? AND receiver_username = ?))
            AND ad_id = ?
        ''', (user1, user2, user2, user1, ad_id))
    else:
        cursor.execute('''
            DELETE FROM messages 
            WHERE (sender_username = ? AND receiver_username = ?) OR (sender_username = ? AND receiver_username = ?)
        ''', (user1, user2, user2, user1))
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected