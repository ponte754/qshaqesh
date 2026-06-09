from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from datetime import datetime, timedelta
import os
import requests
import json
from werkzeug.utils import secure_filename
from functools import wraps
import database as db

app = Flask(__name__)
app.secret_key = 'your_secret_key_here_12345_please_change_this_in_production'

# ===== إعدادات الجلسة =====
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ===== إعدادات رفع الصور المحسنة =====
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
MAX_IMAGES = 5
MAX_FILE_SIZE = 16 * 1024 * 1024
MAX_TOTAL_SIZE = MAX_IMAGES * MAX_FILE_SIZE

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_TOTAL_SIZE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===== إعدادات Google OAuth =====
GOOGLE_CLIENT_ID = 'YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = 'YOUR_GOOGLE_CLIENT_SECRET'
GOOGLE_REDIRECT_URI = 'http://localhost:5000/google_callback'

# ===== إعدادات الموقع =====
COMMISSION_RATE = 0.15
WHATSAPP_NUMBER = '0981677578'
SITE_NAME = 'قشاقيش'
SITE_DESCRIPTION = 'سوق الإعلانات المبوبة في سوريا'

CITIES = [
    'الحسكة', 'الرقة', 'دير الزور', 'حماة', 'دمشق', 
    'اللاذقية', 'حمص', 'القنيطرة', 'ادلب', 'حلب', 'القامشلي', 'طرطوس'
]

CATEGORIES = [
    'عقارات', 'سيارات', 'وظائف', 'الكترونيات', 'اثاث منزلي',
    'لابتوبات','خدمات', 'حيوانات', 'ازياء', 'كتب', 'رياضة', 'اخرى'
]

db.init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_multiple_images(files, upload_folder):
    saved_images = []
    if not files:
        return saved_images
    if len(files) > MAX_IMAGES:
        return saved_images
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            safe_filename = secure_filename(file.filename)
            name, ext = os.path.splitext(safe_filename)
            filename = f"{timestamp}_{name}{ext}"
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            saved_images.append(filename)
    return saved_images

def delete_images(images_list):
    deleted = 0
    for img in images_list:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], img)
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
                deleted += 1
            except Exception as e:
                print(f"Error deleting {img}: {e}")
    return deleted

def get_current_username():
    return session.get('username') or session.get('google_name', session.get('google_email'))

def get_current_email():
    return session.get('email') or session.get('google_email')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session and 'google_email' not in session:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ===== سياق القوالب =====
@app.context_processor
def inject_globals():
    def get_unread_count():
        if 'username' in session or 'google_email' in session:
            username = get_current_username()
            return db.get_unread_count(username)
        return 0
    
    return {
        'categories': CATEGORIES,
        'cities': CITIES,
        'whatsapp_number': WHATSAPP_NUMBER,
        'commission_rate': COMMISSION_RATE,
        'site_name': SITE_NAME,
        'max_images': MAX_IMAGES,
        'unread_count': get_unread_count()
    }

# ===== الصفحات الرئيسية =====
@app.route('/')
def home():
    if 'username' in session or 'google_email' in session:
        return redirect(url_for('index'))
    return redirect(url_for('login'))

@app.route('/index')
@login_required
def index():
    username = get_current_username()
    email = get_current_email()
    all_ads = db.get_all_ads(current_username=username)
    for ad in all_ads:
        if ad.get('images'):
            ad['images_list'] = json.loads(ad['images'])
        else:
            ad['images_list'] = []
    return render_template('index.html', username=username, email=email, ads=all_ads)

