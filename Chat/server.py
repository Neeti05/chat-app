"""
ChatRoom — Python WebSocket Server v3
==========================================
New in v3:
  • User authentication (register / login / logout)
  • SQLite database (users + message history)
  • Password hashing with bcrypt
  • JWT session tokens (via Flask-Login)
  • Persistent message history per room
  • All v2 features retained

Dependencies:
    pip install flask flask-socketio eventlet flask-login bcrypt

Run:
    python server.py
Then open: http://localhost:5000
"""

from flask import Flask, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime
import os, html, time, re, sqlite3, hashlib, secrets, bcrypt, json

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "lumina-secret-change-in-production-2024")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet",
    max_http_buffer_size=10 * 1024 * 1024,
    manage_session=False,
)

login_manager = LoginManager(app)
login_manager.login_view = "serve_login"

# ─── Database setup ──────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "chatroom.db")

def get_db():
    """Return a thread-local DB connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    UNIQUE NOT NULL COLLATE NOCASE,
            email       TEXT    UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT  NOT NULL,
            avatar      TEXT    NOT NULL DEFAULT '🙂',
            avatar_bg   TEXT    NOT NULL DEFAULT '#1e1a3a',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            last_seen   TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          TEXT    PRIMARY KEY,
            room        TEXT,
            dm_key      TEXT,
            sender_name TEXT    NOT NULL,
            sender_avatar TEXT,
            sender_avatar_bg TEXT,
            text        TEXT    NOT NULL DEFAULT '',
            image_url   TEXT,
            reply_to    TEXT,
            reactions   TEXT    NOT NULL DEFAULT '{}',
            deleted     INTEGER NOT NULL DEFAULT 0,
            edited      INTEGER NOT NULL DEFAULT 0,
            created_at  INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room);
        CREATE INDEX IF NOT EXISTS idx_messages_dm   ON messages(dm_key);
        CREATE INDEX IF NOT EXISTS idx_messages_ts   ON messages(created_at);
    """)
    conn.commit()
    conn.close()

init_db()

# ─── User model ──────────────────────────────────────────────────────────────────
class User(UserMixin):
    def __init__(self, row):
        self.id        = row["id"]
        self.username  = row["username"]
        self.email     = row["email"]
        self.avatar    = row["avatar"]
        self.avatar_bg = row["avatar_bg"]

    @staticmethod
    def get_by_id(uid):
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        return User(row) if row else None

    @staticmethod
    def get_by_username(name):
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (name,)).fetchone()
        conn.close()
        return User(row) if row else None

    @staticmethod
    def get_by_email(email):
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
        conn.close()
        return User(row) if row else None

@login_manager.user_loader
def load_user(uid):
    return User.get_by_id(int(uid))

# ─── In-memory state ─────────────────────────────────────────────────────────────
online_users: dict[str, dict] = {}       # sid → user info

VALID_ROOMS = {"general", "design", "tech", "music", "random"}

# ─── Helpers ─────────────────────────────────────────────────────────────────────
def ts_ms() -> int:
    return int(time.time() * 1000)

def fmt_ts() -> str:
    return datetime.now().strftime("%H:%M")

def sanitise(s: str, max_len: int = 2000) -> str:
    return html.escape(str(s or "").strip()[:max_len])

def broadcast_user_list(room: str):
    members = [
        {"name": u["name"], "avatar": u["avatar"], "avatarBg": u.get("avatarBg", "#1e1a3a")}
        for u in online_users.values() if u.get("room") == room
    ]
    emit("user_list", {"room": room, "users": members}, to=room)

def is_valid_image_url(url: str) -> bool:
    return bool(url and url.startswith("data:image/") and len(url) < 7 * 1024 * 1024)

def is_valid_dm_key(key: str, user_name: str) -> bool:
    if not key.startswith("dm_") or "__" not in key:
        return False
    parts = key.replace("dm_", "").split("__")
    return len(parts) == 2 and user_name in parts

def msg_row_to_dict(row) -> dict:
    reply_to = None
    if row["reply_to"]:
        try:
            reply_to = json.loads(row["reply_to"])
        except Exception:
            pass
    reactions = {}
    try:
        reactions = json.loads(row["reactions"])
    except Exception:
        pass
    return {
        "id":        row["id"],
        "name":      row["sender_name"],
        "avatar":    row["sender_avatar"] or "🙂",
        "avatarBg":  row["sender_avatar_bg"] or "#1e1a3a",
        "text":      row["text"],
        "imageUrl":  row["image_url"],
        "replyTo":   reply_to,
        "reactions": reactions,
        "deleted":   bool(row["deleted"]),
        "edited":    bool(row["edited"]),
        "ts":        row["created_at"],
        "room":      row["room"],
        "dm_key":    row["dm_key"],
    }

