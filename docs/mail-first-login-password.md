# Primer login webmail — cambio obligatorio de contraseña

> **Estado:** SOFTI fork (`softi-cp`) — CyberPanel + SnappyMail  
> **Alcance:** panel de correo y webmail. **Sin** API Softi Host / ERP (opcional después).

## Qué hace

Al crear una cuenta de correo en CyberPanel puedes marcar:

**“Require password change on first webmail login”**

Si está activo:

1. Se guarda `e_users.must_change_password = 1`.
2. El usuario entra a SnappyMail con la contraseña temporal.
3. Un plugin bloquea el buzón hasta que cambie la contraseña.
4. Tras el cambio → `must_change_password = 0` y hash bcrypt `{CRYPT}` en `e_users`.

Si el admin cambia la contraseña desde el panel (`submitPasswordChange`), el flag se limpia.

## Flujo

```
CyberPanel (crear email + checkbox)
    → mailUtilities.createEmailAccount(..., must_change_password=True)
    → MariaDB e_users

Usuario → SnappyMail login (IMAP OK)
    → plugin first-login-password
    → FirstLoginCheck → mustChange: true
    → modal obligatorio
    → FirstLoginChangePassword → UPDATE e_users
```

Dovecot **no** implementa “password expired” en SQL; la lógica vive en SnappyMail + columna custom.

## Archivos del fork

| Archivo | Cambio |
|---------|--------|
| `mailServer/models.py` | Campo `must_change_password` en `EUsers` |
| `mailServer/templates/mailServer/createEmailAccount.html` | Checkbox en formulario |
| `plogical/mailUtilities.py` | Crear cuenta, limpiar flag, instalar plugin |
| `install/snappymail-plugins/first-login-password/` | Plugin SnappyMail (PHP + JS) |
| `scripts/upgrade-mail-must-change-password.py` | `ALTER TABLE` idempotente |
| `scripts/patch-mail-first-login.py` | Parchea `mailserverManager.py`, `mailServer.js`, instala plugin |

En producción, `mailserverManager.py` y `mailServer.js` vienen de upstream CyberPanel; el script de parche los modifica in-place (no están versionados completos en el fork).

## Despliegue en servidor

```bash
# 1. Sincronizar fork a /usr/local/CyberCP (SFTP / deploy habitual)

# 2. Migración DB + parches + plugin
python3 /usr/local/CyberCP/scripts/patch-mail-first-login.py

# 3. Reiniciar panel
find /usr/local/CyberCP/mailServer/__pycache__ -name '*.pyc' -delete 2>/dev/null || true
systemctl restart lscpd
```

Solo reinstalar plugin SnappyMail:

```bash
python3 /usr/local/CyberCP/scripts/patch-mail-first-login.py --install-plugin-only
```

O manualmente:

```bash
/usr/local/CyberCP/bin/python /usr/local/CyberCP/plogical/mailUtilities.py InstallFirstLoginPasswordPlugin
```

## SnappyMail

- Plugin: `first-login-password`
- Runtime: `/usr/local/lscp/cyberpanel/rainloop/data/_data_/_default_/plugins/first-login-password/`
- Config: `plugin-first-login-password.json` (PDO → BD `cyberpanel`, tabla `e_users`)
- Se añade a `enabled_list` en `application.ini` sin quitar plugins existentes (`mailbox-detect`, etc.)

Admin SnappyMail: `https://panel:8090/snappymail/?admin` — verificar que el plugin aparece activo.

## Migración / rollback

**Aplicar columna:**

```sql
ALTER TABLE e_users ADD must_change_password TINYINT(1) NOT NULL DEFAULT 0;
```

**Rollback (solo si no usas la feature):**

```sql
ALTER TABLE e_users DROP COLUMN must_change_password;
```

Quitar plugin de `application.ini` y borrar carpeta `plugins/first-login-password`.

## Integración ERP (futuro, opcional)

Cuando exista `POST /api/softi/v1/mailboxes`, el body puede incluir `mustChangePassword: true` y delegar a `mailUtilities.createEmailAccount`. No es requisito para esta fase.

## Prueba manual

1. Crear `test@dominio.com` con checkbox activo.
2. `SELECT must_change_password FROM e_users WHERE email='test@dominio.com';` → `1`
3. Login SnappyMail → modal de cambio.
4. Cambiar contraseña → acceso al buzón.
5. `must_change_password` → `0`; login con nueva clave.

## Relacionado

- [mail-guard.md](mail-guard.md) — correo saliente / anti-spam
- [erp-integration.md](erp-integration.md) — API Softi (correos: roadmap)