# ===== التسجيل والدخول =====
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        errors = []
        
        if not username or not email or not password:
            errors.append('جميع الحقول مطلوبة')
        if len(username) < 3:
            errors.append('اسم المستخدم يجب أن يكون 3 أحرف على الأقل')
        if '@' not in email or '.' not in email:
            errors.append('البريد الإلكتروني غير صحيح')
        if db.get_user_by_username(username):
            errors.append('اسم المستخدم موجود بالفعل')
        if db.get_user_by_email(email):
            errors.append('البريد الإلكتروني موجود بالفعل')
        if password != confirm_password:
            errors.append('كلمة المرور غير متطابقة')
        if len(password) < 6:
            errors.append('كلمة المرور يجب أن تكون 6 أحرف على الأقل')
        
        if errors:
            return render_template('register.html', errors=errors)
        
        success = db.create_user(username, email, password, 'normal')
        if success:
            session['username'] = username
            session['email'] = email
            session.permanent = True
            flash(f'مرحباً {username}！تم إنشاء حسابك بنجاح', 'success')
            return redirect(url_for('index'))
        else:
            errors.append('حدث خطأ في إنشاء الحساب')
            return render_template('register.html', errors=errors)
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me') == 'on'
        
        user = db.get_user_by_username(username)
        if user and user['password'] == password:
            session['username'] = user['username']
            session['email'] = user['email']
            session.permanent = remember_me
            flash(f'مرحباً {username}！تم تسجيل الدخول بنجاح', 'success')
            return redirect(url_for('index'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'error')
    
    return render_template('login.html', google_client_id=GOOGLE_CLIENT_ID)

@app.route('/google_login')
def google_login():
    google_auth_url = f"https://accounts.google.com/o/oauth2/auth?client_id={GOOGLE_CLIENT_ID}&redirect_uri={GOOGLE_REDIRECT_URI}&response_type=code&scope=email profile"
    return redirect(google_auth_url)

@app.route('/google_callback')
def google_callback():
    code = request.args.get('code')
    if not code:
        flash('فشل تسجيل الدخول عبر Google', 'error')
        return redirect(url_for('login'))
    
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    
    try:
        response = requests.post(token_url, data=data)
        token_data = response.json()
        
        if 'access_token' not in token_data:
            flash('فشل الحصول على رمز الوصول', 'error')
            return redirect(url_for('login'))
        
        userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {'Authorization': f"Bearer {token_data['access_token']}"}
        user_response = requests.get(userinfo_url, headers=headers)
        user_data = user_response.json()
        
        google_email = user_data.get('email')
        google_name = user_data.get('name')
        google_id = user_data.get('id')
        
        user = db.get_user_by_google_id(google_id)
        if not user:
            db.create_user(google_name, google_email, None, 'google', google_id)
        
        session['google_email'] = google_email
        session['google_name'] = google_name
        session['email'] = google_email
        session.permanent = True
        
        flash(f'مرحباً {google_name}！تم تسجيل الدخول عبر Google', 'success')
        return redirect(url_for('index'))
    
    except Exception as e:
        print(f"Google login error: {e}")
        flash('حدث خطأ في تسجيل الدخول عبر Google', 'error')
        return redirect(url_for('login'))

# ===== إدارة الإعلانات =====
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    username = get_current_username()
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '')
        city = request.form.get('city', '')
        price = request.form.get('price', '')
        description = request.form.get('description', '').strip()
        phone = request.form.get('phone', '').strip()
        
        images_list = []
        if 'product_images' in request.files:
            files = request.files.getlist('product_images')
            files = [f for f in files if f and f.filename]
            images_list = save_multiple_images(files, app.config['UPLOAD_FOLDER'])
        
        errors = []
        
        if not title:
            errors.append('عنوان الإعلان مطلوب')
        if not description:
            errors.append('وصف الإعلان مطلوب')
        if not phone:
            errors.append('رقم الهاتف مطلوب')
        if not category:
            errors.append('القسم مطلوب')
        if not city:
            errors.append('المدينة مطلوبة')
        if len(images_list) > MAX_IMAGES:
            errors.append(f'الحد الأقصى للصور هو {MAX_IMAGES} صور فقط')
        
        price_value = 0
        price_display = 'غير محدد'
        if price and price.replace('.', '').isdigit():
            price_value = float(price)
            price_display = f"{price_value:,.2f} "
        
        commission = price_value * COMMISSION_RATE if price_value > 0 else 0
        
        if errors:
            return render_template('add.html', 
                                 errors=errors, 
                                 form_data={
                                     'title': title,
                                     'category': category,
                                     'city': city,
                                     'price': price,
                                     'description': description,
                                     'phone': phone
                                 })
        
        images_json = json.dumps(images_list)
        
        db.create_ad(
            title=title,
            category=category,
            city=city,
            price=price_display,
            price_value=price_value,
            commission=commission,
            description=description,
            phone=phone,
            username=username,
            images=images_json
        )
        
        flash('تم نشر الإعلان بنجاح！', 'success')
        return redirect(url_for('index'))
    
    return render_template('add.html', form_data={})

