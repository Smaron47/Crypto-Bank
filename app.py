from flask import Flask, request, jsonify,send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import datetime
import uuid
import json
import random

# --- Helper Utilities ---

def generate_id():
    """Generates a short, unique ID."""
    return str(uuid.uuid4())[:8].upper()

def format_currency(amount):
    """Simple currency formatting."""
    return f"${amount:,.2f}"

def get_admin_config():
    """Retrieves the single AdminConfig record."""
    config = AdminConfig.query.first()
    if not config:
        config = AdminConfig(pending_loans='[]', ledger='[]')
        db.session.add(config)
        db.session.commit()
    return config

def load_json(data):
    """Safely loads JSON string or returns empty structure."""
    if not data: return {}
    try:
        return json.loads(data)
    except:
        return {}

def load_list(data):
    """Safely loads JSON list or returns empty list."""
    if not data: return []
    try:
        return json.loads(data)
    except:
        return []

# --- Flask App Setup ---

app = Flask(__name__)

# Allow CORS for your frontend origins
CORS(app, supports_credentials=True, origins=[
    'http://127.0.0.1:5500', 
    'http://localhost:5500',
    'http://localhost:3000',
    'http://127.0.0.1:8080'
]) 

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///neobank.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Models ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False) # Email
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user')
    status = db.Column(db.String(20), default='Active')
    
    # Stored as JSON strings
    profile = db.Column(db.Text)      # {name, email, phone, avatar, tier, points, account_number}
    financials = db.Column(db.Text)   # {fiatBalance, cryptoWallet: {BTC: 0, ...}}
    cards = db.Column(db.Text)        # List of card objects
    loans = db.Column(db.Text)        # List of loan objects
    transactions = db.Column(db.Text) # List of transaction objects
    notifications = db.Column(db.Text)# List of notifications

class AdminConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_liquidity = db.Column(db.Float, default=250000000.00)
    base_interest_rate = db.Column(db.Float, default=4.5)
    crypto_fee_base = db.Column(db.Float, default=1.5)
    pending_loans = db.Column(db.Text) 
    ledger = db.Column(db.Text)

class SupportTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    reply = db.Column(db.Text, nullable=True)
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    status = db.Column(db.String(20), default='Open')

# --- DB Initialization ---

with app.app_context():
    db.create_all()
    # Ensure Admin Exists
    if not User.query.filter_by(role='admin').first():
        hashed_pw = generate_password_hash('admin')
        profile = json.dumps({'name': 'System Admin', 'email': 'admin@neobank.ai', 'tier': 'Master', 'points': 0})
        financials = json.dumps({'fiatBalance': 0, 'cryptoWallet': {}})
        admin = User(username='admin@neobank.ai', password=hashed_pw, role='admin', 
                     profile=profile, financials=financials, cards='[]', loans='[]', transactions='[]', notifications='[]')
        db.session.add(admin)
        db.session.commit()
    
    # Ensure Default User Exists
    if not User.query.filter_by(username='user').first():
        hashed_pw = generate_password_hash('user')
        profile = json.dumps({'name': 'Alex Morgan', 'email': 'user', 'tier': 'Gold', 'points': 1250, 'account_number': '100000001'})
        financials = json.dumps({'fiatBalance': 15000.00, 'cryptoWallet': {'BTC': 0.5, 'ETH': 10}})
        user = User(username='user', password=hashed_pw, role='user', 
                    profile=profile, financials=financials, cards='[]', loans='[]', transactions='[]', notifications='[]')
        db.session.add(user)
        db.session.commit()

# --- Auth Decorator ---

def require_auth(role=None):
    def decorator(f):
        def wrapper(*args, **kwargs):
            if request.method == 'OPTIONS': return jsonify({'msg': 'ok'}), 200
            auth_header = request.headers.get('Authorization')
            if not auth_header: return jsonify({'error': 'No token provided'}), 401
            try:
                # Mock Token: "Bearer <user_id>"
                user_id = int(auth_header.split(' ')[1])
                user = User.query.get(user_id)
                if not user: return jsonify({'error': 'Invalid user'}), 401
                if role and user.role != role: return jsonify({'error': 'Forbidden'}), 403
                request.user = user
            except:
                return jsonify({'error': 'Invalid token'}), 401
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

