"""
AluminoPro — PostgreSQL Edition (Render Deployment)
=====================================================
Setup on Render:
    1. Create PostgreSQL database on Render → copy the External Database URL
    2. Create Web Service → connect GitHub repo
    3. Build command : pip install -r requirements.txt
    4. Start command : gunicorn app:app
    5. Environment Variables:
         DATABASE_URL  = postgresql://... (your Render Postgres URL)
         SECRET_KEY    = any_random_string_here_min_32_chars

Photo placement (static/uploads/):
    hero.jpg, about.jpg, workshop.jpg, logo.png
    project1.jpg ... project6.jpg
    upi_qr.png  ← admin uploads via dashboard
"""

import os, hashlib, psycopg2, psycopg2.extras
from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
from functools import wraps

# ── Config ─────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')
# Render sometimes gives postgres:// — fix to postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change_this_in_render_env_vars')
app.permanent_session_lifetime = timedelta(minutes=15)  # Auto-logout after 15 min
app.config.update(
    SESSION_COOKIE_SECURE   = True,   # Render uses HTTPS
    SESSION_COOKIE_HTTPONLY = True,
    SESSION_COOKIE_SAMESITE = 'Lax',
    SESSION_COOKIE_NAME     = 'sharma_acp_session',
)
CORS(app, supports_credentials=True)

# ── Business Config ─────────────────────────────────────────────────────────────
# ── Sharma ACP — Dhanbad, Jharkhand ─────────────────────────────────────────────
UPI_ID   = '9508777145@apl'
UPI_NAME = 'Sandeep Sharma'

# ── Default rates (admin can update these via dashboard → Rate Management) ──────
SERVICE_RATES = {
    'Aluminum Windows (Single Glass)': 350,
    'Aluminum Windows (Double Glass)': 500,
    'Aluminum Sliding Door':           400,
    'Aluminum Casement Door':          450,
    'ACP Cladding (Standard 3mm)':     230,
    'ACP Cladding (FR Grade 4mm)':     290,
    'Glass Office Partition':          550,
    'Structural Glazing Facade':       1100,
    'Shopfront Aluminum Frame':        650,
    'Skylight / Canopy':               1200,
}

def get_live_rates():
    """Returns rates from DB if admin has overridden them, else default SERVICE_RATES."""
    try:
        conn = get_db()
        rows = fetchall(conn, "SELECT service_name, rate FROM service_rates")
        conn.close()
        if rows:
            return {r['service_name']: float(r['rate']) for r in rows}
    except Exception:
        pass
    return SERVICE_RATES
COLOR_OPTIONS = [
    'Silver (Mill Finish)', 'Powder Coated White', 'Powder Coated Black',
    'Powder Coated Bronze', 'Powder Coated Champagne', 'Anodized Silver',
    'Anodized Bronze', 'Anodized Gold', 'Wooden Finish (PVDF)', 'Custom Color',
]
GLASS_OPTIONS = [
    '5mm Clear Glass', '8mm Clear Glass', '10mm Clear Glass',
    '5mm Tinted (Grey)', '5mm Tinted (Blue)', '5mm Frosted',
    'DGU (5+12+5mm)', 'DGU (6+12+6mm)', 'Tempered 10mm', 'Laminated Glass',
]
CANCEL_TERMS = [
    "Cancellation is only allowed if work has NOT started (status: Pending).",
    "Orders with 'Running' or 'Done' status cannot be cancelled.",
    "If an advance payment was made, a 10% processing fee will be deducted.",
    "Refund (if applicable) will be processed within 5–7 business days.",
    "Cancellation request will be reviewed by admin within 24 hours.",
    "By submitting, you agree to these terms and conditions.",
]

