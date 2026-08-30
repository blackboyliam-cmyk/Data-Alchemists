from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Farmer, User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "This email is already registered.")
    lang = body.preferred_language if body.preferred_language in ("en", "hi", "mr") else "en"
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        role="farmer",
        full_name=body.full_name.strip(),
        phone=body.phone,
        preferred_language=lang,
    )
    db.add(user)
    db.flush()
    db.add(Farmer(user_id=user.id))
    db.commit()
    token = create_access_token(user.email, user.role)
    return TokenOut(access_token=token, role=user.role, language=user.preferred_language)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is not correct.")
    token = create_access_token(user.email, user.role)
    return TokenOut(access_token=token, role=user.role, language=user.preferred_language)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.put("/language")
def set_language(lang: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if lang not in ("en", "hi", "mr"):
        raise HTTPException(400, "Language must be en, hi, or mr.")
    user.preferred_language = lang
    db.commit()
    return {"preferred_language": lang}
