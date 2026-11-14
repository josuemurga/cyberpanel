# Softi Package limits (shared hosting)

Configurable in CyberPanel **Packages** (`memoryLimitMB`, `cpuCores`, `procHardLimit`, `diskSpace`, `enforceDiskLimits=1`).

Enforcement (`plogical/softiPackageEnforce.py`):

- systemd `user-{uid}.slice` → `MemoryMax` / `CPUQuota` / `TasksMax` (covers SSH Node/Playwright)
- OLS vhost mem/proc on site create; `lscgctl` best-effort
- Softi: no CyberPanel addons paywall
- Polkit: deny `set-self-linger`

CPU: each `cpuCores` unit = **25%** of one vCPU (cap 100%).

Packages: `admin_SoftiEsencial|Profesional|Comercial|Corporativo`.

## Plan usage UI

Admin Softi CP → **Plan usage** (`/packages/planUsage`):

- Lista websites con package asignado, disco usado/cuota, RAM/CPU **live ≈ `ps`** vs tope Package (`MemoryMax` / `CPUQuota%`), `externalApp`, estado.
- Live: `ps` + `/proc` cwd + **PM2 monit** + **Docker** (compose `working_dir`). Tras Fase 1 Softi Node, los procesos Node Softi corren como `externalApp` → entran en `user-{uid}.slice` (MemoryMax/CPUQuota). PHP sin `lsphp` = idle/0; OLS `nobody` no se reparte.
- Filtros: package, owner, Active/Suspended, agrupación website|servicio, búsqueda dominio/user/email/ref.
- API: `GET|POST /packages/fetchPlanUsage` (`groupBy=website|servicio`, `externalRefFilter`).
- `groupBy=servicio`: suma disk/RAM/CPU de websites con el mismo Softihost `externalRef` (`ServicioRecurso.id`); cuota ≈ max del package Softi. Sin hard-cap multi-UID.

## Softi Node runtime (Fase 1)

- PM2 **central** (root / `pm2-agent`); **no** un daemon PM2 por website.
- Ecosystem Softi: `uid`/`gid` del owner de `/home/<domain>`, interpreter `/usr/local/softi-node/v*/bin/node`, `exec_mode: fork`.
- Migración apps root→site user: socket `migrate_site_uid` (ver [softi-servicio-node-roadmap.md](./softi-servicio-node-roadmap.md)).
- Sin `loginctl enable-linger` por defecto.

Roadmap (Servicio agrupa sitios): [softi-servicio-node-roadmap.md](./softi-servicio-node-roadmap.md).