# ── DB Helpers (psycopg2 + RealDictCursor) ─────────────────────────────────────
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def fetchone(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None

def fetchall(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]

def scalar(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    return list(dict(row).values())[0] if row else None

def run(conn, sql, params=()):
    conn.cursor().execute(sql, params)

def serialize(obj):
    """Convert datetime objects to strings for JSON serialisation."""
    if isinstance(obj, dict):
        return {k: (str(v) if isinstance(v, datetime) else v) for k, v in obj.items()}
    return obj

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

# ── Auth Decorators ─────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*a, **kw)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session or session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*a, **kw)
    return d

# ── Database Init (PostgreSQL DDL) ─────────────────────────────────────────────
def init_db():
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         SERIAL PRIMARY KEY,
            name       TEXT        NOT NULL,
            email      TEXT UNIQUE NOT NULL,
            phone      TEXT        DEFAULT '',
            password   TEXT        NOT NULL,
            role       TEXT        DEFAULT 'user',
            address    TEXT        DEFAULT '',
            dp_url     TEXT        DEFAULT '',
            created_at TIMESTAMP   DEFAULT NOW(),
            last_login TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id             SERIAL  PRIMARY KEY,
            user_id        INTEGER NOT NULL REFERENCES users(id),
            service_type   TEXT    NOT NULL,
            description    TEXT    DEFAULT '',
            width_ft       REAL    DEFAULT 0,
            height_ft      REAL    DEFAULT 0,
            custom_sqft    REAL    DEFAULT 0,
            quantity       INTEGER DEFAULT 1,
            unit           TEXT    DEFAULT 'sqft',
            color_finish   TEXT    DEFAULT '',
            glass_type     TEXT    DEFAULT '',
            estimated_area TEXT    DEFAULT '',
            address        TEXT    DEFAULT '',
            preferred_date TEXT    DEFAULT '',
            status         TEXT    DEFAULT 'pending',
            admin_note     TEXT    DEFAULT '',
            base_rate      REAL    DEFAULT 0,
            total_amount   REAL    DEFAULT 0,
            payment_status TEXT    DEFAULT 'unpaid',
            cancel_requested INTEGER DEFAULT 0,
            created_at     TIMESTAMP DEFAULT NOW(),
            updated_at     TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id         SERIAL  PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            name       TEXT    NOT NULL,
            phone      TEXT    NOT NULL,
            service    TEXT    NOT NULL,
            date       TEXT    NOT NULL,
            time_slot  TEXT    NOT NULL,
            message    TEXT    DEFAULT '',
            status     TEXT    DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id         SERIAL  PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            order_id   INTEGER REFERENCES orders(id),
            rating     INTEGER NOT NULL,
            comment    TEXT    DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id         SERIAL  PRIMARY KEY,
            name       TEXT    NOT NULL,
            email      TEXT    NOT NULL,
            phone      TEXT    DEFAULT '',
            subject    TEXT    DEFAULT '',
            message    TEXT    NOT NULL,
            is_read    INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS blog_posts (
            id         SERIAL  PRIMARY KEY,
            title      TEXT    NOT NULL,
            content    TEXT    NOT NULL,
            excerpt    TEXT    DEFAULT '',
            image_url  TEXT    DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cancel_requests (
            id           SERIAL  PRIMARY KEY,
            order_id     INTEGER NOT NULL REFERENCES orders(id),
            user_id      INTEGER NOT NULL REFERENCES users(id),
            reason       TEXT    NOT NULL,
            agreed_terms INTEGER DEFAULT 0,
            status       TEXT    DEFAULT 'pending',
            admin_note   TEXT    DEFAULT '',
            created_at   TIMESTAMP DEFAULT NOW(),
            updated_at   TIMESTAMP DEFAULT NOW()
        )
    """)

    # ── Seed admin user ──────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO users (name, email, password, role, phone)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (email) DO NOTHING
    """, ('Admin', 'admin@aluminiumpro.com', hash_password('admin123'), 'admin', '9955744336'))

    # ── Seed blog posts ──────────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) AS cnt FROM blog_posts")
    if cur.fetchone()['cnt'] == 0:
        blog_data = [
            ('Why Aluminum Windows Are Better Than Wood',
             'Aluminum windows offer unparalleled durability and weather resistance. They require minimal maintenance, do not warp or rot, and provide excellent thermal performance. Modern aluminum windows come in powder-coated finishes that mimic wood grain while providing decades of service life.',
             'Discover why aluminum is the smart choice for modern homes and offices.'),
            ('ACP Cladding: Transforming Building Facades',
             'Aluminium Composite Panels have revolutionized building exteriors. These panels consist of two thin aluminium layers sandwiching a polyethylene core. They offer excellent weather resistance, can be easily shaped, and come in thousands of colors and finishes.',
             'How ACP panels are changing the face of modern architecture.'),
            ('Top 5 Glass Partition Trends for Modern Offices',
             'Top trends: 1) Frameless glass walls 2) Frosted film for privacy 3) Sliding glass doors 4) Integrated blinds within DGU 5) Curved glass partitions.',
             'Transform your workspace with cutting-edge glass partition designs.'),
        ]
        for title, content, excerpt in blog_data:
            cur.execute(
                "INSERT INTO blog_posts (title, content, excerpt) VALUES (%s, %s, %s)",
                (title, content, excerpt)
            )

    # ── Service rates table (admin can edit via dashboard) ─────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS service_rates (
            id           SERIAL PRIMARY KEY,
            service_name TEXT   UNIQUE NOT NULL,
            rate         REAL   NOT NULL,
            material     TEXT   DEFAULT '',
            lead_time    TEXT   DEFAULT '',
            min_order    TEXT   DEFAULT '',
            updated_at   TIMESTAMP DEFAULT NOW()
        )
    """)

    # Seed default rates if table is empty
    cur.execute("SELECT COUNT(*) AS cnt FROM service_rates")
    if cur.fetchone()['cnt'] == 0:
        default_rates = [
            ('Aluminum Windows (Single Glass)', 350,  '6063 Alloy + 5mm Clear Glass',     '7–10 days',  '10 sqft'),
            ('Aluminum Windows (Double Glass)', 500,  '6063 Alloy + DGU 5+12+5mm',        '10–14 days', '10 sqft'),
            ('Aluminum Sliding Door',           400,  'Heavy Section + 8mm Glass',         '7–12 days',  '20 sqft'),
            ('Aluminum Casement Door',          450,  'Heavy Section + Glass',             '7–12 days',  '15 sqft'),
            ('ACP Cladding (Standard 3mm)',     230,  '3mm ACP + Aluminium Framework',     '5–7 days',   '50 sqft'),
            ('ACP Cladding (FR Grade 4mm)',     290,  '4mm FR ACP + Framework',            '5–7 days',   '50 sqft'),
            ('Glass Office Partition',          550,  'Aluminium Frame + 10mm Glass',      '10–15 days', '30 sqft'),
            ('Structural Glazing Facade',       1100, 'Structural Silicone + DGU',         '15–21 days', '100 sqft'),
            ('Shopfront Aluminum Frame',        650,  'Box Section + Glass',               '7–10 days',  '40 sqft'),
            ('Skylight / Canopy',               1200, 'Special Section + Toughened Glass', '14–21 days', '20 sqft'),
        ]
        for row in default_rates:
            cur.execute("""
                INSERT INTO service_rates (service_name, rate, material, lead_time, min_order)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (service_name) DO NOTHING
            """, row)

    conn.commit()
    conn.close()
    print("✅ PostgreSQL DB initialised")

# ══════════════════════════════════════════════════════════════════════════════
# STATIC FILES
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route('/api/photos')
def get_photos():
    names = ['hero','about','workshop','logo','project1','project2',
             'project3','project4','project5','project6']
    exts  = ['.jpg','.jpeg','.png','.webp']
    found = {}
    for name in names:
        for ext in exts:
            if os.path.exists(os.path.join(UPLOAD_DIR, name + ext)):
                found[name] = f'/static/uploads/{name}{ext}'
                break
    return jsonify(found)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/signup')
def signup_page():
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('admin.html' if session.get('role') == 'admin' else 'user_dashboard.html')

@app.route('/admin')
def admin_panel():
    if session.get('role') != 'admin':
        return redirect('/login')
    return render_template('admin.html')

# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (name, email, phone, password, address)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (email) DO NOTHING
            RETURNING id
        """, (data['name'], data['email'], data.get('phone',''),
              hash_password(data['password']), data.get('address','')))
        row = cur.fetchone()
        conn.commit()
        conn.close()
        if not row:
            return jsonify({'success': False, 'message': 'Email already registered.'})
        return jsonify({'success': True, 'message': 'Account created successfully!'})
    except Exception as e:
        try: conn.rollback()
        except: pass
        conn.close()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    conn = get_db()
    user = fetchone(conn,
        "SELECT * FROM users WHERE email=%s AND password=%s",
        (data['email'], hash_password(data['password']))
    )
    if user:
        session.permanent = True
        session.update({
            'user_id': user['id'],
            'name':    user['name'],
            'role':    user['role'],
            'email':   user['email'],
        })
        run(conn, "UPDATE users SET last_login=%s WHERE id=%s", (datetime.now(), user['id']))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'role': user['role'], 'name': user['name']})
    conn.close()
    return jsonify({'success': False, 'message': 'Invalid email or password.'})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/me')
