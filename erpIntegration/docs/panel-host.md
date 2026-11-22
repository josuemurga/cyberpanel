# panel.softi.host — publicación del panel sin puerto

> SOFTI-MEJORA. Parte vive en este repo y parte en la configuración del servidor
> (fuera de git). Este archivo documenta ambas para poder reconstruirlo.

## Resultado

| URL | Respuesta |
|-----|-----------|
| `https://panel.softi.host` | Panel (proxy LiteSpeed → `https://127.0.0.1:8090`) |
| `http://panel.softi.host` | 301 → `https://panel.softi.host` |
| `https://panel.softi.host:8090` | Panel directo (acceso de respaldo) |
| `cyberpanel.softi.host` (80/443) | 301 → `https://panel.softi.host` (conserva ruta) |
| `cyberpanel.softi.host:8090` | 301 → `https://panel.softi.host`, **excepto `/api/`** |

`/api/` no se redirige en el host antiguo: integraciones (el ERP) que aún usen
`https://cyberpanel.softi.host:8090` siguen funcionando.

## En el repo

- `erpIntegration/middleware.py` — `SoftiCanonicalHostMiddleware` (primero en
  `MIDDLEWARE` de `CyberCP/settings.py`). Env opcional: `SOFTI_PANEL_HOST`,
  `SOFTI_PANEL_LEGACY_HOSTS`.
- `CyberCP/secMiddleware.py` — `get_client_ip`: si `REMOTE_ADDR` es loopback
  (llega por el proxy), usa la última IP de `X-Forwarded-For`. Sin esto todos los
  usuarios serían `127.0.0.1` y el control «sesión ligada a la IP» no serviría.
- `erpIntegration/services/sso.py` — la sesión SSO guarda la misma IP.
- `GET /api/softi/v1/health` devuelve `clientIp` (diagnóstico del proxy).

## En el servidor (fuera de git)

1. **Proxy** — `/usr/local/lsws/conf/vhosts/panel.softi.host/vhost.conf`:
   ```
   extprocessor softipanel {
   type proxy
   address https://127.0.0.1:8090   # HTTPS: el 8090 no habla HTTP (con http:// había bucle)
   ...
   }
   ```
2. **`/home/panel.softi.host/public_html/.htaccess`** (al inicio):
   ```
   RewriteEngine On
   RewriteCond %{HTTPS} !=on
   RewriteCond %{REQUEST_URI} !^/\.well-known/acme-challenge/
   RewriteRule ^(.*)$ https://panel.softi.host/$1 [R=301,L]
   ```
   y al final el proxy: `REWRITERULE ^(.*)$ HTTP://softipanel/$1 [P]`.
3. **`/home/cyberpanel.softi.host/public_html/.htaccess`** (al inicio; el
   WordPress de ese sitio queda oculto, no borrado):
   ```
   RewriteEngine On
   RewriteCond %{REQUEST_URI} !^/\.well-known/acme-challenge/
   RewriteRule ^(.*)$ https://panel.softi.host/$1 [R=301,L]
   ```
   En `.htaccess` la ruta llega sin `/` inicial: `^/(.*)$` nunca coincide.
4. **Certificado del 8090** — acme.sh `panel.softi.host_ecc` con SAN
   `panel.softi.host` + `cyberpanel.softi.host`, instalado en
   `/etc/letsencrypt/live/panel.softi.host/` (lscpd lo usa vía symlinks en
   `/usr/local/lscp/conf/{cert,key}.pem`). Recarga tras renovar:
   `systemctl restart lscpd && /usr/local/lsws/bin/lswsctrl restart`.
   ```bash
   acme.sh --issue -d panel.softi.host -d cyberpanel.softi.host \
     -w /usr/local/lsws/Example/html --keylength ec-256 --force
   acme.sh --install-cert -d panel.softi.host --ecc \
     --cert-file /etc/letsencrypt/live/panel.softi.host/cert.pem \
     --key-file /etc/letsencrypt/live/panel.softi.host/privkey.pem \
     --fullchain-file /etc/letsencrypt/live/panel.softi.host/fullchain.pem \
     --reloadcmd "systemctl restart lscpd && /usr/local/lsws/bin/lswsctrl restart"
   ```

## ERP

`CYBERPANEL_PANEL_URL=https://panel.softi.host` (enlace «Entrar al panel»).
La credencial CyberPanel del ERP puede quedar en `https://cyberpanel.softi.host:8090`
o pasar a `https://panel.softi.host:8090`; ambas tienen certificado válido.