def load_history_room(room: str, limit: int = 50) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM messages WHERE room=? ORDER BY created_at DESC LIMIT ?",
        (room, limit)
    ).fetchall()
    conn.close()
    return [msg_row_to_dict(r) for r in reversed(rows)]

def load_history_dm(dm_key: str, limit: int = 50) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM messages WHERE dm_key=? ORDER BY created_at DESC LIMIT ?",
        (dm_key, limit)
    ).fetchall()
    conn.close()
    return [msg_row_to_dict(r) for r in reversed(rows)]

def save_message(msg: dict):
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO messages
        (id, room, dm_key, sender_name, sender_avatar, sender_avatar_bg,
         text, image_url, reply_to, reactions, deleted, edited, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        msg["id"],
        msg.get("room"),
        msg.get("dm_key"),
        msg["name"],
        msg.get("avatar"),
        msg.get("avatarBg"),
        msg.get("text", ""),
        msg.get("imageUrl"),
        json.dumps(msg["replyTo"]) if msg.get("replyTo") else None,
        json.dumps(msg.get("reactions", {})),
        int(msg.get("deleted", False)),
        int(msg.get("edited", False)),
        msg.get("ts", ts_ms()),
    ))
    conn.commit()
    conn.close()

def db_update_message(msg_id: str, **kwargs):
    if not kwargs:
        return
    parts = ", ".join(f"{k}=?" for k in kwargs)
    conn = get_db()
    conn.execute(f"UPDATE messages SET {parts} WHERE id=?", (*kwargs.values(), msg_id))
    conn.commit()
    conn.close()

def build_message(data: dict, user: dict, room: str = None, dm_key: str = None) -> dict:
    text = sanitise(data.get("text", ""))
    image_url = data.get("imageUrl", "")
    if image_url and not is_valid_image_url(image_url):
        image_url = ""

    reply_raw = data.get("replyTo")
    reply_to = None
    if isinstance(reply_raw, dict):
        reply_to = {
            "id":   sanitise(str(reply_raw.get("id", ""))[:64], 64),
            "name": sanitise(str(reply_raw.get("name", ""))[:32], 32),
            "text": sanitise(str(reply_raw.get("text", ""))[:200], 200),
        }

    msg = {
        "id":        request.sid[:8] + str(ts_ms()),
        "name":      user["name"],
        "avatar":    user["avatar"],
        "avatarBg":  user.get("avatarBg", "#1e1a3a"),
        "text":      text,
        "imageUrl":  image_url or None,
        "replyTo":   reply_to,
        "ts":        ts_ms(),
        "room":      room,
        "dm_key":    dm_key,
        "deleted":   False,
        "edited":    False,
        "reactions": {},
    }
    return msg

def find_message_in_db(msg_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
    conn.close()
    return msg_row_to_dict(row) if row else None

# ─── HTTP routes — Auth ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main chat app (requires login)."""
    path = os.path.join(os.path.dirname(__file__), "chat_app.html")
    if not os.path.exists(path):
        return "<h1>Place chat_app.html in the same directory as server.py</h1>", 404
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.route("/login")
def serve_login():
    path = os.path.join(os.path.dirname(__file__), "auth.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Place auth.html in the same directory as server.py</h1>", 404

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data     = request.get_json(force=True) or {}
    username = sanitise(data.get("username", ""), 32).strip()
    email    = sanitise(data.get("email", ""), 120).strip()
    password = data.get("password", "")
    avatar   = data.get("avatar", "🙂")
    avatar_bg = data.get("avatarBg", "#1e1a3a")

    # Validation
    if not username or not email or not password:
        return jsonify({"ok": False, "error": "All fields are required"}), 400
    if len(username) < 2:
        return jsonify({"ok": False, "error": "Username must be at least 2 characters"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "Password must be at least 6 characters"}), 400
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", username):
        return jsonify({"ok": False, "error": "Username can only contain letters, numbers, _ - ."}), 400
    if "@" not in email:
        return jsonify({"ok": False, "error": "Invalid email address"}), 400

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, email, password_hash, avatar, avatar_bg) VALUES (?,?,?,?,?)",
            (username, email, password_hash, avatar, avatar_bg)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
        user = User(row)
        login_user(user, remember=True)
        return jsonify({"ok": True, "user": {"username": user.username, "avatar": user.avatar, "avatarBg": user.avatar_bg}})
    except sqlite3.IntegrityError as e:
        if "username" in str(e):
            return jsonify({"ok": False, "error": "Username already taken"}), 409
        if "email" in str(e):
            return jsonify({"ok": False, "error": "Email already registered"}), 409
        return jsonify({"ok": False, "error": "Registration failed"}), 500
    finally:
        conn.close()

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data     = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"ok": False, "error": "Username and password required"}), 400

    conn = get_db()
    row  = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
    if not row:
        # also try by email
        row = conn.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (username,)).fetchone()
    conn.close()

    if not row or not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return jsonify({"ok": False, "error": "Invalid username or password"}), 401

    user = User(row)
    login_user(user, remember=True)

    # Update last_seen
    conn = get_db()
    conn.execute("UPDATE users SET last_seen=datetime('now') WHERE id=?", (user.id,))
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "user": {"username": user.username, "avatar": user.avatar, "avatarBg": user.avatar_bg}})

