import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Cookie, HTTPException, Response
from cryptography.fernet import Fernet
from . import db
from .config import DATA_DIR, SECURE_COOKIE


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000)
    return salt + ':' + base64.b64encode(digest).decode()


def verify_password(password, stored):
    salt, digest = stored.split(':')
    candidate = base64.b64encode(hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000)).decode()
    return hmac.compare_digest(candidate, digest)


def session_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(response: Response, user_id):
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    with db.transaction() as conn:
        conn.execute('INSERT INTO sessions VALUES(?,?,?)', (session_hash(token), user_id, expires))
        conn.execute('DELETE FROM sessions WHERE expires_at < ?', (db.now(),))
    response.set_cookie('studio_session', token, httponly=True, secure=SECURE_COOKIE,
                        samesite='strict', max_age=604800, path='/')


def current_user(studio_session: str | None = Cookie(default=None)):
    if not studio_session:
        raise HTTPException(401, '请先登录')
    user = db.one('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires_at>?',
                  (session_hash(studio_session), db.now()))
    if not user:
        raise HTTPException(401, '登录已过期，请重新登录')
    return user


def public_user(user):
    return {k: user[k] for k in ('id', 'email', 'name', 'role', 'balance', 'reserved', 'created_at')}


def cipher():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key_path = DATA_DIR / 'secret.key'
    if not key_path.exists():
        try:
            with key_path.open('xb') as file:
                file.write(Fernet.generate_key())
        except FileExistsError:
            pass
    return Fernet(key_path.read_bytes())


def encrypt(value):
    return cipher().encrypt(value.encode()).decode() if value else ''


def decrypt(value):
    return cipher().decrypt(value.encode()).decode() if value else ''


def sign_asset(asset_id, expires):
    key = (DATA_DIR / 'secret.key').read_bytes()
    return hmac.new(key, f'{asset_id}:{expires}'.encode(), hashlib.sha256).hexdigest()
