# Primer login webmail — cambio obligatorio de contraseña

> **Estado:** SOFTI fork (`softi-cp` / rama `mis-mejoras`) — CyberPanel + SnappyMail  
> **Plugin:** `first-login-password` v1.1.1 (2026-08-31)  
> **Alcance:** panel de correo y webmail. Sin API Softi Host / ERP (opcional después).

## Qué hace

Permite exigir que el usuario cambie su contraseña en el **primer acceso a SnappyMail** (webmail), con control desde CyberPanel:

| Acción en CyberPanel | Efecto |
|----------------------|--------|
| Crear cuenta con checkbox **Require password change on first webmail login** | `e_users.must_change_password = 1` |
| Cambiar contraseña en **List Emails** con checkbox **Require password change…** | Marca o limpia el flag según el checkbox |
| Badge **Password change pending** en listado | Indica cuentas con flag activo |
| Usuario cambia contraseña en SnappyMail | `must_change_password = 0`, hash bcrypt `{CRYPT}` |

Dovecot **no** implementa “password expired” en SQL; la lógica vive en SnappyMail + columna custom en `e_users`.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│ CyberPanel (Django)                                             │
│  createEmailAccount.html / listEmails.html  →  mailServer.js      │
│  mailserverManager.submitEmailCreation / submitPasswordChange   │
│  mailUtilities.createEmailAccount(..., must_change_password)    │
└────────────────────────────┬────────────────────────────────────┘
                             │ MariaDB cyberpanel.e_users
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ SnappyMail plugin first-login-password                          │
│  FilterAppDataPluginSection → Plugins['first-login-password']   │
│  FirstLoginCheck / FirstLoginChangePassword (JSON hooks)        │
│  FirstLoginGate.js → overlay modal bloqueante                   │
└─────────────────────────────────────────────────────────────────┘
```

### Flujo crear cuenta

1. Admin marca checkbox al crear email.
2. `submitEmailCreation` lee `mustChangePassword` del POST.
3. `mailUtilities.createEmailAccount(..., must_change_password=True)` persiste en `e_users`.
4. Usuario entra a SnappyMail con contraseña temporal → plugin muestra modal.
5. Tras cambio exitoso: UPDATE password + `must_change_password = 0`, sesión SnappyMail actualizada (sin logout IMAP).

### Flujo cambiar contraseña (List Emails)

1. Admin abre modal **Change Password** (único `#changePasswordModal`, **fuera** del `ng-repeat`).
2. Checkbox `mustChangePasswordOnReset` en scope padre.
3. `submitPasswordChange`: si checkbox marcado → `must_change_password = 1`; si no → `0`.
4. Listado refresca badge vía `populateCurrentRecords()` tras guardar.

---

## Archivos del fork

| Archivo | Rol |
|---------|-----|
| `mailServer/models.py` | Campo `must_change_password` en `EUsers` (**mantener modelos upstream completos**) |
| `mailServer/mailserverManager.py` | `submitEmailCreation`, `submitPasswordChange`, `fetchEmails` (parcheado in-place) |
| `mailServer/static/mailServer/mailServer.js` | POST `mustChangePassword`, modal change password (parcheado in-place) |
| `mailServer/static/mailServer/mailServer.softi-patch.md` | Referencia de qué parchea el script |
| `mailServer/templates/mailServer/createEmailAccount.html` | Checkbox al crear |
| `mailServer/templates/mailServer/listEmails.html` | Badge Status, modal único, checkbox al resetear |
| `plogical/mailUtilities.py` | `_set/_clear_must_change_password`, `InstallFirstLoginPasswordPlugin` |
| `install/snappymail-plugins/first-login-password/` | Plugin SnappyMail (PHP + JS) |
| `scripts/upgrade-mail-must-change-password.py` | `ALTER TABLE` idempotente |
| `scripts/patch-mail-first-login.py` | Migración + parches manager/JS + instala plugin |
| `scripts/sync-static.sh` | Copia `static/` → `public/static/` (tras editar JS) |
| `docs/mail-first-login-password.md` | Este documento |

**Espejo local (sin git):** `softi-cp/usr/local/CyberCP/`  
**Repo git (prod):** `/usr/local/CyberCP` en VPS, rama `mis-mejoras` → `github.com/josuemurga/cyberpanel`

---

## Despliegue en servidor

```bash
# 1. Sincronizar fork → /usr/local/CyberCP (rsync/SFTP habitual)

# 2. Migración DB + parches manager/JS + plugin
python3 /usr/local/CyberCP/scripts/patch-mail-first-login.py

# 3. Si se editó mailServer.js en static/, publicar copia servida
/usr/local/CyberCP/scripts/sync-static.sh

# 4. Limpiar caché SnappyMail (obligatorio tras cambiar JS del plugin)
rm -rf /usr/local/lscp/cyberpanel/rainloop/data/_data_/_default_/cache/*

# 5. Reiniciar panel
find /usr/local/CyberCP/mailServer/__pycache__ -name '*.pyc' -delete 2>/dev/null || true
systemctl restart lscpd
```

Solo reinstalar plugin:

```bash
python3 /usr/local/CyberCP/scripts/patch-mail-first-login.py --install-plugin-only
# o
/usr/local/CyberCP/bin/python /usr/local/CyberCP/plogical/mailUtilities.py InstallFirstLoginPasswordPlugin
```

**Python:** usar `/usr/local/CyberCP/bin/python` para migraciones (tiene `MySQLdb`).

---

## SnappyMail