def me():
    if 'user_id' not in session:
        return jsonify({'logged_in': False})
    conn = get_db()
    user = fetchone(conn,
        "SELECT id,name,email,phone,address,role,dp_url,created_at,last_login FROM users WHERE id=%s",
        (session['user_id'],)
    )
    conn.close()
    if user:
        return jsonify({'logged_in': True, 'user': serialize(user)})
    return jsonify({'logged_in': False})

@app.route('/api/update_profile', methods=['POST'])
@login_required
def update_profile():
    data = request.json
    conn = get_db()
    run(conn,
        "UPDATE users SET name=%s, phone=%s, address=%s WHERE id=%s",
        (data['name'], data['phone'], data['address'], session['user_id'])
    )
    conn.commit()
    conn.close()
    session['name'] = data['name']
    return jsonify({'success': True, 'message': 'Profile updated!'})

# ── User: Upload profile photo ──────────────────────────────────────────────────
@app.route('/api/user/upload-dp', methods=['POST'])
@login_required
def upload_dp():
    if 'dp' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'})
    f   = request.files['dp']
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
        return jsonify({'success': False, 'message': 'Only JPG/PNG/WEBP allowed'})
    # Remove old DP files for this user
    for old_ext in ['.jpg', '.jpeg', '.png', '.webp']:
        old = os.path.join(UPLOAD_DIR, f'dp_{session["user_id"]}{old_ext}')
        if os.path.exists(old):
            os.remove(old)
    filename = f'dp_{session["user_id"]}{ext}'
    f.save(os.path.join(UPLOAD_DIR, filename))
    dp_url = f'/static/uploads/{filename}'
    conn = get_db()
    run(conn, "UPDATE users SET dp_url=%s WHERE id=%s", (dp_url, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'dp_url': dp_url})

