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
- Live: `ps` + `/proc` cwd + **PM2 monit** + **Docker** (compose `working_dir`). No cgroup (`user-{uid}.slice` inactivo mientras Node corre como root). PHP sin `lsphp` = idle/0; OLS `nobody` no se reparte.
- Filtros: package, owner, Active/Suspended, búsqueda dominio/user/email.
- API: `GET|POST /packages/fetchPlanUsage`.

Roadmap siguiente (Node como Linux user + Servicio que agrupa sitios): [softi-servicio-node-roadmap.md](./softi-servicio-node-roadmap.md).
