"""Suspender / reactivar un website (dunning del ERP Softihost)."""

import json
import os

ESTADOS_VALIDOS = ('Suspend', 'Un-Suspend')


def set_website_status(domain: str, state: str) -> dict:
    if state not in ESTADOS_VALIDOS:
        return {
            'status': 0,
            'error_message': 'state debe ser Suspend o Un-Suspend',
        }

    from websiteFunctions.models import Websites

    site = Websites.objects.filter(domain=domain).first()
    if not site:
        return {'status': 0, 'error_message': 'Sitio no encontrado', 'notFound': True}

    # Websites.state: 1 activo, 0 suspendido. Repetir la orden no es error.
    ya_aplicado = (state == 'Suspend' and site.state == 0) or (
        state == 'Un-Suspend' and site.state == 1
    )
    if ya_aplicado:
        return {
            'status': 1,
            'websiteStatus': 1,
            'domain': domain,
            'state': state,
            'message': 'El sitio ya estaba en ese estado',
            'alreadyApplied': True,
        }

    from loginSystem.models import Administrator
    from websiteFunctions.website import WebsiteManager

    admin_user = os.environ.get('SOFTI_CP_ADMIN_USER', 'admin')
    admin = Administrator.objects.filter(userName=admin_user).first()
    if admin is None:
        return {
            'status': 0,
            'error_message': f'No existe el administrador {admin_user}',
        }

    response = WebsiteManager().submitWebsiteStatus(
        admin.pk, {'websiteName': domain, 'state': state}
    )
    content = response.content.decode() if hasattr(response, 'content') else str(response)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {'status': 0, 'error_message': content or 'Respuesta inválida'}

    if data.get('websiteStatus') == 1:
        return {
            'status': 1,
            'websiteStatus': 1,
            'domain': domain,
            'state': state,
            'message': 'Sitio suspendido' if state == 'Suspend' else 'Sitio reactivado',
        }

    return {
        'status': 0,
        'error_message': str(data.get('error_message') or 'No se pudo cambiar el estado'),
    }