# ══════════════════════════════════════════════════════════════════════════════
# RATES & CALCULATOR
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/rates')
def get_rates():
    return jsonify({'rates': get_live_rates(), 'colors': COLOR_OPTIONS, 'glass': GLASS_OPTIONS})

@app.route('/api/rates/full')
def get_rates_full():
    """Returns full rate data including material, lead_time, min_order for admin table."""
    try:
        conn = get_db()
        rows = fetchall(conn, "SELECT id, service_name, rate, material, lead_time, min_order, updated_at FROM service_rates ORDER BY id")
        conn.close()
        if rows:
            return jsonify({'rates': [serialize(r) for r in rows]})
    except Exception:
        pass
    # Fallback to defaults
    return jsonify({'rates': [
        {'service_name': k, 'rate': v,
         'material': '', 'lead_time': '', 'min_order': '', 'updated_at': None}
        for k, v in SERVICE_RATES.items()
    ]})

@app.route('/api/admin/rates', methods=['PUT'])
@admin_required
def update_rate():
    """Admin updates a single service rate."""
    data      = request.json
    service   = data.get('service_name', '')
    rate_val  = float(data.get('rate', 0))
    material  = data.get('material',  '')
    lead_time = data.get('lead_time', '')
    min_order = data.get('min_order', '')
    if not service or rate_val <= 0:
        return jsonify({'success': False, 'message': 'Service name and a valid rate are required'})
    conn = get_db()
    run(conn, """
        INSERT INTO service_rates (service_name, rate, material, lead_time, min_order, updated_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (service_name) DO UPDATE
        SET rate=%s, material=%s, lead_time=%s, min_order=%s, updated_at=NOW()
    """, (service, rate_val, material, lead_time, min_order,
             rate_val, material, lead_time, min_order))
    conn.commit()
    conn.close()
    SERVICE_RATES[service] = rate_val   # update in-memory immediately
    return jsonify({'success': True, 'message': f'Rate updated: {service} → ₹{rate_val}/sqft'})

