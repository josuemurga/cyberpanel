import json
import os
import secrets

from websiteFunctions.models import Websites
from websiteFunctions.website import WebsiteManager


def provision_website(payload: dict) -> dict:
    domain = (payload.get('domainName') or '').strip().lower()
    if not domain:
        return {'status': 0, 'error_message': 'domainName requerido'}

    external_ref = (payload.get('externalRef') or '').strip()
    existing = Websites.objects.filter(domain=domain).first()
    if existing:
        return {
            'status': 1,
            'createWebSiteStatus': 1,
            'domainName': domain,
            'externalRef': external_ref,
            'message': 'Sitio ya existía',
            'alreadyExisted': True,
        }

    admin_user = os.environ.get('SOFTI_CP_ADMIN_USER', 'admin')
    admin_pass = os.environ.get('SOFTI_CP_ADMIN_PASS', '')
    if not admin_pass:
        return {
            'status': 0,
            'error_message': 'SOFTI_CP_ADMIN_PASS no configurada en el servidor',
        }

    api_data = {
        'adminUser': admin_user,
        'adminPass': admin_pass,
        'domainName': domain,
        'ownerEmail': payload.get('ownerEmail') or f'admin@{domain}',
        'packageName': payload.get('packageName') or 'Default',
        'websiteOwner': payload.get('websiteOwner') or admin_user,
        'phpSelection': payload.get('phpVersion') or 'PHP 8.3',
        'ownerPassword': payload.get('ownerPassword') or secrets.token_urlsafe(12),
        'ssl': 1 if payload.get('ssl', True) else 0,
        'dkimCheck': 1,
        'openBasedir': 0,
    }

    if external_ref:
        api_data['externalRef'] = external_ref

    wm = WebsiteManager()
    response = wm.createWebsiteAPI(api_data)
    content = response.content.decode() if hasattr(response, 'content') else str(response)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {'status': 0, 'error_message': content or 'Error al crear sitio'}

    if data.get('createWebSiteStatus') == 1:
        data['status'] = 1
        data['domainName'] = domain
        data['externalRef'] = external_ref
        data['alreadyExisted'] = False
    else:
        data['status'] = 0
        if not data.get('error_message'):
            data['error_message'] = 'createWebSiteStatus distinto de 1'

    return data
