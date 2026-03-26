import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from mangum import Mangum

# --- Settings & Database Config ---
SECRET_KEY = os.environ.get("SECRET_KEY", "super_secret_key_change_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

DATABASE_URL = os.environ.get("DATABASE_URL", "libsql://streakforge-bharath-vk-18.aws-ap-south-1.turso.io")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

# Turso uses libsql:// but SQLAlchemy needs sqlite+libsql:// prefix
if DATABASE_URL.startswith("libsql://"):
    DATABASE_URL = DATABASE_URL.replace("libsql://", "sqlite+libsql://", 1)

# Append auth token if available
if TURSO_AUTH_TOKEN:
    DATABASE_URL = f"{DATABASE_URL}?authToken={TURSO_AUTH_TOKEN}"

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False}
    )
except Exception as e:
    print(f"Warning: Engine creation error: {e}")
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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

# --- Database Models ---
class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    streaks = relationship("StreakDB", back_populates="owner")

class StreakDB(Base):
    __tablename__ = "streaks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    category = Column(String)
    icon = Column(String)
    color = Column(String)
    frequency = Column(String)
    reminderTime = Column(String)
    active = Column(Boolean, default=True)
    startDate = Column(String)
    history = Column(JSON, default=dict)
    freezesLeft = Column(Integer, default=3)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    owner = relationship("UserDB", back_populates="streaks")

# Table creation deferred to startup event for serverless compatibility

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

    class Config:
        from_attributes = True

# --- FastAPI App ---
app = FastAPI(title="StreakForge API")

@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Warning: Could not create tables: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# --- Auth Routes ---
@app.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(UserDB).filter(UserDB.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    db_user = UserDB(username=user.username, hashed_password=get_password_hash(user.password))
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    access_token = create_access_token(data={"sub": db_user.username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me")
def read_users_me(current_user: UserDB = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username}

# --- Streak Routes ---
@app.get("/api/streaks", response_model=List[StreakResponse])
def get_streaks(current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(StreakDB).filter(StreakDB.user_id == current_user.id).all()

@app.post("/api/streaks", response_model=StreakResponse)
def create_streak(streak: StreakCreate, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    db_streak = StreakDB(
        **streak.dict(),
        user_id=current_user.id,
        active=True,
        freezesLeft=3
    )
    db.add(db_streak)
    db.commit()
    db.refresh(db_streak)
    return db_streak

@app.put("/api/streaks/{streak_id}", response_model=StreakResponse)
def update_streak(streak_id: int, streak_update: StreakUpdate, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    db_streak = db.query(StreakDB).filter(StreakDB.id == streak_id, StreakDB.user_id == current_user.id).first()
    if not db_streak:
        raise HTTPException(status_code=404, detail="Streak not found")
        
    update_data = streak_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_streak, key, value)
        
    db.commit()
    db.refresh(db_streak)
    return db_streak

@app.delete("/api/streaks/{streak_id}")
def delete_streak(streak_id: int, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    db_streak = db.query(StreakDB).filter(StreakDB.id == streak_id, StreakDB.user_id == current_user.id).first()
    if not db_streak:
        raise HTTPException(status_code=404, detail="Streak not found")
        
    db.delete(db_streak)
    db.commit()
    return {"status": "success"}

# --- Vercel Serverless Handler ---
handler = Mangum(app)