@app.route('/api/admin/rates/reset', methods=['POST'])
@admin_required
def reset_rates():
    """Reset all rates to default values."""
    conn = get_db()
    run(conn, "DELETE FROM service_rates")
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Rates reset to defaults. Restart to reload.'})

@app.route('/api/calculate', methods=['POST'])
def calculate_price():
    data    = request.json
    service = data.get('service_type', '')
    live_rates = get_live_rates()
    if service not in live_rates:
        return jsonify({'error': 'Unknown service type'}), 400
    rate       = live_rates[service]
    width      = float(data.get('width_ft',    0) or 0)
    height     = float(data.get('height_ft',   0) or 0)
    csqft      = float(data.get('custom_sqft', 0) or 0)
    qty        = max(1, int(data.get('quantity', 1) or 1))
    sqft_per   = csqft if csqft > 0 else (width * height)
    total_sqft = round(sqft_per * qty, 2)
    price      = total_sqft * rate
    gst        = round(price * 0.18)
    return jsonify({
        'sqft_per_unit': round(sqft_per, 2),
        'total_sqft':    total_sqft,
        'quantity':      qty,
        'rate':          rate,
        'price':         round(price),
        'gst':           gst,
        'total_with_gst':round(price + gst),
    })

# ══════════════════════════════════════════════════════════════════════════════
# UPI PAYMENT
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/payment/info')
def payment_info():
    return jsonify({'upi_id': UPI_ID, 'upi_name': UPI_NAME})

@app.route('/api/payment/qr-image')
def get_qr_image():
    """Returns the custom QR photo URL if admin has uploaded one."""
    for ext in ['.jpg', '.jpeg', '.png', '.webp']:
        path = os.path.join(UPLOAD_DIR, 'upi_qr' + ext)
        if os.path.exists(path):
            return jsonify({'url': f'/static/uploads/upi_qr{ext}', 'custom': True})
    return jsonify({'url': None, 'custom': False})

# ── Admin: Upload custom UPI QR photo ──────────────────────────────────────────
@app.route('/api/admin/upload-qr', methods=['POST'])
@admin_required
def upload_qr():
    if 'qr' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'})
    f   = request.files['qr']
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
        return jsonify({'success': False, 'message': 'Only JPG/PNG/WEBP allowed'})
    # Remove old QR files
    for old_ext in ['.jpg', '.jpeg', '.png', '.webp']:
        old = os.path.join(UPLOAD_DIR, 'upi_qr' + old_ext)
        if os.path.exists(old):
            os.remove(old)
    f.save(os.path.join(UPLOAD_DIR, 'upi_qr' + ext))
    return jsonify({'success': True, 'message': 'QR uploaded!', 'url': f'/static/uploads/upi_qr{ext}'})

