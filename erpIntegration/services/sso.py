"""
Acceso al panel desde «Mi cuenta» de Softihost sin contraseña.

El ERP firma un token corto con la misma API key compartida:
    base64url(json{u, exp, jti}) + "." + base64url(hmac_sha256(payload))
Reglas: vence en ≤ 120 s, un solo uso (jti), solo usuarios con ACL «user».
"""

import base64
import hashlib
import hmac
import json
import os
import time

MAX_TTL = 120
JTI_PATH = os.environ.get(
    'SOFTI_SSO_JTI_PATH', '/etc/cyberpanel/softi-sso-jti.json'
)


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def verify_token(token: str, secret: str) -> dict:
    try:
        payload_b64, sig_b64 = (token or '').split('.', 1)
    except ValueError:
        return {'ok': False, 'error': 'Token mal formado'}

    expected = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    try:
        provided = _b64decode(sig_b64)
    except Exception:
        return {'ok': False, 'error': 'Firma inválida'}
    if not hmac.compare_digest(expected, provided):
        return {'ok': False, 'error': 'Firma inválida'}

    try:
        data = json.loads(_b64decode(payload_b64))
    except Exception:
        return {'ok': False, 'error': 'Token mal formado'}

    now = int(time.time())
    exp = int(data.get('exp') or 0)
    if exp < now or exp > now + MAX_TTL:
        return {'ok': False, 'error': 'Token vencido'}
    jti = str(data.get('jti') or '')
    if len(jti) < 16:
        return {'ok': False, 'error': 'Token sin jti'}
    if not _consumir_jti(jti, exp, now):
        return {'ok': False, 'error': 'Token ya usado'}
    return {'ok': True, 'userName': str(data.get('u') or '').strip().lower()}


def _consumir_jti(jti: str, exp: int, now: int) -> bool:
    """Registra el jti; False si ya existía. Falla cerrado si no puede escribir."""
    import fcntl

    try:
        fd = os.open(JTI_PATH, os.O_RDWR | os.O_CREAT, 0o660)
    except OSError:
        return False
    with os.fdopen(fd, 'r+', encoding='utf-8') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            raw = handle.read()
            usados = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            usados = {}
        usados = {k: v for k, v in usados.items() if int(v) >= now}
        if jti in usados:
            return False
        usados[jti] = exp
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(usados))
    return True


def client_ip_for_session(request) -> str:
    """Mismo formato que secMiddleware: IPv4 completa, IPv6 con 3 grupos."""
    ip = request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR') or ''
    if '.' in ip:
        return ip
    return ':'.join(ip.split(':')[:3])
