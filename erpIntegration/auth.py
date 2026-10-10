import os

from django.http import JsonResponse


def get_expected_api_key():
    key_path = '/etc/cyberpanel/softi-erp.key'
    if os.path.isfile(key_path):
        with open(key_path, encoding='utf-8') as handle:
            value = handle.read().strip()
            if value:
                return value
    return os.environ.get('SOFTI_ERP_API_KEY', '').strip()


def require_api_key(request):
    expected = get_expected_api_key()
    if not expected:
        return JsonResponse(
            {
                'status': 0,
                'error_message': 'SOFTI_ERP_API_KEY no configurada en el servidor',
            },
            status=503,
        )

    provided = request.headers.get('X-Softi-Api-Key', '').strip()
    if not provided:
        provided = request.META.get('HTTP_X_SOFTI_API_KEY', '').strip()

    if not provided or provided != expected:
        return JsonResponse(
            {'status': 0, 'error_message': 'API key inválida'},
            status=401,
        )

    return None