# ══════════════════════════════════════════════════════════════════════════════
# ORDERS
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/orders', methods=['POST'])
@login_required
def create_order():
    data    = request.json
    service = data.get('service_type', '')
    width   = float(data.get('width_ft',    0) or 0)
    height  = float(data.get('height_ft',   0) or 0)
    csqft   = float(data.get('custom_sqft', 0) or 0)
    qty     = max(1, int(data.get('quantity', 1) or 1))
    sqft_per   = csqft if csqft > 0 else (width * height)
    total_sqft = round(sqft_per * qty, 2)
    live = get_live_rates()
    base_rate  = live.get(service, 0) if isinstance(live.get(service,0), (int,float)) else live.get(service, {}).get('min', 0)
    est_area   = f"{total_sqft} sqft" if total_sqft else data.get('estimated_area', '')
    conn = get_db()
    run(conn, """
        INSERT INTO orders
            (user_id, service_type, description, width_ft, height_ft, custom_sqft,
             quantity, unit, color_finish, glass_type, estimated_area, address,
             preferred_date, base_rate, total_amount)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        session['user_id'], service, data.get('description', ''),
        width, height, csqft, qty, 'sqft',
        data.get('color_finish', ''), data.get('glass_type', ''),
        est_area, data.get('address', ''), data.get('preferred_date', ''),
        base_rate, round(total_sqft * base_rate)
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Order placed! We will confirm pricing and contact you soon.'})

@app.route('/api/orders/my')
@login_required
def my_orders():
    conn   = get_db()
    orders = fetchall(conn,
        "SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC",
        (session['user_id'],)
    )
    conn.close()
    return jsonify([serialize(o) for o in orders])

@app.route('/api/orders/all')
@admin_required
def all_orders():
    conn   = get_db()
    orders = fetchall(conn, """
        SELECT o.*, u.name AS user_name, u.email, u.phone
        FROM orders o JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC
    """)
    conn.close()
    return jsonify([serialize(o) for o in orders])

@app.route('/api/orders/<int:oid>/status', methods=['PUT'])
@admin_required
def update_order_status(oid):
    data = request.json
    conn = get_db()
    run(conn, """
        UPDATE orders
        SET status=%s, admin_note=%s, total_amount=%s, payment_status=%s, updated_at=%s
        WHERE id=%s
    """, (
        data['status'], data.get('admin_note', ''),
        data.get('total_amount', 0), data.get('payment_status', 'unpaid'),
        datetime.now(), oid
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/orders/<int:oid>/payment', methods=['PUT'])
@admin_required
def update_payment_status(oid):
    data = request.json
    conn = get_db()
    run(conn,
        "UPDATE orders SET payment_status=%s, updated_at=%s WHERE id=%s",
        (data['payment_status'], datetime.now(), oid)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/orders/<int:oid>', methods=['DELETE'])
@admin_required
def delete_order(oid):
    conn = get_db()
    run(conn, "DELETE FROM feedback       WHERE order_id=%s", (oid,))
    run(conn, "DELETE FROM cancel_requests WHERE order_id=%s", (oid,))
    run(conn, "DELETE FROM orders          WHERE id=%s",       (oid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Order #{oid} deleted'})

# ══════════════════════════════════════════════════════════════════════════════
# APPOINTMENTS
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/appointments', methods=['POST'])
@login_required
def book_appointment():
    data = request.json
    conn = get_db()
    run(conn,
        "INSERT INTO appointments (user_id,name,phone,service,date,time_slot,message) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (session['user_id'], data['name'], data['phone'],
         data['service'], data['date'], data['time_slot'], data.get('message', ''))
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Appointment booked!'})

@app.route('/api/appointments/all')
@admin_required
def all_appointments():
    conn  = get_db()
    appts = fetchall(conn, """
        SELECT a.*, u.email
        FROM appointments a JOIN users u ON a.user_id = u.id
        ORDER BY a.created_at DESC
    """)
    conn.close()
    return jsonify([serialize(a) for a in appts])

@app.route('/api/appointments/<int:aid>/status', methods=['PUT'])
@admin_required
def update_appt_status(aid):
    data = request.json
    conn = get_db()
    run(conn, "UPDATE appointments SET status=%s WHERE id=%s", (data['status'], aid))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ══════════════════════════════════════════════════════════════════════════════
# FEEDBACK
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/feedback', methods=['POST'])
@login_required
def submit_feedback():
    data = request.json
    conn = get_db()
    run(conn,
        "INSERT INTO feedback (user_id,order_id,rating,comment) VALUES (%s,%s,%s,%s)",
        (session['user_id'], data.get('order_id') or None,
         data['rating'], data.get('comment', ''))
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Thank you for your feedback!'})

@app.route('/api/feedback/all')
@admin_required
def all_feedback():
    conn = get_db()
    fb   = fetchall(conn, """
        SELECT f.*, u.name, u.email
        FROM feedback f JOIN users u ON f.user_id = u.id
        ORDER BY f.created_at DESC
    """)
    conn.close()
    return jsonify([serialize(f) for f in fb])

# ══════════════════════════════════════════════════════════════════════════════
# CONTACT
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/contact', methods=['POST'])
def contact():
    data = request.json
    conn = get_db()
    run(conn,
        "INSERT INTO contact_messages (name,email,phone,subject,message) VALUES (%s,%s,%s,%s,%s)",
        (data['name'], data['email'], data.get('phone',''), data.get('subject',''), data['message'])
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Message sent! We will reply shortly.'})

@app.route('/api/contact/all')
@admin_required
def all_contacts():
    conn = get_db()
    msgs = fetchall(conn, "SELECT * FROM contact_messages ORDER BY created_at DESC")
    conn.close()
    return jsonify([serialize(m) for m in msgs])

@app.route('/api/contact/<int:mid>/read', methods=['PUT'])
@admin_required
def mark_read(mid):
    conn = get_db()
    run(conn, "UPDATE contact_messages SET is_read=1 WHERE id=%s", (mid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ══════════════════════════════════════════════════════════════════════════════
# BLOG
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/blog')
def get_blog():
    conn  = get_db()
    posts = fetchall(conn, "SELECT * FROM blog_posts ORDER BY created_at DESC")
    conn.close()
    return jsonify([serialize(p) for p in posts])

# ══════════════════════════════════════════════════════════════════════════════
# CANCEL ORDER
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/cancel-terms')
def get_cancel_terms():
    return jsonify({'terms': CANCEL_TERMS})

@app.route('/api/orders/<int:oid>/cancel-request', methods=['POST'])
@login_required
def request_cancel(oid):
    data = request.json
    if not data.get('agreed_terms'):
        return jsonify({'success': False, 'message': 'You must agree to the terms to cancel.'})
    if not data.get('reason', '').strip():
        return jsonify({'success': False, 'message': 'Please provide a reason for cancellation.'})
    conn = get_db()
    order = fetchone(conn, "SELECT * FROM orders WHERE id=%s AND user_id=%s", (oid, session['user_id']))
    if not order:
        conn.close()
        return jsonify({'success': False, 'message': 'Order not found.'})
    if order['status'] in ('done', 'cancelled'):
        conn.close()
        return jsonify({'success': False, 'message': f'Order is already {order["status"]} — cannot cancel.'})
    if order['status'] == 'running':
        conn.close()
        return jsonify({'success': False, 'message': 'Order is running. Please contact us directly.'})
    existing = fetchone(conn, "SELECT id FROM cancel_requests WHERE order_id=%s AND status='pending'", (oid,))
    if existing:
        conn.close()
        return jsonify({'success': False, 'message': 'A cancellation request is already pending.'})
    run(conn,
        "INSERT INTO cancel_requests (order_id,user_id,reason,agreed_terms) VALUES (%s,%s,%s,%s)",
        (oid, session['user_id'], data['reason'], 1)
    )
    run(conn, "UPDATE orders SET cancel_requested=1 WHERE id=%s", (oid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cancellation request submitted. Admin will review within 24 hours.'})

@app.route('/api/cancel-requests/all')
@admin_required
def all_cancel_requests():
    conn = get_db()
    reqs = fetchall(conn, """
        SELECT cr.*, o.service_type, o.status AS order_status, o.total_amount,
               u.name AS user_name, u.email, u.phone
        FROM cancel_requests cr
        JOIN orders o ON cr.order_id = o.id
        JOIN users  u ON cr.user_id  = u.id
        ORDER BY cr.created_at DESC
    """)
    conn.close()
    return jsonify([serialize(r) for r in reqs])

@app.route('/api/cancel-requests/<int:rid>/action', methods=['PUT'])
@admin_required
def handle_cancel_request(rid):
    data   = request.json
    action = data.get('action')  # 'approve' | 'reject'
    note   = data.get('admin_note', '')
    conn   = get_db()
    req    = fetchone(conn, "SELECT * FROM cancel_requests WHERE id=%s", (rid,))
    if not req:
        conn.close()
        return jsonify({'success': False, 'message': 'Request not found'})
    new_status = 'approved' if action == 'approve' else 'rejected'
    run(conn,
        "UPDATE cancel_requests SET status=%s, admin_note=%s, updated_at=%s WHERE id=%s",
        (new_status, note, datetime.now(), rid)
    )
    if action == 'approve':
        run(conn, """
            UPDATE orders
            SET status='cancelled', payment_status='refund_pending',
                cancel_requested=0, admin_note=%s, updated_at=%s
            WHERE id=%s
        """, (f'Cancelled: {note}' if note else 'Cancelled by Sharma ACP admin', datetime.now(), req['order_id']))
    else:
        run(conn, "UPDATE orders SET cancel_requested=0 WHERE id=%s", (req['order_id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Request {new_status}!'})

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — USER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    conn  = get_db()
    avg   = scalar(conn, "SELECT AVG(rating) FROM feedback")
    users = fetchall(conn,
        "SELECT id,name,email,phone,role,dp_url,created_at,last_login FROM users ORDER BY created_at DESC"
    )
    stats = {
        'total_users':          scalar(conn, "SELECT COUNT(*) FROM users WHERE role='user'"),
        'total_orders':         scalar(conn, "SELECT COUNT(*) FROM orders"),
        'pending_orders':       scalar(conn, "SELECT COUNT(*) FROM orders WHERE status='pending'"),
        'running_orders':       scalar(conn, "SELECT COUNT(*) FROM orders WHERE status='running'"),
        'done_orders':          scalar(conn, "SELECT COUNT(*) FROM orders WHERE status='done'"),
        'total_appointments':   scalar(conn, "SELECT COUNT(*) FROM appointments"),
        'unread_messages':      scalar(conn, "SELECT COUNT(*) FROM contact_messages WHERE is_read=0"),
        'avg_rating':           round(float(avg), 1) if avg else 0,
        'pending_cancellations':scalar(conn, "SELECT COUNT(*) FROM cancel_requests WHERE status='pending'") or 0,
        'all_users':            [serialize(u) for u in users],
    }
    conn.close()
    return jsonify(stats)

@app.route('/api/admin/user/<int:uid>')
@admin_required
def admin_get_user(uid):
    conn   = get_db()
    user   = fetchone(conn, "SELECT * FROM users WHERE id=%s", (uid,))
    if not user:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    user.pop('password', None)
    orders = fetchall(conn, "SELECT * FROM orders       WHERE user_id=%s ORDER BY created_at DESC", (uid,))
    appts  = fetchall(conn, "SELECT * FROM appointments WHERE user_id=%s ORDER BY created_at DESC", (uid,))
    fbs    = fetchall(conn, "SELECT * FROM feedback     WHERE user_id=%s ORDER BY created_at DESC", (uid,))
    conn.close()
    return jsonify({
        'user':         serialize(user),
        'orders':       [serialize(o) for o in orders],
        'appointments': [serialize(a) for a in appts],
        'feedback':     [serialize(f) for f in fbs],
    })

@app.route('/api/admin/user/<int:uid>', methods=['PUT'])
@admin_required
def admin_edit_user(uid):
    data   = request.json
    conn   = get_db()
    fields, values = [], []
    for col in ['name', 'email', 'phone', 'address', 'role']:
        if col in data:
            fields.append(f"{col}=%s")
            values.append(data[col])
    if data.get('password'):
        fields.append("password=%s")
        values.append(hash_password(data['password']))
    if not fields:
        conn.close()
        return jsonify({'success': False, 'message': 'Nothing to update'})
    values.append(uid)
    run(conn, f"UPDATE users SET {', '.join(fields)} WHERE id=%s", values)
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'User updated!'})

@app.route('/api/admin/user/<int:uid>', methods=['DELETE'])
@admin_required
def admin_delete_user(uid):
    if uid == session['user_id']:
        return jsonify({'success': False, 'message': 'Cannot delete your own admin account'})
    conn = get_db()
    run(conn, "DELETE FROM feedback        WHERE user_id=%s", (uid,))
    run(conn, "DELETE FROM appointments    WHERE user_id=%s", (uid,))
    run(conn, "DELETE FROM cancel_requests WHERE user_id=%s", (uid,))
    # Reassign orders to admin (id=1) so we don't lose data
    run(conn, "UPDATE orders SET user_id=1 WHERE user_id=%s", (uid,))
    run(conn, "DELETE FROM users WHERE id=%s", (uid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'User deleted'})

# ══════════════════════════════════════════════════════════════════════════════
# INVOICE
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/api/invoice/<int:oid>')
@login_required
def get_invoice(oid):
    conn  = get_db()
    order = fetchone(conn, """
        SELECT o.*, u.name, u.email, u.phone, u.address AS user_address
        FROM orders o JOIN users u ON o.user_id = u.id
        WHERE o.id = %s
    """, (oid,))
    conn.close()
    if not order:
        return jsonify({'error': 'Not found'}), 404
    if session.get('role') != 'admin' and order.get('user_id') != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify(serialize(order))

# ══════════════════════════════════════════════════════════════════════════════
# STARTUP — init_db() at MODULE LEVEL so gunicorn also initialises the DB
# ══════════════════════════════════════════════════════════════════════════════
try:
    init_db()
except Exception as _startup_err:
    print(f"⚠️  init_db error: {_startup_err}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)