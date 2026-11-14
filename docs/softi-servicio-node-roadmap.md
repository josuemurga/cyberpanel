# Softi — Roadmap: Node por Linux user + Servicio que agrupa sitios

> **Repo:** fork CyberPanel `mis-mejoras` (`/usr/local/CyberCP`)  
> **Relacionado:** [softi-package-limits.md](./softi-package-limits.md), Nest [cyberpanel-softi-api.md](https://github.com/josuemurga/nestjs-erp/blob/main/docs/arquitectura/integraciones/cyberpanel-softi-api.md), [hosting.md](https://github.com/josuemurga/nestjs-erp/blob/main/docs/arquitectura/verticales/hosting.md)

## Modelo (tres capas)

| Rol | Qué es | Ejemplo |
|-----|--------|---------|
| **Cliente comercial** | Comprador Softihost (Nest) | Cliente + `ServicioRecurso` |
| **Owner CyberPanel** | Login panel / reseller | `cmoralest` |
| **Linux user (`externalApp`)** | Permisos por website (profesional: 1 sitio → 1 user) | `renta5620` |

El **plan comprado** vive en el **Servicio**. Cada website sigue con su propio Linux user aunque pertenezca al mismo plan (como cPanel/Plesk). Child domains comparten user del master; apps distintas (`api.`, `gestion.`) pueden ser websites separados.

## Hecho (baseline)

- [x] Package Softi → systemd `user-{uid}.slice` (`softiPackageEnforce.py`)
- [x] Plan usage UI `/packages/planUsage` (disco + RAM/CPU approx ps/cwd/PM2/Docker)
- [x] Softi Node chown al owner del cwd (archivos)
- [x] **Fase 1:** Softi Node runtime con `uid`/`gid` = owner de `/home/<domain>` (`externalApp`); PM2 daemon sigue siendo root/central

## Orden de entrega

### Fase 1 — Softi Node como `externalApp` (enforcement real) ✅

1. [x] `pm2_agent` escribe ecosystem con `uid`/`gid` numéricos + `exec_mode: fork`.
2. [x] Interpreter absoluto en `/usr/local/softi-node/v*/bin/node` (publicado desde nvm; usable por el user del sitio).
3. [x] Logs en `{cwd}/.softi-logs/`; `HOME`/`PATH` del sitio en `env`.
4. [x] `cmd: migrate_site_uid` — rewrite + `pm2 delete` + `pm2 start` ecosystem (sin linger).
5. [x] Doc operativa aquí + `softi-package-limits.md`.

**Migrar una app Softi existente (VPS, como root):**

```bash
python3 - <<'PY'
import json,socket
def call(p):
    s=socket.socket(socket.AF_UNIX); s.connect('/run/pm2-agent.sock')
    s.sendall(json.dumps(p).encode()+b'\n'); print(s.recv(65536).decode())
call({"cmd":"migrate_site_uid","pm2_name":"dominio.tld__app"})
PY
# Verificar: pm2 list (columna user) y ps -o user= -p <pid>
```

**No:** un PM2 daemon por cada usuario (más RAM). Un PM2 central + procesos con uid del sitio.

### Fase 2 — Servicio agrupa N websites (medición / producto) ✅ MVP

1. [x] Nest: `ServicioRecurso` 1:N `ServicioSitio`; Softi `externalRef` = `ServicioRecurso.id` (provision hijos + sync).
2. [x] Plan usage: `groupBy=servicio` + UI «Por servicio Softihost»; suma uso; cuota ≈ max package (sin hard-cap multi-UID).
3. [ ] Flutter Hosting: misma agrupación + cuotas Nest (`espacioGB`/`ramGB`); Softi API métricas (D4).
4. Enforcement MVP: **alerta por suma**; hard-cap multi-UID después.

### Fase 3 — Datos + child domains

1. Backfill (ej. Cordillera → un servicio con `rentacar` + `api` + `gestion`).
2. Corregir creación de **child domains** Softi (PHP/mismo sitio); websites nuevos solo si es otro stack.
3. Altas Softihost: crear servicio + amarrar websites.

## Dónde documentar en Nest

| Doc | Uso |
|-----|-----|
| `docs/ROADMAP.md` | Estado global hosting D4/D5 |
| `docs/arquitectura/verticales/hosting.md` | Checklist Fase D |
| `docs/arquitectura/integraciones/cyberpanel-softi-api.md` | D4 métricas / D5 servicio+Node uid |
| `docs/fases/fase-53-softi-servicio-plan-usage.md` | Entrega checklist |

## Criterios de hecho

- Node Softi de Cordillera/API aparece como user Linux del sitio (no root).
- Plan usage (o admin Hosting) muestra **un servicio** con suma de sitios.
- Docs Softi CP + Nest alineados; commit en `mis-mejoras` + docs Nest en `main`/rama de trabajo.
