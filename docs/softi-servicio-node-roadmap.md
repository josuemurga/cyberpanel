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
- [x] Softi Node chown al owner del cwd (archivos); **procesos aún como root vía PM2**

## Orden de entrega

### Fase 1 — Softi Node como `externalApp` (enforcement real)

1. Start Softi/PM2 con `uid`/`gid` del sitio (o `runuser -u`), no solo chown.
2. Ecosystem: bin Node absoluto, logs/cwd del user, `PORT` Softi.
3. Migrar apps existentes; verificar HTTPS + Plan usage por UID.
4. Sin linger por defecto; arranque vía panel/agente.
5. Doc operativa en este archivo + `softi-package-limits.md`.

**No:** un PM2 daemon por cada usuario (más RAM). Un PM2 central + procesos con uid del sitio.

### Fase 2 — Servicio agrupa N websites (medición / producto)

1. Nest: `ServicioRecurso` = plan Softi + lista de dominios (`externalRef` / sync CP).
2. Softi API / Plan usage: filtro y **suma** por servicio vs cuota del plan.
3. Flutter Hosting: misma agrupación.
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
