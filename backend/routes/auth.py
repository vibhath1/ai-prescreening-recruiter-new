# backend/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User as DBUser
from backend.schemas.user import UserCreate, UserOut
from backend.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)

# -------------------------------------------------------------------------
# Router & Auth configuration
# -------------------------------------------------------------------------
router = APIRouter(prefix="/api", tags=["auth"])

# full absolute path is safest for Swagger/OAuth2 tooling
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

# -------------------------------------------------------------------------
# Register
# -------------------------------------------------------------------------
@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="register",
)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(DBUser).filter(DBUser.username == user_in.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    if db.query(DBUser).filter(DBUser.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user = DBUser(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# -------------------------------------------------------------------------
# Login  (single, unique definition)
# -------------------------------------------------------------------------
@router.post("/login", operation_id="login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user: DBUser | None = db.query(DBUser).filter(DBUser.username == form.username).first()

    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

# -------------------------------------------------------------------------
# Current-user dependency
# -------------------------------------------------------------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> DBUser:
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except Exception:  # broad catch; you can narrow it if desired
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user