from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
socketio = SocketIO(app, cors_allowed_origins="*", manage_session=False)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database initialization
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT
        )
    ''')
    
    # Create messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users (id),
            FOREIGN KEY (receiver_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()


class User(UserMixin):
    def __init__(self, id, username, name=None):
        self.id = str(id)
        self.username = username
        self.name = name or username


def get_user_by_id(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, name FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return User(row[0], row[1], row[2])
    return None


def get_user_by_username(username):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, password_hash, name FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    return row


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

# Initialize database on startup
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user_row = get_user_by_username(username)
        
        if user_row and check_password_hash(user_row[2], password):
            user = User(user_row[0], user_row[1], user_row[3])
            login_user(user)
            session['name'] = user.name
            session['username'] = user.username
            return redirect(url_for('chat'))
        else:
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form['username']
    password = request.form['password']
    name = request.form.get('name', username)
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    try:
        password_hash = generate_password_hash(password)
        cursor.execute('INSERT INTO users (username, password_hash, name) VALUES (?, ?, ?)',
                      (username, password_hash, name))
        conn.commit()
        
        user_id = cursor.lastrowid
        conn.close()
        
        user = User(user_id, username, name)
        login_user(user)
        session['name'] = user.name
        session['username'] = user.username
        
        return redirect(url_for('chat'))
    except sqlite3.IntegrityError:
        conn.close()
        return render_template('login.html', error='Username already exists')

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('index'))

@app.route('/api/users')
@login_required
def get_users():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Not authenticated'}), 401
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, name FROM users WHERE id != ?', (current_user.id,))
    users = cursor.fetchall()
    conn.close()
    
    return jsonify([{'id': user[0], 'username': user[1], 'name': user[2] or user[1]} for user in users])

@app.route('/api/search/<username>')
@login_required
def search_user(username):
    if not current_user.is_authenticated:
        return jsonify({'error': 'Not authenticated'}), 401
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, name FROM users WHERE username = ? AND id != ?', 
                  (username, current_user.id))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return jsonify({'id': user[0], 'username': user[1], 'name': user[2] or user[1]})
    else:
        return jsonify({'error': 'No user found'}), 404

@app.route('/api/messages/<int:user_id>')
@login_required
def get_messages(user_id):
    if not current_user.is_authenticated:
        return jsonify({'error': 'Not authenticated'}), 401
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.text, m.timestamp, u.username, u.name, m.sender_id
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE (m.sender_id = ? AND m.receiver_id = ?) OR (m.sender_id = ? AND m.receiver_id = ?)
        ORDER BY m.timestamp ASC
    ''', (current_user.id, user_id, user_id, current_user.id))
    
    messages = cursor.fetchall()
    conn.close()
    
    return jsonify([{
        'text': msg[0],
        'timestamp': msg[1],
        'sender_username': msg[2],
        'sender_name': msg[3],
        'is_own': str(msg[4]) == str(current_user.id)
    } for msg in messages])

# Socket events
@socketio.on('connect')
def on_connect():
    if not current_user.is_authenticated:
        return False
    join_room(f"user_{current_user.id}")
    print(f"User {current_user.username} connected")

@socketio.on('disconnect')
def on_disconnect():
    if current_user.is_authenticated:
        leave_room(f"user_{current_user.id}")
        print(f"User {current_user.username} disconnected")

@socketio.on('send_message')
def handle_message(data):
    if not current_user.is_authenticated:
        return
    
    receiver_id = data['receiver_id']
    message_text = data['message']
    
    # Save message to database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (sender_id, receiver_id, text)
        VALUES (?, ?, ?)
    ''', (current_user.id, receiver_id, message_text))
    conn.commit()
    
    # Get timestamp
    cursor.execute('SELECT timestamp FROM messages WHERE id = ?', (cursor.lastrowid,))
    timestamp = cursor.fetchone()[0]
    conn.close()
    
    # Emit to receiver
    emit('receive_message', {
        'message': message_text,
        'sender_id': current_user.id,
        'sender_username': current_user.username,
        'sender_name': current_user.name,
        'timestamp': timestamp
    }, room=f"user_{receiver_id}")
    
    # Emit back to sender for confirmation
    emit('message_sent', {
        'message': message_text,
        'receiver_id': receiver_id,
        'timestamp': timestamp
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
