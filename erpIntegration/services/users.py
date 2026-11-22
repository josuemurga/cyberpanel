"""Usuarios de panel por cliente Softihost (ACL «user»)."""

import os
import re
import secrets

USERNAME_RE = re.compile(r'^[a-z][a-z0-9]{3,31}$')
NOMBRE_RE = re.compile(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ' -]")


def _admin():
    from loginSystem.models import Administrator

    admin_user = os.environ.get('SOFTI_CP_ADMIN_USER', 'admin')
    return Administrator.objects.filter(userName=admin_user).first()


def _nombre(valor, fallback):
    """CyberPanel exige nombres alfabéticos de 3+ caracteres."""
    limpio = NOMBRE_RE.sub('', valor or '').strip()[:30]
    return limpio if len(limpio) >= 3 else fallback


def es_usuario_cliente(user) -> bool:
    acl = getattr(user, 'acl', None)
    return bool(acl) and getattr(acl, 'name', '') == 'user'


def ensure_user(payload: dict) -> dict:
    """Crea el usuario si no existe. Idempotente; nunca toca usuarios admin."""
    from loginSystem.models import Administrator

    user_name = (payload.get('userName') or '').strip().lower()
    if not USERNAME_RE.match(user_name):
        return {'status': 0, 'error_message': 'userName inválido (a-z0-9, 4-32, empieza con letra)'}

    existing = Administrator.objects.filter(userName=user_name).first()
    if existing:
        if not es_usuario_cliente(existing):
            return {'status': 0, 'error_message': 'El usuario existe y no es de tipo cliente'}
        return {'status': 1, 'userName': user_name, 'created': False}

    admin = _admin()
    if admin is None:
        return {'status': 0, 'error_message': 'No existe el administrador del panel'}

    email = (payload.get('email') or '').strip()
    if '@' not in email:
        return {'status': 0, 'error_message': 'email requerido'}

    from userManagment.views import submitUserCreation

    request = {
        'userID': admin.pk,
        'firstName': _nombre(payload.get('firstName'), 'Cliente'),
        'lastName': _nombre(payload.get('lastName'), 'Softi'),
        'email': email,
        'userName': user_name,
        # El cliente entra por SSO; puede definir su clave desde el panel.
        'password': secrets.token_urlsafe(18),
        'websitesLimit': int(payload.get('websitesLimit') or 0),
        'selectedACL': 'user',
        'securityLevel': 'HIGH',
    }
    response = submitUserCreation(request)
    import json

    content = response.content.decode() if hasattr(response, 'content') else str(response)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {'status': 0, 'error_message': content or 'Respuesta inválida'}
    if data.get('createStatus') == 1:
        return {'status': 1, 'userName': user_name, 'created': True}
    return {'status': 0, 'error_message': str(data.get('error_message') or 'No se pudo crear el usuario')}


def set_owner(domain: str, user_name: str) -> dict:
    """Pasa el website (y su dominio de correo) al usuario cliente."""
    from loginSystem.models import Administrator
    from websiteFunctions.models import Websites

    site = Websites.objects.filter(domain=domain).first()
    if not site:
        return {'status': 0, 'error_message': 'Sitio no encontrado', 'notFound': True}

    user = Administrator.objects.filter(userName=(user_name or '').strip().lower()).first()
    if user is None:
        return {'status': 0, 'error_message': 'Usuario no encontrado'}
    if not es_usuario_cliente(user):
        return {'status': 0, 'error_message': 'Solo se asignan sitios a usuarios cliente'}

    if site.admin_id == user.pk:
        return {'status': 1, 'domain': domain, 'userName': user.userName, 'changed': False}

    site.admin = user
    site.save()
    return {'status': 1, 'domain': domain, 'userName': user.userName, 'changed': True}
