import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .auth import require_api_key


def _json_error(message, status=400):
    return JsonResponse({'status': 0, 'error_message': message}, status=status)


@csrf_exempt
def provision(request):
    """
    POST /api/softi/v1/provision
    Crea sitio en CyberPanel (idempotente si el dominio ya existe).
    """
    if request.method != 'POST':
        return _json_error('Método no permitido', 405)

    auth_error = require_api_key(request)
    if auth_error:
        return auth_error

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _json_error('JSON inválido')

    from .services.provision import provision_website

    result = provision_website(payload)
    status_code = 200 if result.get('status') == 1 else 400
    return JsonResponse(result, status=status_code)


@csrf_exempt
def health(request):
    """
    GET /softi/v1/health
    Header: X-Softi-Api-Key
    """
    if request.method != 'GET':
        return _json_error('Método no permitido', 405)

    auth_error = require_api_key(request)
    if auth_error:
        return auth_error

    cyberpanel_version = None
    cyberpanel_build = None
    try:
        from baseTemplate.models import version as version_model

        ver = version_model.objects.get(pk=1)
        cyberpanel_version = ver.currentVersion
        cyberpanel_build = getattr(ver, 'build', None)
    except Exception:
        pass

    return JsonResponse(
        {
            'status': 1,
            'service': 'softi-erp-api',
            'fork': 'mis-mejoras',
            'apiVersion': 'v1',
            'cyberpanelVersion': cyberpanel_version,
            'cyberpanelBuild': cyberpanel_build,
        }
    )


@csrf_exempt
def websites_summary(request):
    """
    GET /softi/v1/websites
    Resumen de sitios en este servidor (lectura).
    """
    if request.method != 'GET':
        return _json_error('Método no permitido', 405)

    auth_error = require_api_key(request)
    if auth_error:
        return auth_error

    try:
        from websiteFunctions.models import Websites

        rows = list(
            Websites.objects.all().values('domain', 'adminEmail', 'state')[:500]
        )
        return JsonResponse(
            {
                'status': 1,
                'websiteCount': len(rows),
                'websites': rows,
            }
        )
    except Exception as exc:
        return _json_error(str(exc), 500)


@csrf_exempt
def website_detail(request, domain):
    """
    GET /softi/v1/websites/<domain>
    """
    if request.method != 'GET':
        return _json_error('Método no permitido', 405)

    auth_error = require_api_key(request)
    if auth_error:
        return auth_error

    domain = (domain or '').strip().lower()
    if not domain:
        return _json_error('Dominio requerido')

    try:
        from websiteFunctions.models import Websites

        site = Websites.objects.filter(domain=domain).first()
        if not site:
            return _json_error('Sitio no encontrado', 404)

        return JsonResponse(
            {
                'status': 1,
                'website': {
                    'domain': site.domain,
                    'adminEmail': site.adminEmail,
                    'state': site.state,
                    'phpSelection': getattr(site, 'phpSelection', None),
                    'package': getattr(site, 'package', None),
                },
            }
        )
    except Exception as exc:
        return _json_error(str(exc), 500)
