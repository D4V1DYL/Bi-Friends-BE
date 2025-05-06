from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, EmailStr
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from config import supabase_client
import secrets
import smtplib
import jwt
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
from passlib.context import CryptContext
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import ssl

router = APIRouter()

# Rate Limiting Middleware
limiter = Limiter(key_func=get_remote_address)

SECRET_KEY = "27aa6d1a-519c-4d88-b265-cda5808c0fe5"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class RegisterRequest(BaseModel):
    username: str
    nim: str
    email: EmailStr
    password: str
    gender: str
    profile_picture: Optional[str] = None

class LoginRequest(BaseModel):
    nim: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    token: str
    new_password: str
    confirm_password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class VerifyTokenRequest(BaseModel):
    email: str
    token: str


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

#Backend Register (SELESAI)
@router.post('/register')
@limiter.limit("5/minute")
def register_user(request: Request,register_data:RegisterRequest):
    if not register_data.email.endswith("@binus.ac.id"):
        raise HTTPException(status_code=400, detail="Email harus menggunakan domain @binus.ac.id")

    hashed_password = pwd_context.hash(register_data.password).strip()
    response = supabase_client.table('msuser').insert({
        "username": register_data.username,
        "nim": register_data.nim,
        "email": register_data.email,
        "password": hashed_password,
        "gender": register_data.gender,
        "profile_picture": register_data.profile_picture,
        "created_at": datetime.utcnow().isoformat(),
        "friend_status": 0
    }).execute()
    if response.data is None or len(response.data) == 0:
        raise HTTPException(status_code=400, detail="Error creating user")

    return {"message": "User registered successfully"}

#Backend Login (SELESAI)
@router.post('/login', response_model=Token)
@limiter.limit("5/minute")
def login(request: Request, login_data: LoginRequest):
    response = supabase_client.table('msuser').select('password, nim').eq('nim', login_data.nim).maybe_single().execute()
    
    if response is None or len(response.data) == 0:
        raise HTTPException(status_code=401, detail="NIM atau password salah!")

    user = response.data
    hashed_password = user['password'].strip()

    if len(hashed_password) != 60:
        raise HTTPException(status_code=500, detail="Hash password rusak, silakan reset password.")

    if not pwd_context.verify(login_data.password, hashed_password):
        raise HTTPException(status_code=401, detail="NIM atau password salah!")

    access_token = create_access_token(data={"sub": user['nim'].strip()})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post('/forgot-password')
@limiter.limit("3/minute")
def forgot_password(request: Request, forgot_data: ForgotPasswordRequest):
    if not forgot_data.email.endswith("@binus.ac.id"):
        raise HTTPException(status_code=400, detail="Email harus menggunakan domain @binus.ac.id")
    
    response = supabase_client.table('msuser').select('email').eq('email', forgot_data.email).execute()
    if response.data:
        reset_token = ''.join([str(secrets.randbelow(10)) for _ in range(5)])
        supabase_client.table('password_reset').insert({"email": forgot_data.email, "token": reset_token, "created_at": datetime.utcnow().isoformat()}).execute()
        send_reset_email(forgot_data.email, reset_token)
        return {"message": "Cek email untuk reset password."}
    raise HTTPException(status_code=404, detail="Email tidak ditemukan!")

def send_reset_email(email, token):
    sender_email = "bifriends@nextora.my.id"
    sender_password = "wellplayed123"
    smtp_server = "mail.nextora.my.id"
    smtp_port = 465

    message = MIMEMultipart('alternative')
    message['Subject'] = "Reset Password - Bi-Friends"
    message['From'] = sender_email
    message['To'] = email
    message['X-Priority'] = '1'

    html = f"""
    <html>
      <body>
        <h2>Password Reset Request</h2>
        <p>You have requested to reset your password.</p>
        <p>Your reset token is: <strong>{token}</strong></p>
        <p>If you didn't request this, please ignore this email.</p>
        <br>
        <p>Best regards,</p>
        <p>Bi-Friends Team</p>
      </body>
    </html>
    """

    part = MIMEText(html, 'html')
    message.attach(part)

    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            server.login(sender_email, sender_password)
            server.send_message(message)
            print(f"Reset password email sent successfully to {email}")

    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send reset email: {str(e)}"
        )


@router.get("/check-token")
def check_token_validity(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"message": "Token is valid"}
    except jwt.PyJWTError:
        raise credentials_exception

@router.post('/verify-token')
@limiter.limit("10/minute")
def verify_token(request: Request, verify_data: VerifyTokenRequest):
    response = supabase_client.table('password_reset').select('*')\
        .eq('email', verify_data.email)\
        .eq('token', verify_data.token)\
        .maybe_single().execute()

    if not response :
        return {"message": "Token tidak valid atau email tidak cocok!", "status": False}

    reset_data = response.data
    expires_at = datetime.fromisoformat(reset_data['expires_at'])

    if datetime.utcnow() > expires_at:
        return {"message": "Token sudah kadaluarsa!", "status": False}

    return {"message": "Token valid, lanjutkan reset password.", "status": True}


@router.post('/reset-password')
@limiter.limit("10/minute")
def reset_password(request: Request, reset_data: ResetPasswordRequest):
    if reset_data.new_password != reset_data.confirm_password:
        raise HTTPException(status_code=400, detail="Password baru dan konfirmasi tidak cocok!")

    user_response = supabase_client.table('msuser').select('email')\
        .eq('email', reset_data.email).maybe_single().execute()

    if not user_response or not getattr(user_response, "data", None):
        raise HTTPException(status_code=404, detail="Email tidak ditemukan di sistem!")

    hashed_password = pwd_context.hash(reset_data.new_password).strip()

    update_response = supabase_client.table('msuser').update({'password': hashed_password})\
        .eq('email', reset_data.email).execute()

    if not update_response.data:
        raise HTTPException(status_code=500, detail="Gagal memperbarui password!")

    supabase_client.table('password_reset').delete()\
        .eq('email', reset_data.email).execute()

    return {"message": "Password berhasil diperbarui!", "status": True}