| Concepto | Valor |
|----------|-------|
| Carpeta plugin | `first-login-password` |
| Clave en `AppData.Plugins` | **`first-login-password`** (nombre de carpeta), no `First Login Password` |
| Fuente instalación | `install/snappymail-plugins/first-login-password/` |
| Runtime | `/usr/local/lscp/cyberpanel/rainloop/data/_data_/_default_/plugins/first-login-password/` |
| Config PDO | `plugin-first-login-password.json` → BD `cyberpanel`, tabla `e_users` |
| Admin | `https://panel:8090/snappymail/?admin` — verificar plugin activo en `enabled_list` |

### Hooks JSON del plugin

| Hook | Uso |
|------|-----|
| `FirstLoginCheck` | Confirma `mustChange` tras login |
| `FirstLoginChangePassword` | Valida, UPDATE BD, `SetPassword` + `SetAuthToken` + `resealCryptKey`, devuelve `AppData(false)` |

### Política de contraseña (igual que plugin `change-password`)

- Mínimo 10 caracteres (`pass_min_length`)
- Mínimo 70% fortaleza (`pass_min_strength`)
- Hash: `{CRYPT}` + `password_hash(..., PASSWORD_BCRYPT)`

### Caché del plugin JS

SnappyMail empaqueta assets de plugins; la URL del JS solo cambia si subes **`VERSION`** en `index.php`. Tras cada cambio en `FirstLoginGate.js`:

1. Bump `VERSION` en `index.php`
2. Reinstalar plugin (`patch-mail-first-login.py --install-plugin-only`)
3. Borrar `.../cache/*` en rainloop data

---

## Lecciones aprendidas (pitfalls)

Registro de bugs reales durante el desarrollo — consultar antes de tocar esta feature.

| Síntoma | Causa raíz | Fix |
|---------|------------|-----|
| HTTP 500 en `/email/createEmailAccount` | `models.py` recortado (solo `EUsers`) → imports rotos, `ACLManager` undefined | Restaurar **todos** los modelos upstream + añadir `must_change_password` |
| Modal SnappyMail nunca aparece | JS buscaba plugin `'First Login Password'`; AppData usa clave de carpeta `'first-login-password'` | `PLUGIN_IDS` con ambos nombres; leer `Result.Plugins` en login |
| JS viejo en navegador tras deploy | Caché SnappyMail + hash URL ligado a `VERSION` | Bump versión plugin + `rm -rf .../cache/*` |
| “Contraseñas no coinciden” con datos correctos | `ChangePassword()` leía args PHP en vez del body JSON | Usar `$this->jsonParam('NewPassword')` etc. |
| Logout / error IMAP tras cambiar contraseña | Solo UPDATE en BD; sesión SnappyMail seguía con password vieja | `SetPassword`, `SetAuthToken`, `resealCryptKey`, `AppData(false)`; JS `rl.setData(data.Result)` |
| Checkbox CyberPanel no guardaba flag | Modal `#changePasswordModal` **dentro** de `ng-repeat` → scope hijo aislado | Modal **único fuera** del repeat; `mustChangePasswordOnReset` en scope padre |
| Listado no muestra badge tras save | No refrescaba datos | `populateCurrentRecords()` en success de `changePassword` |
| Modal no abre justo tras login (sí con F5) | `sm-user-login-response` en `window`, listener en `document`; `setData()` re-renderiza tarde | `window.addEventListener`, patch `rl.setData`, `scheduleShowGate()`, listener `sm-show-screen` |

### Detalle Angular (CyberPanel)

```html
<!-- ❌ MAL: un modal por fila, ng-model en scope hijo -->
<tr ng-repeat="record in records">
  <div id="changePasswordModal">...</div>
</tr>

<!-- ✅ BIEN: un solo modal al final del template, fuera del ng-repeat -->
<div id="changePasswordModal" ng-show="changePasswordBox">...</div>
```

### Detalle SnappyMail (PHP)

```php
// ❌ MAL — argumentos de función no llegan del POST JSON
public function ChangePassword($NewPassword) { ... }

// ✅ BIEN
$NewPassword = (string) $this->jsonParam('NewPassword', '');
return $this->jsonResponse(__FUNCTION__, $oActions->AppData(false));
```

### Detalle SnappyMail (JS)

```javascript
// ❌ MAL
document.addEventListener('sm-user-login-response', ...);

// ✅ BIEN — SnappyMail dispara en window
window.addEventListener('sm-user-login-response', ...);
```

---

## Migración / rollback

**Aplicar columna (idempotente):**

```bash
/usr/local/CyberCP/bin/python /usr/local/CyberCP/scripts/upgrade-mail-must-change-password.py
```

```sql
ALTER TABLE e_users ADD must_change_password TINYINT(1) NOT NULL DEFAULT 0;
```

**Rollback (solo si no usas la feature):**

```sql
ALTER TABLE e_users DROP COLUMN must_change_password;
```

Quitar `first-login-password` de `enabled_list` en `application.ini` y borrar carpeta en `plugins/`.

---

## Verificación manual

1. Crear `test@dominio.com` con checkbox activo.
2. `SELECT must_change_password FROM e_users WHERE email='test@dominio.com';` → `1`
3. Login SnappyMail → modal bloqueante (sin F5).
4. Cambiar contraseña → acceso al buzón, **sin** logout.
5. `must_change_password` → `0`; login con nueva clave.
6. En List Emails: badge **Password change pending** al marcar flag; desaparece al limpiar.
7. Cambiar contraseña desde panel con checkbox → flag coherente en BD y badge.

Cuenta de prueba histórica: `testpassword@softi.host`.

---

## Integración ERP (futuro, opcional)

Cuando exista `POST /api/softi/v1/mailboxes`, el body puede incluir `mustChangePassword: true` y delegar a `mailUtilities.createEmailAccount`. No es requisito para esta fase.

---

## Relacionado

- [mail-guard.md](mail-guard.md) — correo saliente / anti-spam
- [erp-integration.md](erp-integration.md) — API Softi (correos: roadmap)
