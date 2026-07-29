from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import json
import hashlib
import secrets
from werkzeug.utils import secure_filename
from PIL import Image
import io
import logging

# إعدادات التسجيل
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# إعدادات الأمان - استخدام متغيرات البيئة
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# إعدادات الملفات
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# إعدادات قاعدة البيانات - استخدام متغيرات البيئة
database_url = os.environ.get('DATABASE_URL', 'sqlite:///qashqish.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

db = SQLAlchemy(app)

# نماذج قاعدة البيانات
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    google_email = db.Column(db.String(120), unique=True, nullable=True)
    google_name = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_blocked = db.Column(db.Boolean, default=False)
    block_reason = db.Column(db.String(200), nullable=True)
    blocked_at = db.Column(db.DateTime, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100), nullable=True)

class Ad(db.Model):
    __tablename__ = 'ads'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.String(50), nullable=False)
    currency = db.Column(db.String(10), default='ليرة سورية')
    category = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    whatsapp = db.Column(db.String(20), nullable=True)
    images = db.Column(db.Text, nullable=True)  # JSON array
    username = db.Column(db.String(80), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    featured_until = db.Column(db.DateTime, nullable=True)
    report_count = db.Column(db.Integer, default=0)
    is_reported = db.Column(db.Boolean, default=False)
    report_reason = db.Column(db.String(200), nullable=True)
    reported_by = db.Column(db.String(80), nullable=True)

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(80), nullable=False)
    receiver = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    ad_id = db.Column(db.Integer, nullable=True)

