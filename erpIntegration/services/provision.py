import json
import os
import secrets

from websiteFunctions.models import Websites
from websiteFunctions.website import WebsiteManager

from .external_refs import get_ref, set_ref


def _wait_status(path: str, timeout: int = 100) -> str:
    import time

    if not path:
        return ''
    deadline = time.time() + timeout
    last = ''
    while time.time() < deadline:
        try:
            with open(path, encoding='utf-8', errors='replace') as handle:
                last = handle.read()
        except OSError:
            last = ''
        if '[200]' in last or '[404]' in last:
            return last
        time.sleep(2)
    return last


def provision_website(payload: dict) -> dict:
    domain = (payload.get('domainName') or '').strip().lower()
    if not domain:
        return {'status': 0, 'error_message': 'domainName requerido'}

    external_ref = (payload.get('externalRef') or '').strip()
    existing = Websites.objects.filter(domain=domain).first()
    if existing:
        current_ref = get_ref(domain)
        if external_ref and current_ref and current_ref != external_ref:
            # Otro servicio del ERP ya es dueño de este sitio: no lo adoptamos.
            return {
                'status': 0,
                'createWebSiteStatus': 0,
                'domainName': domain,
                'error_message': 'El sitio ya existe y pertenece a otro servicio',
                'conflict': True,
            }
        if external_ref:
            try:
                set_ref(domain, external_ref)
            except ValueError:
                pass
        return {
            'status': 1,
            'createWebSiteStatus': 1,
            'domainName': domain,
            'externalRef': external_ref or get_ref(domain),
            'message': 'Sitio ya existía',
            'alreadyExisted': True,
        }

    admin_user = os.environ.get('SOFTI_CP_ADMIN_USER', 'admin')
    admin_pass = os.environ.get('SOFTI_CP_ADMIN_PASS', '')
    owner_email = payload.get('ownerEmail') or f'admin@{domain}'
    package_name = payload.get('packageName') or 'Default'
    ssl = 1 if payload.get('ssl', True) else 0

    api_data = {
        'adminUser': admin_user,
        'adminPass': admin_pass,
        'domainName': domain,
        'ownerEmail': owner_email,
        'adminEmail': owner_email,
        'packageName': package_name,
        'package': package_name,
        'websiteOwner': payload.get('websiteOwner') or admin_user,
        'phpSelection': payload.get('phpVersion') or 'PHP 8.3',
        'ownerPassword': payload.get('ownerPassword') or secrets.token_urlsafe(12),
        'ssl': ssl,
        'dkimCheck': 1,
        'openBasedir': 0,
    }

    if external_ref:
        api_data['externalRef'] = external_ref

    wm = WebsiteManager()
    # La API key ya autorizó la llamada. createWebsiteAPI además exige
    # SOFTI_CP_ADMIN_PASS y fuerza ssl=1. Sin esa clave usamos el alta
    # interna y respetamos ssl del pedido.
    if admin_pass:
        response = wm.createWebsiteAPI(api_data)
    else:
        from loginSystem.models import Administrator

        admin = Administrator.objects.filter(userName=admin_user).first()
        if admin is None:
            return {
                'status': 0,
                'error_message': f'No existe el administrador {admin_user}',
            }
        response = wm.submitWebsiteCreation(admin.pk, api_data)
    content = response.content.decode() if hasattr(response, 'content') else str(response)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {'status': 0, 'error_message': content or 'Error al crear sitio'}

    if data.get('createWebSiteStatus') == 1:
        status_log = _wait_status(data.get('tempStatusPath'))
        if '[200]' not in status_log:
            from .delete import delete_website

            last = status_log.strip().splitlines()[-1] if status_log.strip() else 'El alta no terminó'
            cleanup = delete_website(domain)
            return {
                'status': 0,
                'createWebSiteStatus': 0,
                'domainName': domain,
                'error_message': last[:400],
                'cleanup': cleanup.get('swept', []),
            }
        data['status'] = 1
        data['domainName'] = domain
        if external_ref:
            try:
                set_ref(domain, external_ref)
            except ValueError:
                pass
        data['externalRef'] = external_ref or get_ref(domain)
        data['alreadyExisted'] = False
    else:
        data['status'] = 0
        if not data.get('error_message'):
            data['error_message'] = 'createWebSiteStatus distinto de 1'

    return data
