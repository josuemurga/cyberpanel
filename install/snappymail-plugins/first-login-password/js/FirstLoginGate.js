(rl => {
	'use strict';

	if (!rl) {
		return;
	}

	const showGate = () => {
		if (document.getElementById('softi-first-login-gate')) {
			document.getElementById('softi-first-login-gate').style.display = 'flex';
			return;
		}

		const overlay = document.createElement('div');
		overlay.id = 'softi-first-login-gate';
		overlay.style.cssText =
			'position:fixed;inset:0;z-index:99999;background:rgba(15,23,42,.72);' +
			'display:flex;align-items:center;justify-content:center;padding:1rem;';

		overlay.innerHTML = `
			<div style="background:#fff;border-radius:12px;max-width:420px;width:100%;padding:1.5rem;box-shadow:0 20px 50px rgba(0,0,0,.25);">
				<h2 style="margin:0 0 .5rem;font-size:1.25rem;">Cambio de contraseña obligatorio</h2>
				<p style="margin:0 0 1rem;color:#475569;font-size:.9rem;">
					Debes establecer una nueva contraseña antes de usar el correo.
				</p>
				<label style="display:block;margin-bottom:.75rem;font-size:.85rem;">Contraseña actual</label>
				<input id="softi-flp-current" type="password" style="width:100%;margin-bottom:.75rem;padding:.5rem;border:1px solid #cbd5e1;border-radius:6px;">
				<label style="display:block;margin-bottom:.75rem;font-size:.85rem;">Nueva contraseña</label>
				<input id="softi-flp-new" type="password" style="width:100%;margin-bottom:.75rem;padding:.5rem;border:1px solid #cbd5e1;border-radius:6px;">
				<label style="display:block;margin-bottom:.75rem;font-size:.85rem;">Confirmar nueva contraseña</label>
				<input id="softi-flp-confirm" type="password" style="width:100%;margin-bottom:1rem;padding:.5rem;border:1px solid #cbd5e1;border-radius:6px;">
				<p id="softi-flp-error" style="color:#dc2626;font-size:.85rem;display:none;margin:0 0 .75rem;"></p>
				<button id="softi-flp-submit" type="button" style="width:100%;padding:.65rem;border:0;border-radius:6px;background:#3366ff;color:#fff;font-weight:600;cursor:pointer;">
					Guardar y continuar
				</button>
			</div>
		`;

		document.body.appendChild(overlay);

		const err = overlay.querySelector('#softi-flp-error');
		overlay.querySelector('#softi-flp-submit').addEventListener('click', () => {
			err.style.display = 'none';
			rl.pluginRemoteRequest(
				(iError, data) => {
					if (iError) {
						err.textContent = (data && data.ErrorMessageAdditional)
							? data.ErrorMessageAdditional
							: 'Error al cambiar la contraseña';
						err.style.display = 'block';
						return;
					}
					overlay.remove();
					window.location.reload();
				},
				'FirstLoginChangePassword',
				{
					CurrentPassword: overlay.querySelector('#softi-flp-current').value,
					NewPassword: overlay.querySelector('#softi-flp-new').value,
					ConfirmPassword: overlay.querySelector('#softi-flp-confirm').value
				}
			);
		});
	};

	const check = () => {
		rl.pluginRemoteRequest(
			(iError, data) => {
				if (!iError && data && data.mustChange) {
					showGate();
				}
			},
			'FirstLoginCheck',
			{}
		);
	};

	setTimeout(check, 800);
})(window.rl);
