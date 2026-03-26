import os
import json
import traceback

# Step-by-step import test
errors = []

try:
    from fastapi import FastAPI
except Exception as e:
    errors.append(f"fastapi: {e}")

try:
    from pydantic import BaseModel
except Exception as e:
    errors.append(f"pydantic: {e}")

try:
    import httpx
except Exception as e:
    errors.append(f"httpx: {e}")

try:
    from mangum import Mangum
except Exception as e:
    errors.append(f"mangum: {e}")

try:
    from jose import jwt
except Exception as e:
    errors.append(f"python-jose: {e}")

try:
    from passlib.context import CryptContext
except Exception as e:
    errors.append(f"passlib: {e}")

try:
    from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
except Exception as e:
    errors.append(f"fastapi.security: {e}")

try:
    from fastapi.middleware.cors import CORSMiddleware
except Exception as e:
    errors.append(f"cors: {e}")

# Create minimal app
app = FastAPI(title="StreakForge Debug")

@app.get("/health")
def health():
    return {
        "status": "ok",
        "import_errors": errors if errors else "none",
        "env_vars": {
            "SECRET_KEY": bool(os.environ.get("SECRET_KEY")),
            "DATABASE_URL": bool(os.environ.get("DATABASE_URL")),
            "TURSO_AUTH_TOKEN": bool(os.environ.get("TURSO_AUTH_TOKEN")),
        }
    }

@app.get("/register")
def register_get():
    return {"detail": "Use POST to register"}

@app.post("/register")
def register_post():
    return {"detail": "Debug mode - register endpoint reached"}

@app.post("/token")
def token():
    return {"detail": "Debug mode - token endpoint reached"}

handler = Mangum(app)
