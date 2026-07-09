from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from .. import auth, models, schemas
from ..database import get_db
from ..errors import UsernameTakenException, InvalidCredentialsException

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(req: schemas.RegisterRequest, db: Session = Depends(get_db)):
    # 1. Organization creation logic
    org = db.query(models.Organization).filter(models.Organization.name == req.org_name).first()
    is_new_org = False
    if not org:
        org = models.Organization(name=req.org_name)
        db.add(org)
        db.commit()
        db.refresh(org)
        is_new_org = True

    # 2. Check if username taken in org
    existing_user = db.query(models.User).filter(
        models.User.org_id == org.id,
        models.User.username == req.username
    ).first()
    
    if existing_user:
        raise UsernameTakenException()

    # Determine role
    role = "admin" if is_new_org else "member"

    # 3. Create user
    user = models.User(
        org_id=org.id,
        username=req.username,
        hashed_password=auth.hash_password(req.password),
        role=role
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return schemas.RegisterResponse(
        user_id=user.id,
        org_id=user.org_id,
        username=user.username,
        role=user.role
    )


@router.post("/login", response_model=schemas.TokenResponse)
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    org = db.query(models.Organization).filter(models.Organization.name == req.org_name).first()
    if not org:
        raise InvalidCredentialsException()

    user = db.query(models.User).filter(
        models.User.org_id == org.id,
        models.User.username == req.username
    ).first()

    if not user or not auth.verify_password(req.password, user.hashed_password):
        raise InvalidCredentialsException()

    return auth.create_token_pair(user)


@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh(req: schemas.RefreshRequest, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(req.refresh_token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        token_type = payload.get("type")
        if token_type != "refresh":
            raise credentials_exception
            
        jti = payload.get("jti")
        if not jti:
            raise credentials_exception
            
        # Check refresh token reuse
        with auth.token_lock:
            if jti in auth.used_refresh_tokens:
                raise credentials_exception
            auth.used_refresh_tokens.add(jti)
            
        user_id = payload.get("sub")
        org_id = payload.get("org")
        if not user_id or not org_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(
        models.User.id == int(user_id),
        models.User.org_id == int(org_id)
    ).first()
    
    if not user:
        raise credentials_exception

    return auth.create_token_pair(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(credentials: HTTPAuthorizationCredentials = Depends(auth.security_scheme)):
    token = credentials.credentials
    auth.blacklist_access_token(token)
    return None
