import os
import json
import httpx
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from mangum import Mangum

# --- Settings ---
SECRET_KEY = os.environ.get("SECRET_KEY", "super_secret_key_change_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

DATABASE_URL = os.environ.get("DATABASE_URL", "libsql://streakforge-bharath-vk-18.aws-ap-south-1.turso.io")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

# Convert libsql:// to https:// for HTTP API
TURSO_HTTP_URL = DATABASE_URL.replace("libsql://", "https://", 1).rstrip("/") + "/v2/pipeline"

# --- Turso HTTP API Helper ---
def turso_execute(sql, args=None):
    """Execute a single SQL statement via Turso HTTP API and return results."""
    stmt = {"type": "execute", "stmt": {"sql": sql}}
    if args:
        stmt["stmt"]["args"] = [_convert_arg(a) for a in args]
    
    payload = {"requests": [stmt, {"type": "close"}]}
    headers = {"Authorization": f"Bearer {TURSO_AUTH_TOKEN}", "Content-Type": "application/json"}
    
    resp = httpx.post(TURSO_HTTP_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
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
    
    return {"rows": rows, "columns": cols, "affected": response.get("affected_row_count", 0), "last_id": response.get("last_insert_rowid", None)}

def _convert_arg(value):
    """Convert Python value to Turso API argument format."""
    if value is None:
        return {"type": "null", "value": None}
    elif isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    elif isinstance(value, float):
        return {"type": "float", "value": value}
    elif isinstance(value, str):
        return {"type": "text", "value": value}
    else:
        return {"type": "text", "value": str(value)}

def _extract_value(cell):
    """Extract value from Turso API cell format."""
    if cell is None or cell.get("type") == "null":
        return None
    elif cell.get("type") == "integer":
        return int(cell["value"])
    elif cell.get("type") == "float":
        return float(cell["value"])
    else:
        return cell.get("value")

# --- Initialize Database Tables ---
def init_db():
    turso_execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL
        )
    """)
    turso_execute("""
        CREATE TABLE IF NOT EXISTS streaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT,
            icon TEXT,
            color TEXT,
            frequency TEXT,
            reminderTime TEXT,
            active INTEGER DEFAULT 1,
            startDate TEXT,
            history TEXT DEFAULT '{}',
            freezesLeft INTEGER DEFAULT 3,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

try:
    init_db()
    print("Database initialized successfully")
except Exception as e:
    print(f"Warning: DB init error (will retry): {e}")

# --- Auth Utils ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- Pydantic Schemas ---
class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class StreakBase(BaseModel):
    title: str
    category: str
    icon: str
    color: str
    frequency: str
    reminderTime: str

class StreakCreate(StreakBase):
    startDate: str
    history: Dict[str, bool] = {}

class StreakUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    frequency: Optional[str] = None
    reminderTime: Optional[str] = None
    history: Optional[Dict[str, bool]] = None
    freezesLeft: Optional[int] = None
    active: Optional[bool] = None

class StreakResponse(StreakBase):
    id: int
    user_id: int
    active: bool
    startDate: str
    history: Dict[str, bool]
    freezesLeft: int

# --- FastAPI App ---
app = FastAPI(title="StreakForge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper to get current user from token ---
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    result = turso_execute("SELECT id, username FROM users WHERE username = ?", [username])
    if not result["rows"]:
        raise credentials_exception
    row = result["rows"][0]
    return {"id": row[0], "username": row[1]}

# --- Helper to convert DB row to streak dict ---
def row_to_streak(row):
    return {
        "id": row[0],
        "title": row[1],
        "category": row[2],
        "icon": row[3],
        "color": row[4],
        "frequency": row[5],
        "reminderTime": row[6],
        "active": bool(row[7]),
        "startDate": row[8],
        "history": json.loads(row[9]) if row[9] else {},
        "freezesLeft": row[10],
        "user_id": row[11],
    }

# --- Health Check ---
@app.get("/health")
def health_check():
    info = {"status": "ok", "token_set": bool(TURSO_AUTH_TOKEN), "http_url": TURSO_HTTP_URL[:50] + "..."}
    try:
        result = turso_execute("SELECT 1")
        info["db_connection"] = "success"
    except Exception as e:
        info["db_connection"] = f"failed: {str(e)}"
    return info

# --- Auth Routes ---
@app.post("/register", response_model=Token)
def register(user: UserCreate):
    result = turso_execute("SELECT id FROM users WHERE username = ?", [user.username])
    if result["rows"]:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed = get_password_hash(user.password)
    turso_execute("INSERT INTO users (username, hashed_password) VALUES (?, ?)", [user.username, hashed])
    
    result = turso_execute("SELECT id, username FROM users WHERE username = ?", [user.username])
    row = result["rows"][0]
    access_token = create_access_token(data={"sub": row[1]}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    result = turso_execute("SELECT id, username, hashed_password FROM users WHERE username = ?", [form_data.username])
    if not result["rows"]:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    row = result["rows"][0]
    if not verify_password(form_data.password, row[2]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": row[1]}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me")
def read_users_me(current_user: dict = Depends(get_current_user)):
    return {"id": current_user["id"], "username": current_user["username"]}

# --- Streak Routes ---
@app.get("/api/streaks")
def get_streaks(current_user: dict = Depends(get_current_user)):
    result = turso_execute(
        "SELECT id, title, category, icon, color, frequency, reminderTime, active, startDate, history, freezesLeft, user_id FROM streaks WHERE user_id = ?",
        [current_user["id"]]
    )
    return [row_to_streak(row) for row in result["rows"]]

@app.post("/api/streaks")
def create_streak(streak: StreakCreate, current_user: dict = Depends(get_current_user)):
    history_json = json.dumps(streak.history)
    insert_result = turso_execute(
        "INSERT INTO streaks (title, category, icon, color, frequency, reminderTime, active, startDate, history, freezesLeft, user_id) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 3, ?)",
        [streak.title, streak.category, streak.icon, streak.color, streak.frequency, streak.reminderTime, streak.startDate, history_json, current_user["id"]]
    )
    
    result = turso_execute(
        "SELECT id, title, category, icon, color, frequency, reminderTime, active, startDate, history, freezesLeft, user_id FROM streaks WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        [current_user["id"]]
    )
    return row_to_streak(result["rows"][0])

@app.put("/api/streaks/{streak_id}")
def update_streak(streak_id: int, streak_update: StreakUpdate, current_user: dict = Depends(get_current_user)):
    result = turso_execute("SELECT id FROM streaks WHERE id = ? AND user_id = ?", [streak_id, current_user["id"]])
    if not result["rows"]:
        raise HTTPException(status_code=404, detail="Streak not found")
    
    update_data = streak_update.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No data to update")
    
    set_parts = []
    values = []
    for key, value in update_data.items():
        if key == "history":
            set_parts.append(f"{key} = ?")
            values.append(json.dumps(value))
        elif key == "active":
            set_parts.append(f"{key} = ?")
            values.append(1 if value else 0)
        else:
            set_parts.append(f"{key} = ?")
            values.append(value)
    
    values.extend([streak_id, current_user["id"]])
    turso_execute(f"UPDATE streaks SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?", values)
    
    result = turso_execute(
        "SELECT id, title, category, icon, color, frequency, reminderTime, active, startDate, history, freezesLeft, user_id FROM streaks WHERE id = ? AND user_id = ?",
        [streak_id, current_user["id"]]
    )
    return row_to_streak(result["rows"][0])

@app.delete("/api/streaks/{streak_id}")
def delete_streak(streak_id: int, current_user: dict = Depends(get_current_user)):
    result = turso_execute("SELECT id FROM streaks WHERE id = ? AND user_id = ?", [streak_id, current_user["id"]])
    if not result["rows"]:
        raise HTTPException(status_code=404, detail="Streak not found")
    
    turso_execute("DELETE FROM streaks WHERE id = ? AND user_id = ?", [streak_id, current_user["id"]])
    return {"status": "success"}

# --- Vercel Serverless Handler ---
handler = Mangum(app)