# --- Helper Logic ---

def add_points(user, amount_spent):
    """Adds 1 point for every $10 spent."""
    profile = load_json(user.profile)
    points = int(amount_spent / 10)
    if points > 0:
        profile['points'] = profile.get('points', 0) + points
        user.profile = json.dumps(profile)

def log_transaction(user, amount, type, merchant, category='General', status='Completed'):
    txs = load_list(user.transactions)
    tx = {
        'id': generate_id(),
        'date': datetime.datetime.utcnow().isoformat(),
        'merchant': merchant,
        'amount': amount,
        'type': type,
        'category': category,
        'currency': 'USD',
        'status': status
    }
    txs.append(tx)
    user.transactions = json.dumps(txs)
    
    # Add points for spending
    if amount < 0 and type not in ['TRANSFER', 'WITHDRAWAL']:
        add_points(user, abs(amount))
    
    return tx

# --- Routes ---
@app.route('/', methods=['GET'])
def serve_frontend():
    # Serves the index.html from the static directory (assumes it's renamed to index.html)
    return send_from_directory('static', 'fuck.html')

# 1. Auth & Profile
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data.get('email')).first()
    if user and (user.password == data.get('password') or check_password_hash(user.password, data.get('password'))):
        p = load_json(user.profile)
        f = load_json(user.financials)
        return jsonify({
            'token': str(user.id),
            'user': {'name': p.get('name'), 'email': user.username, 'role': user.role, 'account_number': p.get('account_number')},
            'accounts': {'fiat': f.get('fiatBalance', 0), 'crypto': f.get('cryptoWallet', {})}
        })
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data['email']).first():
        return jsonify({'error': 'Email exists'}), 409
    
    new_user = User(
        username=data['email'],
        password=generate_password_hash(data['password']),
        profile=json.dumps({'name': data['name'], 'email': data['email'], 'tier': 'Standard', 'points': 0, 'account_number': generate_id()}),
        financials=json.dumps({'fiatBalance': 0.0, 'cryptoWallet': {}}),
        cards='[]', loans='[]', transactions='[]', notifications='[]'
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'token': str(new_user.id), 'user': {'name': data['name'], 'role': 'user'}}), 201

@app.route('/api/user/profile', methods=['GET', 'PUT', 'OPTIONS'])
@require_auth()
def user_profile():
    if request.method == 'GET':
        p = load_json(request.user.profile)
        f = load_json(request.user.financials)
        
        # FIX: Ensure cards and loans are loaded as lists from JSON strings
        user_cards = load_list(request.user.cards)
        user_loans = load_list(request.user.loans)
        user_transactions = load_list(request.user.transactions)
        
        return jsonify({
            'user': {'name': p.get('name'), 'email': request.user.username, 'role': request.user.role, 'tier': p.get('tier'), 'points': p.get('points', 0)},
            'accounts': {'fiat': f.get('fiatBalance'), 'crypto': f.get('cryptoWallet')},
            'cards': user_cards,
            'loans': user_loans,
            'transactions': user_transactions
        })
    
    if request.method == 'PUT':
        data = request.json
        p = load_json(request.user.profile)
        if 'name' in data: p['name'] = data['name']
        if 'phone' in data: p['phone'] = data['phone']
        request.user.profile = json.dumps(p)
        db.session.commit()
        return jsonify({'message': 'Profile updated'})