@app.route('/edit/<int:ad_id>', methods=['GET', 'POST'])
@login_required
def edit_ad(ad_id):
    username = get_current_username()
    ad = db.get_ad_by_id(ad_id)
    
    if not ad or ad['username'] != username:
        flash('غير مصرح لك بتعديل هذا الإعلان', 'error')
        return redirect(url_for('my_ads'))
    
    ad['images_list'] = json.loads(ad.get('images', '[]'))
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '')
        city = request.form.get('city', '')
        price = request.form.get('price', '')
        description = request.form.get('description', '').strip()
        phone = request.form.get('phone', '').strip()
        
        price_value = 0
        price_display = 'غير محدد'
        if price and price.replace('.', '').isdigit():
            price_value = float(price)
            price_display = f"{price_value:,.2f} "
        
        commission = price_value * COMMISSION_RATE if price_value > 0 else 0
        
        images_list = ad['images_list'].copy()
        
        if 'product_images' in request.files:
            files = request.files.getlist('product_images')
            files = [f for f in files if f and f.filename]
            if files:
                new_images = save_multiple_images(files, app.config['UPLOAD_FOLDER'])
                images_list.extend(new_images)
        
        images_to_delete = request.form.getlist('delete_images')
        for img in images_to_delete:
            if img in images_list:
                images_list.remove(img)
        
        delete_images(images_to_delete)
        
        if len(images_list) > MAX_IMAGES:
            flash(f'لا يمكن أن يتجاوز عدد الصور {MAX_IMAGES} صور', 'error')
            return render_template('edit_ad.html', ad=ad)
        
        images_json = json.dumps(images_list)
        
        db.update_ad(ad_id, title, category, city, price_display, 
                    price_value, commission, description, phone, images_json)
        
        flash('تم تعديل الإعلان بنجاح！', 'success')
        return redirect(url_for('view_ad', ad_id=ad_id))
    
    return render_template('edit_ad.html', ad=ad)

@app.route('/search')
@login_required
def search():
    username = get_current_username()
    email = get_current_email()
    
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '')
    city = request.args.get('city', '')
    
    filtered_ads = db.search_ads(query, category, city, current_username=username)
    
    for ad in filtered_ads:
        if ad.get('images'):
            ad['images_list'] = json.loads(ad['images'])
        else:
            ad['images_list'] = []
    
    return render_template('index.html', 
                         username=username, 
                         email=email, 
                         ads=filtered_ads,
                         search_query=query, 
                         selected_category=category, 
                         selected_city=city)

@app.route('/ad/<int:ad_id>')
@login_required
def view_ad(ad_id):
    username = get_current_username()
    ad = db.get_ad_by_id(ad_id)
    
    if not ad:
        flash('الإعلان غير موجود', 'error')
        return redirect(url_for('index'))
    
    if ad.get('images'):
        ad['images_list'] = json.loads(ad['images'])
    else:
        ad['images_list'] = []
    
    # التحقق من حالة الحظر
    is_blocked = db.is_user_blocked(username, ad['username'])
    
    return render_template('view_ad.html', ad=ad, username=username, is_blocked=is_blocked)

@app.route('/my_ads')
@login_required
def my_ads():
    username = get_current_username()
    email = get_current_email()
    
    user_ads = db.get_ads_by_username(username, current_username=username)
    blocked_by_count = db.get_blocked_by_count(username)
    
    for ad in user_ads:
        if ad.get('images'):
            ad['images_list'] = json.loads(ad['images'])
        else:
            ad['images_list'] = []
    
    return render_template('my_ads.html', 
                         username=username, 
                         email=email, 
                         ads=user_ads,
                         blocked_by_count=blocked_by_count)

@app.route('/delete_ad/<int:ad_id>')
@login_required
def delete_ad(ad_id):
    username = get_current_username()
    ad = db.get_ad_by_id(ad_id)
    
    if ad and ad['username'] == username:
        if ad.get('images'):
            images_list = json.loads(ad['images'])
            delete_images(images_list)
        db.delete_ad(ad_id)
        flash('تم حذف الإعلان بنجاح', 'success')
    else:
        flash('غير مصرح لك بحذف هذا الإعلان', 'error')
    
    return redirect(url_for('my_ads'))

# ===== نظام الحظر =====
@app.route('/block_user/<string:blocked_username>')
@login_required
def block_user(blocked_username):
    blocker = get_current_username()
    if blocker == blocked_username:
        flash('لا يمكنك حظر نفسك', 'error')
        return redirect(request.referrer or url_for('index'))
    
    if db.block_user(blocker, blocked_username):
        flash(f'تم حظر المستخدم {blocked_username} بنجاح. لن تظهر إعلاناته بعد الآن.', 'success')
    else:
        flash('حدث خطأ أثناء محاولة حظر المستخدم', 'error')
    
    return redirect(request.referrer or url_for('index'))

@app.route('/unblock_user/<string:blocked_username>')
@login_required
def unblock_user(blocked_username):
    blocker = get_current_username()
    if db.unblock_user(blocker, blocked_username):
        flash(f'تم إلغاء حظر المستخدم {blocked_username}', 'success')
    else:
        flash('المستخدم غير موجود في قائمة الحظر', 'warning')
    
    return redirect(request.referrer or url_for('index'))