class Favorite(db.Model):
    __tablename__ = 'favorites'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    ad_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BlockedUser(db.Model):
    __tablename__ = 'blocked_users'
    id = db.Column(db.Integer, primary_key=True)
    blocker = db.Column(db.String(80), nullable=False)
    blocked = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# دوال مساعدة
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_multiple_images(files):
    """حفظ الصور مع تحسين الحجم"""
    saved_paths = []
    try:
        # إنشاء المجلد إذا لم يكن موجوداً
        base_dir = os.path.dirname(os.path.abspath(__file__))
        upload_folder = os.path.join(base_dir, 'static', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        
        for file in files:
            if file and allowed_file(file.filename):
                # تنظيف اسم الملف
                filename = secure_filename(file.filename)
                # إضافة timestamp لتجنب التكرار
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')[:-3]
                unique_name = f"{timestamp}_{filename}"
                
                # ضغط الصورة
                img = Image.open(file)
                img.thumbnail((1200, 1200))
                
                # حفظ الصورة
                file_path = os.path.join(upload_folder, unique_name)
                if img.mode in ('RGBA', 'LA'):
                    img = img.convert('RGB')
                img.save(file_path, 'JPEG', quality=85, optimize=True)
                saved_paths.append(f'/static/uploads/{unique_name}')
                
        logger.info(f"تم حفظ {len(saved_paths)} صورة")
        return saved_paths
    except Exception as e:
        logger.error(f"خطأ في حفظ الصور: {str(e)}")
        return []

def get_user(username):
    """الحصول على مستخدم"""
    return User.query.filter_by(username=username).first()

def get_current_username():
    """الحصول على اسم المستخدم الحالي"""
    if 'username' in session:
        return session['username']
    elif 'google_email' in session:
        # محاولة العثور على مستخدم Google
        user = User.query.filter_by(google_email=session['google_email']).first()
        if user:
            return user.username
    return None

def get_user_by_username(username):
    return get_user(username)

def is_blocked(blocker, blocked):
    """التحقق من الحظر"""
    block = BlockedUser.query.filter_by(blocker=blocker, blocked=blocked).first()
    return block is not None

def get_unread_count(username):
    """عدد الرسائل غير المقروءة"""
    return Message.query.filter_by(receiver=username, is_read=False).count()

def hash_password(password):
    """تشفير كلمة المرور"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    """التحقق من كلمة المرور"""
    return hash_password(password) == hashed

# توجيهات الصفحات الرئيسية
@app.route('/')
def index():
    try:
        # جلب جميع الإعلانات النشطة
        ads = Ad.query.filter_by(is_active=True).order_by(Ad.date.desc()).all()
        
        # تحويل الصور من JSON إلى قائمة
        for ad in ads:
            if ad.images:
                try:
                    ad.images_list = json.loads(ad.images)
                except:
                    ad.images_list = []
            else:
                ad.images_list = []
        
        # جلب عدد الإعلانات لكل فئة
        categories = {}
        for ad in ads:
            categories[ad.category] = categories.get(ad.category, 0) + 1
        
        # جلب الإعلانات المميزة
        featured_ads = Ad.query.filter_by(is_featured=True, is_active=True).order_by(Ad.date.desc()).limit(6).all()
        
        return render_template('index.html', 
                             ads=ads, 
                             categories=categories, 
                             featured_ads=featured_ads,
                             get_unread_count=get_unread_count,
                             current_user=get_current_username(),
                             get_user_by_username=get_user_by_username)
    except Exception as e:
        logger.error(f"خطأ في الصفحة الرئيسية: {str(e)}")
        return render_template('index.html', ads=[], categories={}, featured_ads=[])

@app.route('/add_ad', methods=['GET', 'POST'])
def add_ad():
    try:
        username = get_current_username()
        if not username:
            flash('الرجاء تسجيل الدخول أولاً', 'danger')
            return redirect(url_for('login'))
        
        # التحقق من الحظر
        user = get_user(username)
        if user and user.is_blocked:
            flash('حسابك محظور. لا يمكنك إضافة إعلانات جديدة.', 'danger')
            return redirect(url_for('profile'))
        
        if request.method == 'POST':
            logger.info("بدء عملية إضافة إعلان")
            
            # جلب البيانات من النموذج
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            price = request.form.get('price', '').strip()
            currency = request.form.get('currency', 'ليرة سورية')
            category = request.form.get('category', '').strip()
            location = request.form.get('location', '').strip()
            phone = request.form.get('phone', '').strip()
            whatsapp = request.form.get('whatsapp', '').strip()
            
            # التحقق من البيانات
            if not all([title, description, price, category, location, phone]):
                flash('جميع الحقول المطلوبة يجب تعبئتها', 'danger')
                return render_template('add_ad.html')
            
            # معالجة الصور
            images = request.files.getlist('images')
            image_paths = []
            
            if images:
                image_paths = save_multiple_images(images)
                logger.info(f"تم حفظ {len(image_paths)} صورة")
            
            # حفظ الإعلان
            new_ad = Ad(
                title=title,
                description=description,
                price=price,
                currency=currency,
                category=category,
                location=location,
                phone=phone,
                whatsapp=whatsapp if whatsapp else None,
                images=json.dumps(image_paths) if image_paths else None,
                username=username,
                date=datetime.utcnow()
            )
            
            db.session.add(new_ad)
            db.session.commit()
            logger.info(f"تم نشر الإعلان بنجاح: {title}")
            
            flash('تم نشر الإعلان بنجاح!', 'success')
            return redirect(url_for('view_ad', ad_id=new_ad.id))
        
        return render_template('add_ad.html')
    
    except Exception as e:
        logger.error(f"خطأ في إضافة إعلان: {str(e)}")
        db.session.rollback()
        flash(f'حدث خطأ: {str(e)}', 'danger')
        return render_template('add_ad.html')

@app.route('/ad/<int:ad_id>')
def view_ad(ad_id):
    try:
        ad = Ad.query.get_or_404(ad_id)
        
        # زيادة عدد المشاهدات
        ad.views += 1
        db.session.commit()
        
        # تحويل الصور من JSON إلى قائمة
        if ad.images:
            try:
                ad.images_list = json.loads(ad.images)
            except:
                ad.images_list = []
        else:
            ad.images_list = []
        
        # جلب إعلانات مشابهة
        similar_ads = Ad.query.filter(
            Ad.category == ad.category,
            Ad.id != ad.id,
            Ad.is_active == True
        ).order_by(Ad.date.desc()).limit(5).all()
        
        for similar_ad in similar_ads:
            if similar_ad.images:
                try:
                    similar_ad.images_list = json.loads(similar_ad.images)
                except:
                    similar_ad.images_list = []
            else:
                similar_ad.images_list = []
        
        # التحقق من المفضلة
        username = get_current_username()
        is_favorited = False
        if username:
            favorite = Favorite.query.filter_by(username=username, ad_id=ad_id).first()
            is_favorited = favorite is not None
        
        return render_template('view_ad.html', 
                             ad=ad, 
                             similar_ads=similar_ads,
                             is_favorited=is_favorited,
                             current_user=username,
                             get_user_by_username=get_user_by_username)
    
    except Exception as e:
        logger.error(f"خطأ في عرض الإعلان: {str(e)}")
        flash('حدث خطأ في عرض الإعلان', 'danger')
        return redirect(url_for('index'))

@app.route('/favorite/<int:ad_id>', methods=['POST'])
def toggle_favorite(ad_id):
    try:
        username = get_current_username()
        if not username:
            return jsonify({'success': False, 'message': 'الرجاء تسجيل الدخول'}), 401
        
        favorite = Favorite.query.filter_by(username=username, ad_id=ad_id).first()
        
        if favorite:
            db.session.delete(favorite)
            db.session.commit()
            return jsonify({'success': True, 'favorited': False})
        else:
            new_favorite = Favorite(username=username, ad_id=ad_id)
            db.session.add(new_favorite)
            db.session.commit()
            return jsonify({'success': True, 'favorited': True})
    
    except Exception as e:
        logger.error(f"خطأ في المفضلة: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/my_ads')
def my_ads():
    username = get_current_username()
    if not username:
        flash('الرجاء تسجيل الدخول', 'danger')
        return redirect(url_for('login'))
    
    user_ads = Ad.query.filter_by(username=username).order_by(Ad.date.desc()).all()
    
    for ad in user_ads:
        if ad.images:
            try:
                ad.images_list = json.loads(ad.images)
            except:
                ad.images_list = []
        else:
            ad.images_list = []
    
    return render_template('my_ads.html', ads=user_ads, current_user=username)

@app.route('/delete_ad/<int:ad_id>', methods=['POST'])
def delete_ad(ad_id):
    try:
        username = get_current_username()
        if not username:
            flash('الرجاء تسجيل الدخول', 'danger')
            return redirect(url_for('login'))
        
        ad = Ad.query.get_or_404(ad_id)
        
        # التحقق من الملكية
        if ad.username != username:
            flash('ليس لديك صلاحية حذف هذا الإعلان', 'danger')
            return redirect(url_for('my_ads'))
        
        # حذف الصور من الملفات
        if ad.images:
            try:
                images = json.loads(ad.images)
                for img_path in images:
                    if img_path.startswith('/static/uploads/'):
                        full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), img_path[1:])
                        if os.path.exists(full_path):
                            os.remove(full_path)
            except:
                pass
        
        # حذف الإعلان
        db.session.delete(ad)
        db.session.commit()
        
        flash('تم حذف الإعلان بنجاح', 'success')
        return redirect(url_for('my_ads'))
    
    except Exception as e:
        logger.error(f"خطأ في حذف الإعلان: {str(e)}")
        flash(f'حدث خطأ: {str(e)}', 'danger')
        return redirect(url_for('my_ads'))

@app.route('/edit_ad/<int:ad_id>', methods=['GET', 'POST'])
def edit_ad(ad_id):
    try:
        username = get_current_username()
        if not username:
            flash('الرجاء تسجيل الدخول', 'danger')
            return redirect(url_for('login'))
        
        ad = Ad.query.get_or_404(ad_id)
        
        # التحقق من الملكية
        if ad.username != username:
            flash('ليس لديك صلاحية تعديل هذا الإعلان', 'danger')
            return redirect(url_for('my_ads'))
        
        if request.method == 'POST':
            # تحديث البيانات
            ad.title = request.form.get('title', '').strip()
            ad.description = request.form.get('description', '').strip()
            ad.price = request.form.get('price', '').strip()
            ad.currency = request.form.get('currency', 'ليرة سورية')
            ad.category = request.form.get('category', '').strip()
            ad.location = request.form.get('location', '').strip()
            ad.phone = request.form.get('phone', '').strip()
            ad.whatsapp = request.form.get('whatsapp', '').strip()
            
            # معالجة الصور الجديدة
            images = request.files.getlist('images')
            if images and images[0].filename:
                image_paths = save_multiple_images(images)
                if image_paths:
                    ad.images = json.dumps(image_paths)
            
            db.session.commit()
            flash('تم تحديث الإعلان بنجاح', 'success')
            return redirect(url_for('view_ad', ad_id=ad.id))
        
        # تحويل الصور للعرض
        if ad.images:
            try:
                ad.images_list = json.loads(ad.images)
            except:
                ad.images_list = []
        else:
            ad.images_list = []
        
        return render_template('edit_ad.html', ad=ad, current_user=username)
    
    except Exception as e:
        logger.error(f"خطأ في تعديل الإعلان: {str(e)}")
        flash(f'حدث خطأ: {str(e)}', 'danger')
        return redirect(url_for('my_ads'))

# مسارات المستخدم
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        phone = request.form.get('phone', '').strip()
        location = request.form.get('location', '').strip()
        
        # التحقق من البيانات
        if not all([username, email, password]):
            flash('جميع الحقول المطلوبة يجب تعبئتها', 'danger')
            return render_template('register.html')
        
        # التحقق من وجود المستخدم
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود مسبقاً', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('البريد الإلكتروني موجود مسبقاً', 'danger')
            return render_template('register.html')
        
        # إنشاء المستخدم
        hashed_password = hash_password(password)
        new_user = User(
            username=username,
            email=email,
            password=hashed_password,
            phone=phone,
            location=location
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('تم التسجيل بنجاح! يمكنك تسجيل الدخول الآن', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        user = User.query.filter_by(username=username).first()
        
        if user and verify_password(password, user.password):
            session['username'] = username
            session.permanent = True
            flash('تم تسجيل الدخول بنجاح!', 'success')
            return redirect(url_for('index'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('index'))

@app.route('/profile')
def profile():
    username = get_current_username()
    if not username:
        flash('الرجاء تسجيل الدخول', 'danger')
        return redirect(url_for('login'))
    
    user = get_user(username)
    if not user:
        session.clear()
        flash('المستخدم غير موجود', 'danger')
        return redirect(url_for('login'))
    
    # جلب إحصائيات المستخدم
    ads_count = Ad.query.filter_by(username=username).count()
    messages_count = Message.query.filter_by(receiver=username, is_read=False).count()
    favorites_count = Favorite.query.filter_by(username=username).count()
    
    return render_template('profile.html', 
                         user=user,
                         ads_count=ads_count,
                         messages_count=messages_count,
                         favorites_count=favorites_count,
                         current_user=username)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    username = get_current_username()
    if not username:
        flash('الرجاء تسجيل الدخول', 'danger')
        return redirect(url_for('login'))
    
    user = get_user(username)
    if not user:
        flash('المستخدم غير موجود', 'danger')
        return redirect(url_for('login'))
    
    # تحديث البيانات
    user.phone = request.form.get('phone', '').strip()
    user.location = request.form.get('location', '').strip()
    
    # تحديث كلمة المرور إذا تم إدخالها
    new_password = request.form.get('new_password', '').strip()
    if new_password:
        user.password = hash_password(new_password)
    
    db.session.commit()
    flash('تم تحديث الملف الشخصي بنجاح', 'success')
    return redirect(url_for('profile'))

# مسارات الرسائل
@app.route('/messages')
def messages():
    username = get_current_username()
    if not username:
        flash('الرجاء تسجيل الدخول', 'danger')
        return redirect(url_for('login'))
    
    # جلب المحادثات الفريدة
    conversations = db.session.query(
        Message.sender,
        Message.receiver,
        db.func.max(Message.timestamp).label('last_message_time')
    ).filter(
        db.or_(Message.sender == username, Message.receiver == username)
    ).group_by(
        db.func.least(Message.sender, Message.receiver),
        db.func.greatest(Message.sender, Message.receiver)
    ).order_by(db.desc('last_message_time')).all()
    
    # جلب تفاصيل المحادثات
    conversation_list = []
    for conv in conversations:
        other_user = conv.sender if conv.receiver == username else conv.receiver
        # تجنب عرض المحادثات مع النفس
        if other_user == username:
            continue
            
        # جلب آخر رسالة
        last_message = Message.query.filter(
            db.or_(
                db.and_(Message.sender == conv.sender, Message.receiver == conv.receiver),
                db.and_(Message.sender == conv.receiver, Message.receiver == conv.sender)
            )
        ).order_by(Message.timestamp.desc()).first()
        
        # عدد الرسائل غير المقروءة
        unread_count = Message.query.filter_by(
            sender=other_user,
            receiver=username,
            is_read=False
        ).count()
        
        conversation_list.append({
            'other_user': other_user,
            'last_message': last_message,
            'unread_count': unread_count,
            'last_message_time': conv.last_message_time
        })
    
    return render_template('messages.html', 
                         conversations=conversation_list,
                         current_user=username)

@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        username = get_current_username()
        if not username:
            return jsonify({'success': False, 'message': 'الرجاء تسجيل الدخول'}), 401
        
        receiver = request.form.get('receiver', '').strip()
        content = request.form.get('content', '').strip()
        ad_id = request.form.get('ad_id')
        
        if not receiver or not content:
            return jsonify({'success': False, 'message': 'البيانات غير مكتملة'}), 400
        
        # التحقق من الحظر
        if is_blocked(receiver, username):
            return jsonify({'success': False, 'message': 'لا يمكنك إرسال رسالة لهذا المستخدم'}), 403
        
        # حفظ الرسالة
        new_message = Message(
            sender=username,
            receiver=receiver,
            content=content,
            ad_id=int(ad_id) if ad_id else None
        )
        
        db.session.add(new_message)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم إرسال الرسالة'})
    
    except Exception as e:
        logger.error(f"خطأ في إرسال الرسالة: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/get_messages/<other_user>')
def get_messages(other_user):
    username = get_current_username()
    if not username:
        return jsonify({'error': 'غير مصرح'}), 401
    
    # جلب الرسائل بين المستخدمين
    messages = Message.query.filter(
        db.or_(
            db.and_(Message.sender == username, Message.receiver == other_user),
            db.and_(Message.sender == other_user, Message.receiver == username)
        )
    ).order_by(Message.timestamp.asc()).all()
    
    # تحديث حالة القراءة
    for msg in messages:
        if msg.receiver == username and not msg.is_read:
            msg.is_read = True
    db.session.commit()
    
    # تحويل إلى JSON
    messages_data = []
    for msg in messages:
        messages_data.append({
            'id': msg.id,
            'sender': msg.sender,
            'receiver': msg.receiver,
            'content': msg.content,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M'),
            'is_read': msg.is_read,
            'is_mine': msg.sender == username
        })
    
    return jsonify(messages_data)

@app.route('/delete_message/<int:msg_id>', methods=['POST'])
def delete_message(msg_id):
    try:
        username = get_current_username()
        if not username:
            return jsonify({'success': False, 'message': 'الرجاء تسجيل الدخول'}), 401
        
        msg = Message.query.get_or_404(msg_id)
        
        # التحقق من الملكية
        if msg.sender != username:
            return jsonify({'success': False, 'message': 'ليس لديك صلاحية'}), 403
        
        db.session.delete(msg)
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        logger.error(f"خطأ في حذف الرسالة: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# مسارات البحث
@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    location = request.args.get('location', '').strip()
    min_price = request.args.get('min_price', '').strip()
    max_price = request.args.get('max_price', '').strip()
    
    # بناء استعلام البحث
    search_query = Ad.query.filter_by(is_active=True)
    
    if query:
        search_query = search_query.filter(
            db.or_(
                Ad.title.ilike(f'%{query}%'),
                Ad.description.ilike(f'%{query}%')
            )
        )
    
    if category:
        search_query = search_query.filter_by(category=category)
    
    if location:
        search_query = search_query.filter_by(location=location)
    
    if min_price:
        search_query = search_query.filter(Ad.price >= min_price)
    
    if max_price:
        search_query = search_query.filter(Ad.price <= max_price)
    
    ads = search_query.order_by(Ad.date.desc()).all()
    
    # تحويل الصور
    for ad in ads:
        if ad.images:
            try:
                ad.images_list = json.loads(ad.images)
            except:
                ad.images_list = []
        else:
            ad.images_list = []
    
    return render_template('search.html', 
                         ads=ads, 
                         query=query,
                         category=category,
                         location=location,
                         current_user=get_current_username())

# مسارات الإدارة
@app.route('/admin')
def admin_panel():
    username = get_current_username()
    if not username:
        flash('الرجاء تسجيل الدخول', 'danger')
        return redirect(url_for('login'))
    
    user = get_user(username)
    if not user or not user.is_admin:
        flash('غير مصرح', 'danger')
        return redirect(url_for('index'))
    
    # جلب الإحصائيات
    total_users = User.query.count()
    total_ads = Ad.query.count()
    active_ads = Ad.query.filter_by(is_active=True).count()
    total_messages = Message.query.count()
    reported_ads = Ad.query.filter_by(is_reported=True).count()
    
    # جلب الإعلانات المبلغ عنها
    reported_ads_list = Ad.query.filter_by(is_reported=True).order_by(Ad.report_count.desc()).all()
    
    # جلب المستخدمين المحظورين
    blocked_users = User.query.filter_by(is_blocked=True).all()
    
    return render_template('admin.html',
                         total_users=total_users,
                         total_ads=total_ads,
                         active_ads=active_ads,
                         total_messages=total_messages,
                         reported_ads=reported_ads,
                         reported_ads_list=reported_ads_list,
                         blocked_users=blocked_users,
                         current_user=username)

@app.route('/admin/report_ad/<int:ad_id>', methods=['POST'])
def report_ad(ad_id):
    try:
        username = get_current_username()
        if not username:
            return jsonify({'success': False, 'message': 'الرجاء تسجيل الدخول'}), 401
        
        reason = request.form.get('reason', '').strip()
        if not reason:
            return jsonify({'success': False, 'message': 'الرجاء كتابة سبب البلاغ'}), 400
        
        ad = Ad.query.get_or_404(ad_id)
        
        # تحديث البلاغات
        ad.report_count += 1
        ad.is_reported = True
        ad.report_reason = reason
        ad.reported_by = username
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم إرسال البلاغ'})
    
    except Exception as e:
        logger.error(f"خطأ في الإبلاغ: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/block_user/<username>', methods=['POST'])
def block_user(username):
    admin_user = get_current_username()
    if not admin_user:
        return jsonify({'success': False, 'message': 'الرجاء تسجيل الدخول'}), 401
    
    admin = get_user(admin_user)
    if not admin or not admin.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح'}), 403
    
    user = get_user(username)
    if not user:
        return jsonify({'success': False, 'message': 'المستخدم غير موجود'}), 404
    
    # حظر المستخدم
    user.is_blocked = True
    user.block_reason = request.form.get('reason', 'تم الحظر من قبل الإدارة')
    user.blocked_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'تم حظر المستخدم {username}'})

@app.route('/admin/unblock_user/<username>', methods=['POST'])
def unblock_user(username):
    admin_user = get_current_username()
    if not admin_user:
        return jsonify({'success': False, 'message': 'الرجاء تسجيل الدخول'}), 401
    
    admin = get_user(admin_user)
    if not admin or not admin.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح'}), 403
    
    user = get_user(username)
    if not user:
        return jsonify({'success': False, 'message': 'المستخدم غير موجود'}), 404
    
    user.is_blocked = False
    user.block_reason = None
    user.blocked_at = None
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'تم إلغاء حظر المستخدم {username}'})

@app.route('/admin/delete_user/<username>', methods=['POST'])
def admin_delete_user(username):
    admin_user = get_current_username()
    if not admin_user:
        return jsonify({'success': False, 'message': 'الرجاء تسجيل الدخول'}), 401
    
    admin = get_user(admin_user)
    if not admin or not admin.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح'}), 403
    
    user = get_user(username)
    if not user:
        return jsonify({'success': False, 'message': 'المستخدم غير موجود'}), 404
    
    # حذف جميع إعلانات المستخدم
    Ad.query.filter_by(username=username).delete()
    
    # حذف جميع رسائل المستخدم
    Message.query.filter(
        db.or_(Message.sender == username, Message.receiver == username)
    ).delete()
    
    # حذف المفضلة
    Favorite.query.filter_by(username=username).delete()
    
    # حذف المستخدم
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'تم حذف المستخدم {username}'})

@app.route('/admin/toggle_featured/<int:ad_id>', methods=['POST'])
def toggle_featured(ad_id):
    admin_user = get_current_username()
    if not admin_user:
        return jsonify({'success': False, 'message': 'الرجاء تسجيل الدخول'}), 401
    
    admin = get_user(admin_user)
    if not admin or not admin.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح'}), 403
    
    ad = Ad.query.get_or_404(ad_id)
    
    ad.is_featured = not ad.is_featured
    if ad.is_featured:
        ad.featured_until = datetime.utcnow() + timedelta(days=7)
    else:
        ad.featured_until = None
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'تم تحديث حالة التميز'})

# إنشاء قاعدة البيانات
with app.app_context():
    db.create_all()
    
    # إنشاء مدير افتراضي إذا لم يكن موجوداً
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@example.com',
            password=hash_password('admin123'),
            is_admin=True,
            is_verified=True
        )
        db.session.add(admin)
        db.session.commit()
        logger.info("تم إنشاء حساب مدير افتراضي (admin/admin123)")

# تشغيل التطبيق
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
