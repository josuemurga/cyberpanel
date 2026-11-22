"""
SOFTI-MEJORA: host canónico del panel.

Las URL antiguas (cyberpanel.softi.host, con o sin :8090) redirigen 301 a
https://panel.softi.host conservando ruta y query. /api/ queda fuera para no
romper integraciones (el ERP) que aún usen el host antiguo: un 301 en un POST
haría fallar la llamada.

Config por variables de entorno (opcional):
  SOFTI_PANEL_HOST          host canónico           (panel.softi.host)
  SOFTI_PANEL_LEGACY_HOSTS  hosts antiguos, CSV      (cyberpanel.softi.host)
"""

import os

from django.http import HttpResponsePermanentRedirect

CANONICAL = os.environ.get('SOFTI_PANEL_HOST', 'panel.softi.host').strip().lower()
LEGACY = {
    h.strip().lower()
    for h in os.environ.get('SOFTI_PANEL_LEGACY_HOSTS', 'cyberpanel.softi.host').split(',')
    if h.strip()
}


def _host_sin_puerto(request) -> str:
    # HTTP_HOST directo: get_host() lanza DisallowedHost antes de poder redirigir.
    host = (request.META.get('HTTP_HOST') or '').strip().lower()
    if host.startswith('['):  # IPv6 literal
        return host.split(']')[0] + ']'
    return host.split(':')[0]


class SoftiCanonicalHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            CANONICAL
            and _host_sin_puerto(request) in LEGACY
            and not request.path.startswith('/api/')
        ):
            return HttpResponsePermanentRedirect(
                'https://' + CANONICAL + request.get_full_path()
            )
        return self.get_response(request)