# ===== نظام الرسائل الخاصة =====
@app.route('/messages')
@login_required
def messages_inbox():
    username = get_current_username()
    
    received_messages = db.get_user_messages(username)
    sent_messages = db.get_sent_messages(username)
    unread_count = db.get_unread_count(username)
    
    for msg in received_messages:
        if msg.get('ad_images'):
            try:
                images = json.loads(msg['ad_images'])
                msg['ad_image'] = images[0] if images else None
            except:
                msg['ad_image'] = None
    
    return render_template('messages/inbox.html', 
                         received_messages=received_messages,
                         sent_messages=sent_messages,
                         unread_count=unread_count,
                         username=username)

@app.route('/message/send/<int:ad_id>', methods=['GET', 'POST'])
@login_required
def send_message(ad_id):
    sender = get_current_username()
    ad = db.get_ad_by_id(ad_id)
    
    if not ad:
        flash('الإعلان غير موجود', 'error')
        return redirect(url_for('index'))
    
    receiver = ad['username']
    
    if sender == receiver:
        flash('لا يمكنك إرسال رسالة لنفسك', 'warning')
        return redirect(url_for('view_ad', ad_id=ad_id))
    
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        if not subject or not message:
            flash('الرجاء إدخال عنوان ورسالة', 'error')
            return render_template('messages/send_message.html', ad=ad, form_data=request.form)
        
        if len(message) < 10:
            flash('الرسالة قصيرة جداً (10 أحرف على الأقل)', 'error')
            return render_template('messages/send_message.html', ad=ad, form_data=request.form)
        
        msg_id = db.create_message(sender, receiver, ad_id, subject, message)
        
        if msg_id:
            flash('تم إرسال رسالتك بنجاح! سيتم إشعار البائع.', 'success')
            return redirect(url_for('view_ad', ad_id=ad_id))
        else:
            flash('حدث خطأ أثناء إرسال الرسالة', 'error')
    
    return render_template('messages/send_message.html', ad=ad)

@app.route('/message/conversation/<int:ad_id>/<string:other_user>')
@login_required
def view_conversation(ad_id, other_user):
    current_user = get_current_username()
    ad = db.get_ad_by_id(ad_id)
    
    if not ad:
        flash('الإعلان غير موجود', 'error')
        return redirect(url_for('messages_inbox'))
    
    if current_user not in [ad['username'], other_user]:
        flash('غير مصرح لك بمشاهدة هذه المحادثة', 'error')
        return redirect(url_for('messages_inbox'))
    
    conversation = db.get_conversation(current_user, other_user, ad_id)
    
    for msg in conversation:
        if msg['receiver_username'] == current_user and not msg['is_read']:
            db.mark_message_as_read(msg['id'])
    
    return render_template('messages/conversation.html', 
                         conversation=conversation,
                         ad=ad,
                         other_user=other_user,
                         current_user=current_user)

@app.route('/message/delete/<int:message_id>')
@login_required
def delete_message(message_id):
    username = get_current_username()
    
    if db.delete_message(message_id, username):
        flash('تم حذف الرسالة بنجاح', 'success')
    else:
        flash('لم يتم العثور على الرسالة أو لا يمكن حذفها', 'error')
    
    return redirect(url_for('messages_inbox'))

@app.route('/message/delete_conversation/<int:ad_id>/<string:other_user>')
@login_required
def delete_conversation(ad_id, other_user):
    current_user = get_current_username()
    
    if db.delete_conversation(current_user, other_user, ad_id):
        flash('تم حذف المحادثة بنجاح', 'success')
    else:
        flash('حدث خطأ أثناء حذف المحادثة', 'error')
    
    return redirect(url_for('messages_inbox'))

@app.route('/api/unread-count')
@login_required
def api_unread_count():
    username = get_current_username()
    count = db.get_unread_count(username)
    return jsonify({'unread_count': count})

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('login'))

# ===== API endpoints =====
@app.route('/api/ads')
def api_get_ads():
    ads = db.get_all_ads()
    return jsonify([dict(ad) for ad in ads])

@app.route('/api/ads/<int:ad_id>')
def api_get_ad(ad_id):
    ad = db.get_ad_by_id(ad_id)
    if ad:
        return jsonify(dict(ad))
    return jsonify({'error': 'Ad not found'}), 404

# ===== معالجة الأخطاء =====
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

@app.errorhandler(413)
def too_large_error(error):
    flash('حجم الملف كبير جداً. الحد الأقصى 16MB لكل صورة', 'error')
    return redirect(request.url)

if __name__ == '__main__':
    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║      {SITE_NAME} - سوق الإعلانات المبوبة           ║
    ║                                                          ║
    ║      🚀 Server is running!                               ║
    ║      📍 http://127.0.0.1:5000                            ║
    ║                                                          ║
    ║      ⚡ Debug mode: ON                                   ║
    ║      📁 Upload folder: {UPLOAD_FOLDER}                  ║
    ║      💬 Messaging system: Enabled                        ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    app.run(debug=True)