# 2. Banking & Transactions
@app.route('/api/transactions', methods=['GET', 'POST', 'OPTIONS'])
@require_auth()
def transactions():
    if request.method == 'GET':
        return jsonify(load_list(request.user.transactions))
    
    # Handle Transfer
    data = request.json
    amount = float(data.get('amount', 0))
    recipient_identity = data.get('recipient')
    
    f = load_json(request.user.financials)
    if f['fiatBalance'] < amount: return jsonify({'error': 'Insufficient funds'}), 400
    
    # Find recipient (simplistic)
    recipient = User.query.filter((User.username == recipient_identity) | (User.profile.contains(recipient_identity))).first()
    if not recipient: return jsonify({'error': 'Recipient not found'}), 404
    
    # Deduct
    f['fiatBalance'] -= amount
    request.user.financials = json.dumps(f)
    log_transaction(request.user, -amount, 'TRANSFER', f"Transfer to {recipient_identity}")
    
    # Credit Recipient
    rf = load_json(recipient.financials)
    rf['fiatBalance'] += amount
    recipient.financials = json.dumps(rf)
    log_transaction(recipient, amount, 'DEPOSIT', f"Received from {load_json(request.user.profile).get('name')}")
    
    db.session.commit()
    return jsonify({'message': 'Transfer successful'})

# 3. Cards Management
@app.route('/api/cards', methods=['POST', 'OPTIONS'])
@require_auth()
def request_card():
    data = request.json
    p = load_json(request.user.profile)
    f = load_json(request.user.financials)
    
    # Calculate fee
    fees = {'neon': 0, 'black': 20, 'gold': 50, 'metal': 100}
    fee = fees.get(data.get('skin'), 0)
    
    if f['fiatBalance'] < fee: return jsonify({'error': 'Insufficient funds for card fee'}), 400
    
    f['fiatBalance'] -= fee
    request.user.financials = json.dumps(f)
    if fee > 0: log_transaction(request.user, -fee, 'FEE', f"Card Issuance Fee ({data.get('skin')})")
    
    # Determine Status (Physical = Pending Admin Approval)
    status = 'Pending' if data.get('type') == 'Physical' or data.get('skin') == 'metal' else 'Active'
    
    new_card = {
        'id': generate_id(),
        'number': f"4{random.randint(100,999)} **** **** {random.randint(1000,9999)}",
        'name': data.get('name', p.get('name')),
        'type': data.get('type'),
        'skin': data.get('skin'),
        'expiry': '12/29',
        'limit': 5000.0,
        'status': status,
        'userName': p.get('name') # Storing for Admin visibility
    }
    
    cards = load_list(request.user.cards)
    cards.append(new_card)
    request.user.cards = json.dumps(cards)
    
    db.session.commit()
    return jsonify(new_card)

# 4. Loans System
@app.route('/api/loans/request', methods=['POST', 'OPTIONS'])
@require_auth()
def request_loan():
    data = request.json
    p = load_json(request.user.profile)
    
    loan = {
        'id': generate_id(),
        'amount': float(data['amount']),
        'duration': int(data['duration']),
        'reason': data.get('reason', 'Personal'),
        'interest_rate': 4.5,
        'status': 'Pending',
        'date': datetime.datetime.utcnow().isoformat(),
        'userName': p.get('name')
    }
    
    loans = load_list(request.user.loans)
    loans.append(loan)
    request.user.loans = json.dumps(loans)
    
    db.session.commit()
    return jsonify(loan)

# 5. Crypto
@app.route('/api/crypto/market', methods=['GET'])
def market_data():
    return jsonify([
        {'symbol': 'BTC', 'name': 'Bitcoin', 'price': 65000.00, 'change_24h': 2.5},
        {'symbol': 'ETH', 'name': 'Ethereum', 'price': 3500.00, 'change_24h': -1.2},
        {'symbol': 'SOL', 'name': 'Solana', 'price': 145.00, 'change_24h': 5.0}
    ])

