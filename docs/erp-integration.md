# ERP Integration — Módulo `erpIntegration`

> **Estado:** ✅ D1 + externalRef + PATCH link · D2 provision en código  
> Contrato ERP: `nestjs-erp/docs/arquitectura/integraciones/cyberpanel-softi-api.md`

---

## Rutas activas

Todas bajo **`/api/softi/v1/`** (requieren pasar por `api/urls.py` — lscpd no enruta `/softi/v1/` en la raíz).

| Método | Ruta | Header | Notas |
|--------|------|--------|-------|
| GET | `/api/softi/v1/health` | `X-Softi-Api-Key` | Incluye `features` |
| GET | `/api/softi/v1/websites` | idem | Lista + `externalRef`, `package`, `state` |
| GET | `/api/softi/v1/websites/<domain>` | idem | Detalle |
| PATCH | `/api/softi/v1/websites/<domain>` | idem | Body `{ "externalRef": "<uuid>" }` |
| POST | `/api/softi/v1/provision` | idem | Crea sitio; persiste `externalRef` |

Ejemplo:

```bash
curl -sk -H "X-Softi-Api-Key: $(cat /etc/cyberpanel/softi-erp.key)" \
  https://127.0.0.1:8090/api/softi/v1/health
```

### externalRef (sync Softihost)

- Archivo: `/etc/cyberpanel/softi-external-refs.json` (override: `SOFTI_EXTERNAL_REFS_PATH`)
- Valor: UUID de `ServicioRecurso.id` en NestJS (**mismo** UUID en N websites del plan)
- Al provisionar con `externalRef` o con PATCH, se guarda el vínculo domain → UUID
- Plan usage: `GET /packages/fetchPlanUsage?groupBy=servicio` suma por ese UUID

```bash
curl -sk -X PATCH \
  -H "X-Softi-Api-Key: $(cat /etc/cyberpanel/softi-erp.key)" \
  -H "Content-Type: application/json" \
  -d '{"externalRef":"11111111-2222-3333-4444-555555555555"}' \
  https://127.0.0.1:8090/api/softi/v1/websites/ejemplo.com
```

---

## API key

```bash
# Generar
openssl rand -hex 24 | tee /etc/cyberpanel/softi-erp.key
chown root:cyberpanel /etc/cyberpanel/softi-erp.key
chmod 640 /etc/cyberpanel/softi-erp.key
```

El proceso Django (`cyberpanel`, uid 1000) debe poder leer el archivo.

La misma key va en el ERP: `CYBERPANEL_SOFTI_API_KEY`.

---

## Despliegue / actualización

```bash
cd /usr/local/CyberCP
# Copiar erpIntegration/ desde el repo softi-cp
python3 /tmp/patch-api-urls-softi.py   # idempotente si ya está parcheado
find erpIntegration -name '*.pyc' -delete
systemctl restart lscpd
# Asegurar que el proceso pueda escribir el JSON de refs:
touch /etc/cyberpanel/softi-external-refs.json
chown root:cyberpanel /etc/cyberpanel/softi-external-refs.json
chmod 660 /etc/cyberpanel/softi-external-refs.json
```

Archivos upstream tocados (marcar `# SOFTI-MEJORA`):

- `CyberCP/settings.py` → `'erpIntegration'` en `INSTALLED_APPS`
- `api/urls.py` → rutas `softi/v1/*`

---

## Código fuente local

Workspace: `softi-cp/usr/local/CyberCP/erpIntegration/`

---

## Roadmap

- [x] D1 health + websites (lectura)
- [x] externalRef persistido + PATCH
- [x] D2 `POST /api/softi/v1/provision` (en fork; ERP con `USE_SOFTI_API`)
- [ ] D3 webhooks → ERP
- [ ] DNS / correo proxy para área cliente
