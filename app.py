import os
import json
import random
import string
import base64
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from db import (
    get_db, init_db, create_user, get_user_by_email, get_user_by_id,
    create_order, get_order, get_all_orders, update_order, delete_order, search_orders,
    get_setting, set_setting, is_supabase_enabled,
    create_product, get_product, get_all_products, get_products_by_section, update_product, delete_product
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(os.path.join(UPLOAD_FOLDER, 'products'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'artworks'), exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'svg'}

def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def handle_image_storage(file_storage, fallback_url=''):
    """Saves uploaded image file to static/uploads/products and returns the URL or base64 URI, or fallback_url."""
    if file_storage and file_storage.filename and allowed_image_file(file_storage.filename):
        sec_name = secure_filename(file_storage.filename)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        filename = f"{timestamp}_{rand_suffix}_{sec_name}"
        upload_dir = os.path.join(UPLOAD_FOLDER, 'products')
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)
        file_storage.save(file_path)
        
        # Check file size for base64 data URI resilience in serverless
        try:
            size = os.path.getsize(file_path)
            if size <= 600 * 1024: # Under 600KB
                ext = sec_name.rsplit('.', 1)[1].lower()
                mime = 'image/svg+xml' if ext == 'svg' else f'image/{ext}'
                if ext == 'jpg': mime = 'image/jpeg'
                with open(file_path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')
                    return f"data:{mime};base64,{b64}"
        except Exception:
            pass
        return f"/static/uploads/products/{filename}"
    return fallback_url
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.secret_key = os.environ.get('SECRET_KEY', 'xol_super_secret_whatsapp_store_key_2026')
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Initialize DB on start
init_db()

@app.context_processor
def inject_user():
    if 'user_id' in session:
        return {'current_user': {
            'id': session['user_id'],
            'name': session.get('user_name', 'Customer'),
            'email': session.get('user_email', '')
        }}
    return {'current_user': None}

def generate_order_id():
    """Generates a memorable order ID like V24-8492"""
    digits = ''.join(random.choices(string.digits, k=4))
    letters = ''.join(random.choices(string.ascii_uppercase, k=2))
    return f"V24-{letters}{digits}"

def parse_order_row(row):
    """Converts a sqlite3.Row into a Python dictionary with parsed JSON fields"""
    if not row:
        return None
    d = dict(row)
    try:
        d['products'] = json.loads(d['products_json']) if d['products_json'] else []
    except Exception:
        d['products'] = []
    
    # Calculate time remaining
    now = datetime.now(timezone.utc)
    try:
        # Support both naive and tz-aware strings
        target_str = d['target_delivery_at']
        if target_str.endswith('Z'):
            target_str = target_str[:-1] + '+00:00'
        target = datetime.fromisoformat(target_str)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        d['target_datetime'] = target
        diff = target - now
        total_seconds = int(diff.total_seconds())
        d['seconds_left'] = max(0, total_seconds)
        d['is_expired'] = total_seconds <= 0
        d['hours_left'] = d['seconds_left'] // 3600
        d['minutes_left'] = (d['seconds_left'] % 3600) // 60
        d['seconds_only'] = d['seconds_left'] % 60
    except Exception as e:
        d['seconds_left'] = 0
        d['is_expired'] = True
        d['hours_left'] = 0
        d['minutes_left'] = 0
        d['seconds_only'] = 0

    # Format created date
    try:
        c_str = d.get('created_at', '')
        if c_str.endswith('Z'):
            c_str = c_str[:-1] + '+00:00'
        c_dt = datetime.fromisoformat(c_str)
        d['created_formatted'] = c_dt.strftime('%b %d, %Y · %I:%M %p')
        d['created_date_short'] = c_dt.strftime('%b %d, %Y')
    except Exception:
        d['created_formatted'] = d.get('created_at', '')
        d['created_date_short'] = d.get('created_at', '')

    # Status & Delivery Progress Stage
    status_lower = str(d.get('status', 'submitted')).lower()
    d['is_delivered'] = status_lower in ('delivered', 'completed')
    if d['is_delivered']:
        d['progress_stage'] = 4
        d['stage_label'] = 'Delivered & Received'
    elif status_lower in ('dispatched', 'shipped', 'out_for_delivery'):
        d['progress_stage'] = 3
        d['stage_label'] = 'Out for Delivery / In Transit'
    elif status_lower in ('in_progress', 'printing', 'ready'):
        d['progress_stage'] = 2
        d['stage_label'] = 'Atelier Crafting & Quality Inspection'
    else:
        d['progress_stage'] = 1
        d['stage_label'] = 'Order Confirmed · In 24h Queue'

    # Check whether the website link is ready to be shown to the vendor:
    # Condition: Admin provided a link AND (publish_mode == 'immediate' OR (publish_mode == 'countdown' and 24h expired))
    has_link = bool(d['website_url'] and d['website_url'].strip())
    is_ready_by_time = d['is_expired'] and has_link
    is_ready_immediate = (d['publish_mode'] == 'immediate') and has_link
    d['can_show_website'] = (is_ready_by_time or is_ready_immediate or d['status'] == 'completed') and has_link
    
    return d

# ----------------- Customer Facing Routes -----------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/collection')
@app.route('/vintage')
def vintage_gallery():
    dynamic_products = get_products_by_section('vintage', include_inactive=False)
    return render_template('vintage.html', dynamic_products=dynamic_products)

@app.route('/custom-studio')
@app.route('/polos')
def custom_studio():
    dynamic_products = get_products_by_section('studio', include_inactive=False)
    return render_template('custom_studio.html', dynamic_products=dynamic_products)

@app.route('/cart')
def cart_view():
    return render_template('cart.html')

@app.route('/auth', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
@app.route('/signup', methods=['GET', 'POST'])
def auth():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    tab = 'signup' if request.path == '/signup' else request.args.get('tab', 'signin')
    
    if request.method == 'POST':
        action = request.form.get('action', 'signin')
        
        if action == 'signup':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            phone = request.form.get('phone', '').strip()
            
            if not name or not email or not password:
                flash("Please fill in all required fields (Name, Email, Password).", "error")
                return render_template('auth.html', tab='signup', name=name, email=email, phone=phone)
            
            existing = get_user_by_email(email)
            if existing:
                flash("An account with this email already exists. Please sign in.", "error")
                return render_template('auth.html', tab='signin', email=email)
            
            pw_hash = generate_password_hash(password)
            user_id = create_user(name, email, phone, pw_hash)
            
            session['user_id'] = user_id
            session['user_name'] = name
            session['user_email'] = email
            
            flash(f"Welcome to Vent Atelier, {name}!", "success")
            next_url = request.args.get('next') or url_for('index')
            return redirect(next_url)
            
        else: # signin
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            
            if not email or not password:
                flash("Please provide both email and password.", "error")
                return render_template('auth.html', tab='signin', email=email)
            
            user = get_user_by_email(email)
            
            if not user or not check_password_hash(user['password_hash'], password):
                flash("Invalid email or password. Please try again.", "error")
                return render_template('auth.html', tab='signin', email=email)
            
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            
            flash(f"Welcome back, {user['name']}!", "success")
            next_url = request.args.get('next') or url_for('index')
            return redirect(next_url)

    return render_template('auth.html', tab=tab)

@app.route('/logout')
def user_logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_email', None)
    flash("You have been signed out.", "info")
    return redirect(request.referrer or url_for('index'))

@app.route('/api/auth', methods=['POST'])
def api_auth():
    data = request.get_json(silent=True) or request.form
    action = data.get('action', 'signin')
    
    if action == 'signup':
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        phone = data.get('phone', '').strip()
        
        if not name or not email or not password:
            return jsonify({'success': False, 'message': 'Please provide Name, Email, and Password.'}), 400
        
        existing = get_user_by_email(email)
        if existing:
            return jsonify({'success': False, 'message': 'Email already registered. Please sign in.'}), 400
        
        pw_hash = generate_password_hash(password)
        user_id = create_user(name, email, phone, pw_hash)
        session['user_id'] = user_id
        session['user_name'] = name
        session['user_email'] = email
        return jsonify({'success': True, 'name': name, 'message': f'Welcome to Vent, {name}!'})
    else:
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and Password required.'}), 400
        user = get_user_by_email(email)
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        return jsonify({'success': True, 'name': user['name'], 'message': f'Welcome back, {user["name"]}!'})

@app.route('/logo-preview')
def logo_preview():
    return render_template('logo_preview.html')

@app.route('/order', methods=['GET', 'POST'])
def order():
    if request.method == 'GET':
        prefill_garment = request.args.get('garment', 'heavy_tee')
        return render_template('order.html', selected_garment=prefill_garment)
    
    # Process Order Submission
    # Support both custom apparel studio submissions and legacy vendor forms
    customer_name = request.form.get('customer_name', '').strip()
    business_name = request.form.get('business_name', '').strip() or customer_name or 'Custom Apparel Client'
    vendor_name = request.form.get('vendor_name', '').strip() or customer_name or business_name
    whatsapp_number = request.form.get('whatsapp_number', '').strip()
    email = request.form.get('email', '').strip()
    address = request.form.get('address', '').strip()

    # Custom Garment & Artwork details
    garment_type = request.form.get('garment_type', 'heavy_tee').strip()
    garment_name = request.form.get('garment_name', 'Heavyweight Boxy Tee (240 GSM)').strip()
    garment_size = request.form.get('garment_size', 'L').strip()
    garment_color = request.form.get('garment_color', 'Onyx Black').strip()
    print_technique = request.form.get('print_technique', '3D Raised Puff Ink').strip()
    print_placement = request.form.get('print_placement', 'Center Chest').strip()
    quantity = request.form.get('quantity', '1').strip()
    artwork_url = request.form.get('artwork_url', '').strip()
    artwork_data = request.form.get('artwork_data', '').strip()
    custom_garment_url = request.form.get('custom_garment_url', '').strip()
    custom_garment_data = request.form.get('custom_garment_data', '').strip()
    design_notes = request.form.get('design_notes', '').strip() or request.form.get('about_text', '').strip()
    tagline_input = request.form.get('tagline', '').strip()
    category = request.form.get('category', 'Custom T-Shirt Studio')
    currency = request.form.get('currency', '₦')

    if not customer_name and not business_name:
        flash("Please provide your name.", "error")
        return redirect(url_for('order'))
    if not whatsapp_number:
        flash("Please provide your WhatsApp number so our atelier can send your digital mockup proof.", "error")
        return redirect(url_for('order'))

    # Determine plan price and naming
    price_val = request.form.get('plan_price')
    try:
        if price_val:
            plan_price = float(price_val)
        else:
            price_map = {
                'heavy_tee': 22000.0,
                'vintage_tee': 24500.0,
                'luxury_polo': 24500.0,
                'french_terry_hoodie': 38000.0,
                'washed_crewneck': 32000.0,
                'custom_blank': 20000.0,
                'basic_2': 2.0,
                'pro_10': 10.0
            }
            plan_price = price_map.get(garment_type, 22000.0)
    except Exception:
        plan_price = 22000.0

    plan_type = request.form.get('plan_type') or garment_type
    plan_name = request.form.get('plan_name') or f"Custom {garment_name} · {print_technique}"

    # Check for legacy product arrays (for backward compatibility)
    product_names = request.form.getlist('product_name[]')
    product_prices = request.form.getlist('product_price[]')
    product_descs = request.form.getlist('product_desc[]')
    product_images = request.form.getlist('product_image[]')
    product_cats = request.form.getlist('product_category[]')

    products = []
    if product_names and product_names[0].strip():
        for i in range(len(product_names)):
            name = product_names[i].strip()
            if name:
                p_price = product_prices[i].strip() if i < len(product_prices) else '0'
                p_desc = product_descs[i].strip() if i < len(product_descs) else ''
                p_img = product_images[i].strip() if i < len(product_images) else ''
                p_cat = product_cats[i].strip() if i < len(product_cats) else 'General'
                products.append({
                    'id': i + 1,
                    'name': name,
                    'price': p_price,
                    'desc': p_desc,
                    'image': p_img or 'https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=500&auto=format&fit=crop&q=60',
                    'category': p_cat
                })
    else:
        preview_img = artwork_url or (artwork_data if len(artwork_data) < 200000 else '') or custom_garment_url or 'https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=900&auto=format&fit=crop&q=80'
        products.append({
            'id': 1,
            'name': f"{garment_name} ({garment_size} / {garment_color})",
            'price': str(plan_price),
            'desc': f"Placement: {print_placement} | Print: {print_technique} | Qty: {quantity} | Notes: {design_notes}",
            'image': preview_img,
            'category': 'Custom Studio Apparel',
            'garment_type': garment_type,
            'garment_size': garment_size,
            'garment_color': garment_color,
            'print_technique': print_technique,
            'print_placement': print_placement,
            'quantity': quantity,
            'design_notes': design_notes,
            'artwork_url': artwork_url,
            'custom_garment_url': custom_garment_url
        })

    order_id = generate_order_id()
    created_at = datetime.now(timezone.utc)
    target_delivery = created_at + timedelta(hours=24)

    order_dict = {
        'id': order_id,
        'created_at': created_at.isoformat(),
        'target_delivery_at': target_delivery.isoformat(),
        'plan_type': plan_type,
        'plan_name': plan_name,
        'plan_price': plan_price,
        'business_name': business_name,
        'vendor_name': vendor_name or business_name,
        'whatsapp_number': whatsapp_number,
        'email': email,
        'category': category,
        'currency': currency,
        'tagline': tagline_input or f"Size {garment_size} · {garment_color} · {print_placement} · {print_technique}",
        'about_text': design_notes,
        'address': address,
        'instagram': request.form.get('instagram', '').strip(),
        'facebook': request.form.get('facebook', '').strip(),
        'tiktok': request.form.get('tiktok', '').strip(),
        'products_json': json.dumps(products),
        'status': 'submitted',
        'website_url': '',
        'publish_mode': 'countdown',
        'is_published': 0
    }
    create_order(order_dict)

    return redirect(url_for('status', order_id=order_id, new='1'))
    create_order(order_dict)

    return redirect(url_for('status', order_id=order_id, new='1'))

@app.route('/status/<order_id>')
def status(order_id):
    row = get_order(order_id)

    if not row:
        flash("Order ID not found. Please check your reference code.", "error")
        return redirect(url_for('track'))

    order_data = parse_order_row(row)
    is_new = request.args.get('new') == '1'
    return render_template('status.html', order=order_data, is_new=is_new)

@app.route('/api/status/<order_id>')
def api_status(order_id):
    row = get_order(order_id)
    if not row:
        return jsonify({'error': 'Order not found'}), 404
    return jsonify(parse_order_row(row))

    if not row:
        return jsonify({'error': 'Order not found'}), 404

    order_data = parse_order_row(row)
    return jsonify({
        'id': order_data['id'],
        'status': order_data['status'],
        'seconds_left': order_data['seconds_left'],
        'is_expired': order_data['is_expired'],
        'can_show_website': order_data['can_show_website'],
        'website_url': order_data['website_url'] if order_data['can_show_website'] else '',
        'plan_type': order_data['plan_type'],
        'vendor_admin_url': order_data['vendor_admin_url'] if order_data['can_show_website'] else '',
        'vendor_admin_user': order_data['vendor_admin_user'] if order_data['can_show_website'] else ''
    })

@app.route('/track', methods=['GET', 'POST'])
def track():
    query = request.args.get('query', '').strip() or request.args.get('order_id', '').strip()
    if request.method == 'POST':
        query = request.form.get('query', '').strip() or query

    user_email = session.get('user_email', '').strip()
    # Auto-load orders if user is signed in
    if not query and user_email:
        query = user_email

    orders = []
    has_searched = bool(query)
    if query:
        raw_rows = search_orders(query)
        orders = [parse_order_row(r) for r in raw_rows if r]

    # Split into active deliveries (package not yet delivered) and past transactions
    active_orders = [o for o in orders if not o.get('is_delivered')]
    past_orders = [o for o in orders if o.get('is_delivered')]

    return render_template('track.html', 
                           query=query, 
                           orders=orders, 
                           active_orders=active_orders, 
                           past_orders=past_orders,
                           has_searched=has_searched)

# ----------------- Admin Management Routes -----------------

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        saved_pass = get_setting('admin_password', 'admin123')
        if password == saved_pass:
            session['is_admin'] = True
            flash("Welcome to the Admin Portal!", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid administrator password.", "error")

    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    flash("You have been signed out.", "info")
    return redirect(url_for('admin_login'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    active_tab = request.args.get('tab', 'submissions')
    status_filter = request.args.get('status', 'all')
    section_filter = request.args.get('section', 'all')
    search_q = request.args.get('q', '').strip().lower()

    # Inbound Orders & Customer Submissions
    rows = get_all_orders()
    all_orders = [parse_order_row(r) for r in rows if r]

    # Filter Orders
    orders = all_orders
    if search_q and active_tab == 'submissions':
        orders = [
            o for o in orders 
            if search_q in o.get('id', '').lower() 
            or search_q in o.get('business_name', '').lower() 
            or search_q in o.get('vendor_name', '').lower() 
            or search_q in o.get('whatsapp_number', '').lower() 
            or search_q in o.get('email', '').lower()
        ]
    if status_filter != 'all':
        if status_filter == 'active':
            orders = [o for o in orders if not o.get('is_delivered')]
        elif status_filter == 'delivered':
            orders = [o for o in orders if o.get('is_delivered')]
        elif status_filter in ('submitted', 'in_progress', 'dispatched'):
            orders = [o for o in orders if o.get('status') == status_filter]

    # Goods / Products Catalog
    all_products = get_all_products(include_inactive=True)
    products = all_products
    if section_filter != 'all':
        products = [p for p in products if p.get('section') == section_filter]
    if search_q and active_tab == 'goods':
        products = [
            p for p in products 
            if search_q in p.get('title', '').lower() 
            or search_q in p.get('category', '').lower() 
            or search_q in p.get('badge', '').lower()
        ]

    # Metrics
    total_orders = len(all_orders)
    pending_orders = sum(1 for o in all_orders if o.get('status') in ('submitted', None, ''))
    crafting_orders = sum(1 for o in all_orders if o.get('status') in ('in_progress', 'printing', 'ready'))
    delivered_orders = sum(1 for o in all_orders if o.get('is_delivered'))
    basic_orders = sum(1 for o in all_orders if o.get('plan_type') == 'basic_2')
    pro_orders = sum(1 for o in all_orders if o.get('plan_type') == 'pro_10')
    completed_orders = sum(1 for o in all_orders if o.get('status') == 'completed' or (o.get('website_url') and o.get('website_url').strip()))
    active_countdowns = sum(1 for o in all_orders if not o.get('is_expired') and o.get('status') not in ('delivered', 'completed'))
    total_revenue = (basic_orders * 2) + (pro_orders * 10)

    total_products = len(all_products)
    vintage_count = sum(1 for p in all_products if p.get('section') == 'vintage')
    studio_count = sum(1 for p in all_products if p.get('section') == 'studio')
    active_goods_count = sum(1 for p in all_products if p.get('is_active', 1) == 1)

    platform_whatsapp = get_setting('platform_whatsapp', '+2348000000000')

    return render_template('admin_dashboard.html', 
                           active_tab=active_tab,
                           status_filter=status_filter,
                           section_filter=section_filter,
                           search_q=search_q,
                           orders=orders,
                           all_orders=all_orders,
                           products=products,
                           all_products=all_products,
                           total_orders=total_orders,
                           pending_orders=pending_orders,
                           crafting_orders=crafting_orders,
                           delivered_orders=delivered_orders,
                           basic_orders=basic_orders,
                           pro_orders=pro_orders,
                           completed_orders=completed_orders,
                           active_countdowns=active_countdowns,
                           total_revenue=total_revenue,
                           total_products=total_products,
                           vintage_count=vintage_count,
                           studio_count=studio_count,
                           active_goods_count=active_goods_count,
                           platform_whatsapp=platform_whatsapp)

@app.route('/admin/product/add', methods=['POST'])
def admin_product_add():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    title = request.form.get('title', '').strip()
    section = request.form.get('section', 'vintage').strip()
    category = request.form.get('category', 'tees').strip()
    price = request.form.get('price', '').strip()
    currency = request.form.get('currency', '$').strip()
    badge = request.form.get('badge', '').strip()
    size = request.form.get('size', 'L').strip()
    condition = request.form.get('condition', '').strip()
    measurements = request.form.get('measurements', '').strip()
    description = request.form.get('description', '').strip()
    image_url_input = request.form.get('image_url', '').strip()
    image_file = request.files.get('image_file')

    if not title:
        flash("Product title is required.", "error")
        return redirect(url_for('admin_dashboard', tab='goods'))

    final_image = handle_image_storage(image_file, image_url_input)
    if not final_image:
        final_image = "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=900&auto=format&fit=crop&q=80"

    product_id = f"PRD-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"
    product_dict = {
        'id': product_id,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'title': title,
        'section': section,
        'category': category,
        'price': price or '0',
        'currency': currency,
        'badge': badge,
        'size': size,
        'condition': condition,
        'measurements': measurements,
        'description': description,
        'image_url': final_image,
        'is_active': 1,
        'sort_order': 0
    }
    create_product(product_dict)
    flash(f"Successfully published '{title}' to {section.title()} catalog!", "success")
    return redirect(url_for('admin_dashboard', tab='goods'))

@app.route('/admin/product/<product_id>/update', methods=['POST'])
def admin_product_update(product_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    existing = get_product(product_id)
    if not existing:
        flash("Product not found.", "error")
        return redirect(url_for('admin_dashboard', tab='goods'))

    title = request.form.get('title', existing.get('title', '')).strip()
    section = request.form.get('section', existing.get('section', 'vintage')).strip()
    category = request.form.get('category', existing.get('category', 'tees')).strip()
    price = request.form.get('price', existing.get('price', '')).strip()
    currency = request.form.get('currency', existing.get('currency', '$')).strip()
    badge = request.form.get('badge', existing.get('badge', '')).strip()
    size = request.form.get('size', existing.get('size', 'L')).strip()
    condition = request.form.get('condition', existing.get('condition', '')).strip()
    measurements = request.form.get('measurements', existing.get('measurements', '')).strip()
    description = request.form.get('description', existing.get('description', '')).strip()
    is_active = 1 if request.form.get('is_active') == '1' else 0

    image_url_input = request.form.get('image_url', '').strip()
    image_file = request.files.get('image_file')
    final_image = handle_image_storage(image_file, image_url_input or existing.get('image_url'))

    update_dict = {
        'title': title,
        'section': section,
        'category': category,
        'price': price,
        'currency': currency,
        'badge': badge,
        'size': size,
        'condition': condition,
        'measurements': measurements,
        'description': description,
        'image_url': final_image,
        'is_active': is_active
    }
    update_product(product_id, update_dict)
    flash(f"Product '{title}' updated successfully!", "success")
    return redirect(url_for('admin_dashboard', tab='goods'))

@app.route('/admin/product/<product_id>/toggle-status', methods=['POST'])
def admin_product_toggle_status(product_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    existing = get_product(product_id)
    if existing:
        current_state = int(existing.get('is_active', 1))
        new_status = 0 if current_state == 1 else 1
        update_product(product_id, {'is_active': new_status})
        status_label = "Visible" if new_status == 1 else "Hidden"
        flash(f"Product visibility set to {status_label}.", "info")
    return redirect(url_for('admin_dashboard', tab='goods'))

@app.route('/admin/product/<product_id>/delete', methods=['POST'])
def admin_product_delete(product_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    delete_product(product_id)
    flash("Product removed from catalog.", "info")
    return redirect(url_for('admin_dashboard', tab='goods'))

@app.route('/admin/order/<order_id>/update-status', methods=['POST'])
def admin_order_update_status(order_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    status = request.form.get('status', 'submitted').strip()
    admin_notes = request.form.get('admin_notes', '').strip()
    website_url = request.form.get('website_url', '').strip()
    publish_mode = request.form.get('publish_mode', 'countdown').strip()

    update_dict = {
        'status': status,
        'admin_notes': admin_notes,
        'website_url': website_url,
        'publish_mode': publish_mode
    }
    update_order(order_id, update_dict)
    flash(f"Submission {order_id} updated (Status: {status}).", "success")
    return redirect(url_for('admin_dashboard', tab='submissions'))

@app.route('/admin/settings/update', methods=['POST'])
def admin_settings_update():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    new_password = request.form.get('admin_password', '').strip()
    platform_whatsapp = request.form.get('platform_whatsapp', '').strip()

    if new_password:
        set_setting('admin_password', new_password)
        flash("Admin portal password updated successfully.", "success")
    if platform_whatsapp:
        set_setting('platform_whatsapp', platform_whatsapp)
        flash("Atelier WhatsApp contact number updated.", "success")

    return redirect(url_for('admin_dashboard', tab='settings'))

@app.route('/admin/order/<order_id>/update', methods=['POST'])
def admin_order_update(order_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    website_url = request.form.get('website_url', '').strip()
    status = request.form.get('status', 'in_progress')
    publish_mode = request.form.get('publish_mode', 'countdown') # 'countdown' or 'immediate'
    vendor_admin_url = request.form.get('vendor_admin_url', '').strip()
    vendor_admin_user = request.form.get('vendor_admin_user', '').strip()
    vendor_admin_pass = request.form.get('vendor_admin_pass', '').strip()
    admin_notes = request.form.get('admin_notes', '').strip()

    update_data = {
        'website_url': website_url,
        'status': status,
        'publish_mode': publish_mode,
        'vendor_admin_url': vendor_admin_url,
        'vendor_admin_user': vendor_admin_user,
        'vendor_admin_pass': vendor_admin_pass,
        'admin_notes': admin_notes
    }
    update_order(order_id, update_data)

    flash(f"Order {order_id} updated successfully! Website link submitted.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/order/<order_id>/simulate-time', methods=['POST'])
def admin_simulate_time(order_id):
    """
    Demo/Testing tool: allows the administrator to expire the 24-hour countdown immediately
    or set it back to active to test the exact delivery behavior!
    """
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403

    action = request.form.get('action', 'expire') # 'expire' or 'reset'

    if action == 'expire':
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        update_order(order_id, {'target_delivery_at': past_time})
    else:
        future_time = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        update_order(order_id, {'target_delivery_at': future_time})

    flash(f"24-hour timer simulation updated for order {order_id} ({action})!", "info")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/order/<order_id>/delete', methods=['POST'])
def admin_order_delete(order_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    delete_order(order_id)
    flash(f"Order {order_id} has been deleted.", "info")
    return redirect(url_for('admin_dashboard'))

# ----------------- Auto-Generated Live WhatsApp Store Preview -----------------

@app.route('/preview/<order_id>')
def preview_store(order_id):
    """
    Renders a live, fully functional WhatsApp storefront generated directly
    from the vendor's submitted information!
    This allows the admin or vendor to immediately test their website with
    1-click WhatsApp order formatting.
    """
    row = get_order(order_id)
    if not row:
        return "Store not found", 404

    order_data = parse_order_row(row)
    return render_template('vendor_store.html', store=order_data)

@app.route('/preview/<order_id>/vendor-admin')
def preview_vendor_admin(order_id):
    """
    Demonstrates the $10 Pro Plan Admin Login capability!
    Allows the vendor to log in to manage their products and orders.
    """
    row = get_order(order_id)
    if not row:
        return "Store not found", 404

    order_data = parse_order_row(row)
    return render_template('vendor_admin.html', store=order_data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("Starting Vent Collection Platform...")
    print(f"Customer Site: http://127.0.0.1:{port}")
    print(f"Admin Portal: http://127.0.0.1:{port}/admin (Password: admin123)")
    app.run(host='127.0.0.1', port=port, debug=False)