@app.route('/api/crypto/trade', methods=['POST', 'OPTIONS'])
@require_auth()
def trade_crypto():
    data = request.json
    f = load_json(request.user.financials)
    
    action = data['action'] # 'buy' or 'sell'
    symbol = data['symbol']
    amount = float(data['amount']) # Amount in Crypto
    price = float(data['price'])
    cost = amount * price
    
    if action == 'buy':
        if f['fiatBalance'] < cost: return jsonify({'error': 'Insufficient funds'}), 400
        f['fiatBalance'] -= cost
        f['cryptoWallet'][symbol] = f['cryptoWallet'].get(symbol, 0) + amount
        log_transaction(request.user, -cost, 'BUY', f"Bought {amount} {symbol}")
        
    elif action == 'sell':
        if f['cryptoWallet'].get(symbol, 0) < amount: return jsonify({'error': 'Insufficient crypto'}), 400
        f['cryptoWallet'][symbol] -= amount
        f['fiatBalance'] += cost
        log_transaction(request.user, cost, 'SELL', f"Sold {amount} {symbol}")
        
    request.user.financials = json.dumps(f)
    db.session.commit()
    return jsonify({'message': 'Trade executed'})

@app.route('/api/crypto/withdraw', methods=['POST', 'OPTIONS'])
@require_auth()
def withdraw_crypto():
    data = request.json
    f = load_json(request.user.financials)
    symbol = data['symbol']
    amount = float(data['amount'])
    
    if f['cryptoWallet'].get(symbol, 0) < amount:
        return jsonify({'error': 'Insufficient crypto balance'}), 400
        
    f['cryptoWallet'][symbol] -= amount
    request.user.financials = json.dumps(f)
    log_transaction(request.user, 0, 'WITHDRAW', f"Sent {amount} {symbol} to external wallet")
    
    db.session.commit()
    return jsonify({'message': 'Withdrawal processed'})


# 6. Admin Routes
@app.route('/api/users', methods=['GET'])
@require_auth('admin')
def admin_get_users():
    users = User.query.all()
    res = []
    for u in users:
        p = load_json(u.profile)
        f = load_json(u.financials)
        # Calculate Mock Crypto Value (assuming static prices for list view)
        crypto_val = f.get('cryptoWallet', {}).get('BTC', 0) * 65000 + f.get('cryptoWallet', {}).get('ETH', 0) * 3500
        res.append({
            'id': u.id,
            'name': p.get('name'),
            'email': u.username,
            'fiat_balance': f.get('fiatBalance'),
            'crypto_value': crypto_val,
            'role': u.role,
            'status': u.status
        })
    return jsonify(res)

@app.route('/api/admin/users/<int:user_id>', methods=['PUT', 'OPTIONS'])
@require_auth('admin')
def admin_update_user(user_id):
    user = User.query.get(user_id)
    data = request.json
    if 'fiatBalance' in data:
        f = load_json(user.financials)
        f['fiatBalance'] = float(data['fiatBalance'])
        user.financials = json.dumps(f)
    if 'role' in data:
        user.role = data['role']
    db.session.commit()
    return jsonify({'message': 'User updated'})

@app.route('/api/admin/cards', methods=['GET'])
@require_auth('admin')
def admin_get_cards():
    users = User.query.all()
    all_cards = []
    for u in users:
        cards = load_list(u.cards)
        all_cards.extend(cards)
    return jsonify(all_cards)

@app.route('/api/admin/cards/<card_id>', methods=['PUT'])
@require_auth('admin')
def admin_edit_card(card_id):
    data = request.json
    # Find user with this card
    users = User.query.all()
    for u in users:
        cards = load_list(u.cards)
        for c in cards:
            if c['id'] == card_id:
                c['limit'] = float(data.get('limit', c['limit']))
                c['status'] = data.get('status', c['status'])
                u.cards = json.dumps(cards)
                db.session.commit()
                return jsonify({'message': 'Card updated'})
    return jsonify({'error': 'Card not found'}), 404

