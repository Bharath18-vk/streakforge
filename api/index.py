from http.server import BaseHTTPRequestHandler
import os
import json
import hashlib
import hmac
import secrets
import time
import urllib.parse

# Try to import httpx, fall back to urllib
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    import urllib.request
    HAS_HTTPX = False

# --- Settings ---
SECRET_KEY = os.environ.get("SECRET_KEY", "super_secret_key_change_in_production")
DATABASE_URL = os.environ.get("DATABASE_URL", "libsql://streakforge-bharath-vk-18.aws-ap-south-1.turso.io")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")
TOKEN_EXPIRE_SECONDS = 60 * 60 * 24 * 7  # 7 days

# Convert libsql:// to https:// for HTTP API
TURSO_HTTP_URL = DATABASE_URL.replace("libsql://", "https://", 1).rstrip("/") + "/v2/pipeline"

# --- Simple JWT-like token using HMAC ---
import base64

def create_token(username):
    payload = json.dumps({"sub": username, "exp": int(time.time()) + TOKEN_EXPIRE_SECONDS})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def verify_token(token):
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload.get("sub")
    except Exception:
        return None

# --- Password hashing using hashlib (no bcrypt needed) ---
def hash_password(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
    return f"{salt}:{hashed}"

def check_password(password, stored):
    try:
        salt, hashed = stored.split(":")
        return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex() == hashed
    except Exception:
        return False

# --- Turso HTTP API ---
def turso_execute(sql, args=None):
    stmt = {"type": "execute", "stmt": {"sql": sql}}
    if args:
        stmt["stmt"]["args"] = [_convert_arg(a) for a in args]
    
    payload = json.dumps({"requests": [stmt, {"type": "close"}]})
    headers = {"Authorization": f"Bearer {TURSO_AUTH_TOKEN}", "Content-Type": "application/json"}
    
    if HAS_HTTPX:
        resp = httpx.post(TURSO_HTTP_URL, content=payload, headers=headers, timeout=30)
        data = resp.json()
    else:
        req = urllib.request.Request(TURSO_HTTP_URL, data=payload.encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    
    if "results" not in data or len(data["results"]) == 0:
        return {"rows": [], "columns": []}
    
    result = data["results"][0]
    if result.get("type") == "error":
        raise Exception(f"Turso error: {result['error']['message']}")
    
    response = result.get("response", {}).get("result", {})
    cols = [c["name"] for c in response.get("cols", [])]
    rows = []
    for row in response.get("rows", []):
        rows.append([_extract_value(cell) for cell in row])
    
    return {"rows": rows, "columns": cols}

def _convert_arg(value):
    if value is None:
        return {"type": "null", "value": None}
    elif isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    elif isinstance(value, float):
        return {"type": "float", "value": value}
    else:
        return {"type": "text", "value": str(value)}

def _extract_value(cell):
    if cell is None or cell.get("type") == "null":
        return None
    elif cell.get("type") == "integer":
        return int(cell["value"])
    elif cell.get("type") == "float":
        return float(cell["value"])
    else:
        return cell.get("value")

# --- Init DB ---
def init_db():
    turso_execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL
    )""")
    turso_execute("""CREATE TABLE IF NOT EXISTS streaks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, category TEXT, icon TEXT, color TEXT,
        frequency TEXT, reminderTime TEXT, active INTEGER DEFAULT 1,
        startDate TEXT, history TEXT DEFAULT '{}', freezesLeft INTEGER DEFAULT 3,
        user_id INTEGER, FOREIGN KEY (user_id) REFERENCES users(id)
    )""")

try:
    init_db()
except Exception as e:
    print(f"DB init warning: {e}")

# --- Row to dict helper ---
def row_to_streak(row):
    return {
        "id": row[0], "title": row[1], "category": row[2], "icon": row[3],
        "color": row[4], "frequency": row[5], "reminderTime": row[6],
        "active": bool(row[7]), "startDate": row[8],
        "history": json.loads(row[9]) if row[9] else {},
        "freezesLeft": row[10], "user_id": row[11],
    }

def get_user_from_request(headers):
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    username = verify_token(token)
    if not username:
        return None
    result = turso_execute("SELECT id, username FROM users WHERE username = ?", [username])
    if not result["rows"]:
        return None
    return {"id": result["rows"][0][0], "username": result["rows"][0][1]}

# --- Request Handler ---
class handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        body = self.rfile.read(length)
        content_type = self.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            return json.loads(body.decode())
        elif 'application/x-www-form-urlencoded' in content_type:
            return dict(urllib.parse.parse_qsl(body.decode()))
        return {}

    def _require_auth(self):
        user = get_user_from_request(self.headers)
        if not user:
            self._send_json({"detail": "Could not validate credentials"}, 401)
            return None
        return user

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        
        if path == "/health":
            info = {"status": "ok", "token_set": bool(TURSO_AUTH_TOKEN), "httpx": HAS_HTTPX}
            try:
                turso_execute("SELECT 1")
                info["db"] = "connected"
            except Exception as e:
                info["db"] = f"error: {str(e)}"
            self._send_json(info)
        
        elif path == "/users/me":
            user = self._require_auth()
            if user:
                self._send_json({"id": user["id"], "username": user["username"]})
        
        elif path == "/api/streaks":
            user = self._require_auth()
            if user:
                result = turso_execute(
                    "SELECT id, title, category, icon, color, frequency, reminderTime, active, startDate, history, freezesLeft, user_id FROM streaks WHERE user_id = ?",
                    [user["id"]]
                )
                self._send_json([row_to_streak(r) for r in result["rows"]])
        
        else:
            self._send_json({"detail": "Not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_body()
        
        if path == "/register":
            username = body.get("username", "")
            password = body.get("password", "")
            if not username or not password:
                self._send_json({"detail": "Username and password required"}, 400)
                return
            
            existing = turso_execute("SELECT id FROM users WHERE username = ?", [username])
            if existing["rows"]:
                self._send_json({"detail": "Username already registered"}, 400)
                return
            
            hashed = hash_password(password)
            turso_execute("INSERT INTO users (username, hashed_password) VALUES (?, ?)", [username, hashed])
            token = create_token(username)
            self._send_json({"access_token": token, "token_type": "bearer"})
        
        elif path == "/token":
            username = body.get("username", "")
            password = body.get("password", "")
            if not username or not password:
                self._send_json({"detail": "Username and password required"}, 400)
                return
            
            result = turso_execute("SELECT id, username, hashed_password FROM users WHERE username = ?", [username])
            if not result["rows"] or not check_password(password, result["rows"][0][2]):
                self._send_json({"detail": "Incorrect username or password"}, 400)
                return
            
            token = create_token(result["rows"][0][1])
            self._send_json({"access_token": token, "token_type": "bearer"})
        
        elif path == "/api/streaks":
            user = self._require_auth()
            if user:
                history_json = json.dumps(body.get("history", {}))
                turso_execute(
                    "INSERT INTO streaks (title, category, icon, color, frequency, reminderTime, active, startDate, history, freezesLeft, user_id) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 3, ?)",
                    [body.get("title", ""), body.get("category", ""), body.get("icon", ""), body.get("color", ""),
                     body.get("frequency", ""), body.get("reminderTime", ""), body.get("startDate", ""),
                     history_json, user["id"]]
                )
                result = turso_execute(
                    "SELECT id, title, category, icon, color, frequency, reminderTime, active, startDate, history, freezesLeft, user_id FROM streaks WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                    [user["id"]]
                )
                self._send_json(row_to_streak(result["rows"][0]))
        
        else:
            self._send_json({"detail": "Not found"}, 404)

    def do_PUT(self):
        path = self.path.split("?")[0]
        
        # /api/streaks/{id}
        if path.startswith("/api/streaks/"):
            user = self._require_auth()
            if not user:
                return
            
            try:
                streak_id = int(path.split("/")[-1])
            except ValueError:
                self._send_json({"detail": "Invalid streak ID"}, 400)
                return
            
            existing = turso_execute("SELECT id FROM streaks WHERE id = ? AND user_id = ?", [streak_id, user["id"]])
            if not existing["rows"]:
                self._send_json({"detail": "Streak not found"}, 404)
                return
            
            body = self._read_body()
            set_parts = []
            values = []
            for key in ["title", "category", "icon", "color", "frequency", "reminderTime", "startDate"]:
                if key in body:
                    set_parts.append(f"{key} = ?")
                    values.append(body[key])
            if "history" in body:
                set_parts.append("history = ?")
                values.append(json.dumps(body["history"]))
            if "freezesLeft" in body:
                set_parts.append("freezesLeft = ?")
                values.append(body["freezesLeft"])
            if "active" in body:
                set_parts.append("active = ?")
                values.append(1 if body["active"] else 0)
            
            if set_parts:
                values.extend([streak_id, user["id"]])
                turso_execute(f"UPDATE streaks SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?", values)
            
            result = turso_execute(
                "SELECT id, title, category, icon, color, frequency, reminderTime, active, startDate, history, freezesLeft, user_id FROM streaks WHERE id = ? AND user_id = ?",
                [streak_id, user["id"]]
            )
            self._send_json(row_to_streak(result["rows"][0]))
        else:
            self._send_json({"detail": "Not found"}, 404)

    def do_DELETE(self):
        path = self.path.split("?")[0]
        
        if path.startswith("/api/streaks/"):
            user = self._require_auth()
            if not user:
                return
            
            try:
                streak_id = int(path.split("/")[-1])
            except ValueError:
                self._send_json({"detail": "Invalid streak ID"}, 400)
                return
            
            existing = turso_execute("SELECT id FROM streaks WHERE id = ? AND user_id = ?", [streak_id, user["id"]])
            if not existing["rows"]:
                self._send_json({"detail": "Streak not found"}, 404)
                return
            
            turso_execute("DELETE FROM streaks WHERE id = ? AND user_id = ?", [streak_id, user["id"]])
            self._send_json({"status": "success"})
        else:
            self._send_json({"detail": "Not found"}, 404)

    def log_message(self, format, *args):
        pass  # Suppress default logging
