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
            'features': ['websites', 'provision', 'externalRef', 'delete', 'status', 'users', 'owner', 'usage', 'sso'],
        }
    )


@csrf_exempt
def websites_summary(request):
    """
    GET /api/softi/v1/websites
    Resumen de sitios (+ externalRef) para sync Softihost.
    """
    if request.method != 'GET':
        return _json_error('Método no permitido', 405)

    auth_error = require_api_key(request)
    if auth_error:
        return auth_error

    try:
        from .services.websites import list_websites

        rows = list_websites(500)
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
def website_status(request, domain):
    """
    POST /api/softi/v1/websites/<domain>/status  body: { state: Suspend | Un-Suspend }
    Idempotente: si ya está en ese estado responde status 1.
    """
    if request.method != 'POST':
        return _json_error('Método no permitido', 405)

    domain = (domain or '').strip().lower()
    if not domain:
        return _json_error('Dominio requerido')

    auth_error = require_api_key(request)
    if auth_error:
        return auth_error

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _json_error('JSON inválido')

    try:
        from .services.status import set_website_status

        result = set_website_status(domain, (payload.get('state') or '').strip())
        if result.get('status') == 1:
            return JsonResponse(result)
        return JsonResponse(result, status=404 if result.get('notFound') else 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@csrf_exempt
def website_detail(request, domain):
    """
    GET /api/softi/v1/websites/<domain>
    PATCH /api/softi/v1/websites/<domain>  body: { externalRef }
    DELETE /api/softi/v1/websites/<domain>  borra el website (vhost y archivos)
    """
    domain = (domain or '').strip().lower()
    if not domain:
        return _json_error('Dominio requerido')

    auth_error = require_api_key(request)
    if auth_error:
        return auth_error

    if request.method == 'PATCH':
        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return _json_error('JSON inválido')

        external_ref = (payload.get('externalRef') or '').strip()
        if not external_ref:
            return _json_error('externalRef requerido')

        try:
            from websiteFunctions.models import Websites
            from .services.external_refs import set_ref
            from .services.websites import serialize_website

            site = Websites.objects.filter(domain=domain).first()
            if not site:
                return _json_error('Sitio no encontrado', 404)

            set_ref(domain, external_ref)
            return JsonResponse(
                {
                    'status': 1,
                    'message': 'externalRef actualizado',
                    'website': serialize_website(site, external_ref),
                }
            )
        except ValueError as exc:
            return _json_error(str(exc))
        except Exception as exc:
            return _json_error(str(exc), 500)

    if request.method == 'DELETE':
        try:
            from .services.delete import delete_website

            result = delete_website(domain)
            status_code = 200 if result.get('status') == 1 else 400
            return JsonResponse(result, status=status_code)
        except Exception as exc:
            return _json_error(str(exc), 500)

    if request.method != 'GET':
        return _json_error('Método no permitido', 405)

    try:
        from websiteFunctions.models import Websites
        from .services.websites import serialize_website

        site = Websites.objects.filter(domain=domain).first()
        if not site:
            return _json_error('Sitio no encontrado', 404)

        return JsonResponse(
            {
                'status': 1,
                'website': serialize_website(site),
            }
        )
    except Exception as exc:
        return _json_error(str(exc), 500)


def _json_body(request):
    try:
        return json.loads(request.body or '{}'), None
    except json.JSONDecodeError:
        return None, _json_error('JSON inválido')


@csrf_exempt
def users(request):
    """
    POST /api/softi/v1/users  body: { userName, email, firstName, lastName }
    Crea (idempotente) el usuario de panel del cliente con ACL «user».
    """
    if request.method != 'POST':
        return _json_error('Método no permitido', 405)
    auth_error = require_api_key(request)
    if auth_error:
        return auth_error
    payload, error = _json_body(request)
    if error:
        return error
    try:
        from .services.users import ensure_user

        result = ensure_user(payload)
        return JsonResponse(result, status=200 if result.get('status') == 1 else 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@csrf_exempt
def website_owner(request, domain):
    """POST /api/softi/v1/websites/<domain>/owner  body: { userName }"""
    if request.method != 'POST':
        return _json_error('Método no permitido', 405)
    domain = (domain or '').strip().lower()
    auth_error = require_api_key(request)
    if auth_error:
        return auth_error
    payload, error = _json_body(request)
    if error:
        return error
    try:
        from .services.users import set_owner

        result = set_owner(domain, payload.get('userName') or '')
        if result.get('status') == 1:
            return JsonResponse(result)
        return JsonResponse(result, status=404 if result.get('notFound') else 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@csrf_exempt
def usage(request):
    """GET /api/softi/v1/usage?externalRef=<ServicioRecurso.id>&domains=a.com,b.pe"""
    if request.method != 'GET':
        return _json_error('Método no permitido', 405)
    auth_error = require_api_key(request)
    if auth_error:
        return auth_error
    try:
        from .services.usage import servicio_usage

        result = servicio_usage(
            request.GET.get('externalRef', ''), request.GET.get('domains', '')
        )
        if result.get('status') == 1:
            return JsonResponse(result)
        return JsonResponse(result, status=404 if result.get('notFound') else 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@csrf_exempt
def sso(request):
    """
    GET /api/softi/v1/sso?token=...
    Lo abre el navegador del cliente desde «Mi cuenta». Sin API key en header:
    la autenticación es el token firmado (ver services/sso.py).
    """
    from django.shortcuts import redirect

    if request.method != 'GET':
        return _json_error('Método no permitido', 405)

    from .auth import get_expected_api_key
    from .services.sso import client_ip_for_session, verify_token
    from .services.users import es_usuario_cliente

    secret = get_expected_api_key()
    if not secret:
        return _json_error('SOFTI_ERP_API_KEY no configurada en el servidor', 503)

    check = verify_token(request.GET.get('token', ''), secret)
    if not check.get('ok'):
        return redirect('/?softi_sso=' + ('expirado' if 'vencido' in check.get('error', '') else 'invalido'))

    from loginSystem.models import Administrator

    user = Administrator.objects.filter(userName=check['userName']).first()
    if user is None or not es_usuario_cliente(user):
        return redirect('/?softi_sso=invalido')

    request.session.flush()
    request.session['userID'] = user.pk
    request.session['ipAddr'] = client_ip_for_session(request)
    request.session.set_expiry(43200)
    return redirect('/base/')