@app.route('/api/admin/cards/<card_id>/<action>', methods=['POST'])
@require_auth('admin')
def admin_card_action(card_id, action):
    users = User.query.all()
    for u in users:
        cards = load_list(u.cards)
        for c in cards:
            if c['id'] == card_id:
                if action == 'approve': c['status'] = 'Active'
                elif action == 'reject': c['status'] = 'Rejected'
                u.cards = json.dumps(cards)
                db.session.commit()
                return jsonify({'message': f'Card {action}d'})
    return jsonify({'error': 'Card not found'}), 404

@app.route('/api/admin/loans', methods=['GET'])
@require_auth('admin')
def admin_get_loans():
    users = User.query.all()
    all_loans = []
    for u in users:
        loans = load_list(u.loans)
        all_loans.extend(loans)
    return jsonify(all_loans)

@app.route('/api/admin/loans/<loan_id>/<action>', methods=['POST'])
@require_auth('admin')
def admin_loan_action(loan_id, action):
    data = request.json or {}
    users = User.query.all()
    for u in users:
        loans = load_list(u.loans)
        for l in loans:
            if l['id'] == loan_id:
                if action == 'approve':
                    l['status'] = 'Active'
                    if 'interest_rate' in data: l['interest_rate'] = data['interest_rate']
                    # Credit the user
                    f = load_json(u.financials)
                    f['fiatBalance'] += l['amount']
                    u.financials = json.dumps(f)
                    log_transaction(u, l['amount'], 'LOAN', 'Loan Disbursed')
                elif action == 'reject':
                    l['status'] = 'Rejected'
                
                u.loans = json.dumps(loans)
                db.session.commit()
                return jsonify({'message': f'Loan {action}d'})
    return jsonify({'error': 'Loan not found'}), 404

# 7. Support System
@app.route('/api/support/create', methods=['POST', 'OPTIONS'])
@require_auth()
def create_ticket():
    data = request.json
    p = load_json(request.user.profile)
    t = SupportTicket(user_id=request.user.id, subject=data['subject'], message=data['message'])
    db.session.add(t)
    db.session.commit()
    return jsonify({'message': 'Ticket created'})

@app.route('/api/admin/tickets', methods=['GET'])
@require_auth('admin')
def admin_tickets():
    tickets = SupportTicket.query.order_by(SupportTicket.date.desc()).all()
    res = []
    for t in tickets:
        u = User.query.get(t.user_id)
        p = load_json(u.profile) if u else {}
        res.append({
            'id': t.id,
            'subject': t.subject,
            'message': t.message,
            'status': t.status,
            'date': t.date.isoformat(),
            'userName': p.get('name', 'Unknown')
        })
    return jsonify(res)

@app.route('/api/admin/tickets/<int:ticket_id>/reply', methods=['POST', 'OPTIONS'])
@require_auth('admin')
def admin_reply_ticket(ticket_id):
    t = SupportTicket.query.get(ticket_id)
    if not t: return jsonify({'error': 'Ticket not found'}), 404
    
    t.reply = request.json.get('message')
    t.status = 'Closed'
    db.session.commit()
    return jsonify({'message': 'Reply sent'})

@app.route('/api/admin/stats', methods=['GET'])
@require_auth('admin')
def admin_stats():
    # Mock aggregation for the dashboard counters
    return jsonify({'msg': 'ok'}) 

@app.route('/api/config', methods=['GET', 'PUT', 'OPTIONS'])
def config_route():
    if request.method == 'OPTIONS': return jsonify({'msg': 'ok'}), 200
    conf = get_admin_config()
    if request.method == 'GET':
        return jsonify({
            'totalLiquidity': conf.total_liquidity,
            'baseInterestRate': conf.base_interest_rate
        })
    data = request.json
    if 'totalLiquidity' in data: conf.total_liquidity = float(data['totalLiquidity'])
    if 'baseInterestRate' in data: conf.base_interest_rate = float(data['baseInterestRate'])
    db.session.commit()
    return jsonify({'msg': 'Updated'})

if __name__ == '__main__':
    app.run(debug=True, port=8080)