@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    logout_user()
    return jsonify({"ok": True})

@app.route("/api/auth/me")
def api_me():
    if current_user.is_authenticated:
        return jsonify({"ok": True, "user": {"username": current_user.username, "avatar": current_user.avatar, "avatarBg": current_user.avatar_bg}})
    return jsonify({"ok": False}), 401

# ─── HTTP routes — History ───────────────────────────────────────────────────────
@app.route("/api/history/<room>")
def history_api(room: str):
    if room not in VALID_ROOMS:
        return jsonify([])
    msgs = load_history_room(room, 50)
    return jsonify(msgs)

# ─── SocketIO: connection lifecycle ─────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    print(f"[+] {request.sid} connected")

@socketio.on("disconnect")
def on_disconnect():
    user = online_users.pop(request.sid, None)
    if user:
        room = user.get("room", "general")
        emit("system", {"text": f'{user["name"]} left the chat', "ts": fmt_ts()}, to=room)
        broadcast_user_list(room)
    print(f"[-] {request.sid} disconnected")

@socketio.on("ping_latency")
def on_ping(data):
    emit("pong_latency", {"client_ts": data.get("ts")})

# ─── SocketIO: room management ──────────────────────────────────────────────────
@socketio.on("join")
def on_join(data: dict):
    name      = sanitise(data.get("name", "Anonymous"), 32)
    avatar    = data.get("avatar", "🙂")
    avatar_bg = data.get("avatarBg", "#1e1a3a")
    room      = data.get("room", "general")
    if room not in VALID_ROOMS:
        room = "general"

    online_users[request.sid] = {
        "name": name, "avatar": avatar, "avatarBg": avatar_bg,
        "room": room, "sid": request.sid,
    }
    join_room(room)

    history = load_history_room(room, 50)
    emit("history", {"room": room, "messages": history})
    emit("system", {"text": f"{name} joined #{room}", "ts": fmt_ts()}, to=room)
    broadcast_user_list(room)
    print(f"[join] {name} → #{room}")

@socketio.on("switch_room")
def on_switch_room(data: dict):
    user     = online_users.get(request.sid)
    if not user:
        return
    old_room = user.get("room", "general")
    new_room = data.get("room", "general")
    if new_room not in VALID_ROOMS:
        return

    leave_room(old_room)
    join_room(new_room)
    online_users[request.sid]["room"] = new_room

    emit("system", {"text": f'{user["name"]} left', "ts": fmt_ts()}, to=old_room)
    broadcast_user_list(old_room)

    history = load_history_room(new_room, 50)
    emit("history", {"room": new_room, "messages": history})
    emit("system", {"text": f'{user["name"]} joined #{new_room}', "ts": fmt_ts()}, to=new_room)
    broadcast_user_list(new_room)

# ─── SocketIO: request DM history ───────────────────────────────────────────────
@socketio.on("dm_history")
def on_dm_history(data: dict):
    dm_key = data.get("dm_key", "")
    user   = online_users.get(request.sid)
    if not user:
        return
    if not is_valid_dm_key(dm_key, user["name"]):
        return
    history = load_history_dm(dm_key, 50)
    emit("dm_history", {"dm_key": dm_key, "messages": history})

# ─── SocketIO: messaging ─────────────────────────────────────────────────────────
@socketio.on("message")
def on_message(data: dict):
    user = online_users.get(request.sid)
    if not user:
        return
    room = data.get("room", "general")
    if room not in VALID_ROOMS:
        return
    msg = build_message(data, user, room=room)
    if not msg["text"] and not msg["imageUrl"]:
        return

    save_message(msg)
    emit("message", msg, to=room)
    print(f'[msg] {user["name"]} #{room}: {msg["text"][:60]}')

