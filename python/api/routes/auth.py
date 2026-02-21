from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth import verify_password, create_token, get_current_user
from ..models import LoginRequest

router = APIRouter()


@router.post("/login")
def login(body: LoginRequest):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email=?", (body.email,)).fetchone()
    conn.close()

    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user["id"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "firstname": user["firstname"],
            "lastname": user["lastname"],
            "email": user["email"],
            "app_role": user["app_role"],
        }
    }


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user