# ─── SocketIO: edit ──────────────────────────────────────────────────────────────
@socketio.on("edit_message")
def on_edit_message(data: dict):
    user = online_users.get(request.sid)
    if not user:
        return
    msg_id   = str(data.get("message_id", ""))
    new_text = sanitise(data.get("new_text", ""))
    room     = data.get("room", "general")
    dm_key   = data.get("dm_key")
    if not new_text:
        return

    msg = find_message_in_db(msg_id)
    if not msg or msg["name"] != user["name"] or msg["deleted"]:
        return

    db_update_message(msg_id, text=new_text, edited=1)
    emit("message_edited", {"message_id": msg_id, "new_text": new_text, "room": room, "dm_key": dm_key},
         to=(request.sid if dm_key else room))
    if dm_key:
        parts = dm_key.replace("dm_","").split("__")
        for sid, u in online_users.items():
            if u["name"] in parts and sid != request.sid:
                emit("message_edited", {"message_id": msg_id, "new_text": new_text, "dm_key": dm_key}, to=sid)
    print(f'[edit] {user["name"]} edited {msg_id}')

# ─── SocketIO: delete ────────────────────────────────────────────────────────────
@socketio.on("delete_message")
def on_delete_message(data: dict):
    user   = online_users.get(request.sid)
    if not user:
        return
    msg_id = str(data.get("message_id", ""))
    room   = data.get("room", "general")
    dm_key = data.get("dm_key")

    msg = find_message_in_db(msg_id)
    if not msg or msg["name"] != user["name"]:
        return

    db_update_message(msg_id, deleted=1, text="", image_url=None)
    emit("message_deleted", {"message_id": msg_id, "room": room, "dm_key": dm_key},
         to=(request.sid if dm_key else room))
    if dm_key:
        parts = dm_key.replace("dm_","").split("__")
        for sid, u in online_users.items():
            if u["name"] in parts and sid != request.sid:
                emit("message_deleted", {"message_id": msg_id, "dm_key": dm_key}, to=sid)
    print(f'[delete] {user["name"]} deleted {msg_id}')

# ─── SocketIO: direct messages ───────────────────────────────────────────────────
@socketio.on("dm")
def on_dm(data: dict):
    sender = online_users.get(request.sid)
    if not sender:
        return

    to_name = sanitise(data.get("to", ""), 32)
    dm_k    = data.get("dm_key", "")
    if not is_valid_dm_key(dm_k, sender["name"]):
        return

    msg = build_message(data, sender, dm_key=dm_k)
    msg["to"] = to_name
    if not msg["text"] and not msg["imageUrl"]:
        return

    save_message(msg)

    recipient_sid = next((sid for sid, u in online_users.items() if u["name"] == to_name), None)
    if recipient_sid:
        emit("dm", msg, to=recipient_sid)
    emit("dm", msg, to=request.sid)
    print(f'[dm] {sender["name"]} → {to_name}: {msg["text"][:60]}')

# ─── SocketIO: typing ────────────────────────────────────────────────────────────
@socketio.on("typing")
def on_typing(data: dict):
    user = online_users.get(request.sid)
    if not user:
        return
    room = data.get("room", "general")
    emit("typing", {"name": user["name"], "avatar": user["avatar"]},
         to=room, include_self=False)

# ─── SocketIO: reactions ─────────────────────────────────────────────────────────
@socketio.on("reaction")
def on_reaction(data: dict):
    user = online_users.get(request.sid)
    if not user:
        return
    msg_id = str(data.get("message_id", ""))
    emoji  = data.get("emoji", "")
    room   = data.get("room", "general")
    dm_k   = data.get("dm_key")

    msg = find_message_in_db(msg_id)
    if msg:
        reactions = msg["reactions"] or {}
        if emoji not in reactions:
            reactions[emoji] = []
        if user["name"] not in reactions[emoji]:
            reactions[emoji].append(user["name"])
        db_update_message(msg_id, reactions=json.dumps(reactions))

    payload = {"message_id": msg_id, "emoji": emoji, "name": user["name"], "room": room}
    if dm_k:
        parts = dm_k.replace("dm_","").split("__")
        for sid, u in online_users.items():
            if u["name"] in parts:
                emit("reaction", payload, to=sid)
    else:
        emit("reaction", payload, to=room, include_self=False)

# ─── Entry point ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"""
╔══════════════════════════════════════════╗
║   ✦  ChatRoom Server v3              ║
║      http://localhost:{port}               ║
║                                          ║
║  Auth: register · login · sessions       ║
║  DB:   SQLite persistent storage         ║
║  v2:   edit · delete · reply · images    ║
╚══════════════════════════════════════════╝
""")
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
