(rl => {
	'use strict';

	const PLUGIN_IDS = ['first-login-password', 'First Login Password'];

	const runWhenReady = fn => {
		if (rl) {
			fn(rl);
			return;
		}
		let tries = 0;
		const timer = setInterval(() => {
			if (window.rl) {
				clearInterval(timer);
				fn(window.rl);
			} else if (++tries > 120) {
				clearInterval(timer);
			}
		}, 100);
	};

	const truthyFlag = value =>
		value === true || value === 1 || value === '1';

	const mustChangeInPlugins = plugins => {
		if (!plugins || typeof plugins !== 'object') {
			return false;
		}
		return PLUGIN_IDS.some(id => truthyFlag(plugins[id]?.mustChange));
	};

	const getPluginSettings = rl => {
		for (const id of PLUGIN_IDS) {
			const length = rl.pluginSettingsGet(id, 'pass_min_length');
			const strength = rl.pluginSettingsGet(id, 'pass_min_strength');
			if (length != null || strength != null) {
				return {
					minLength: parseInt(length, 10) || 10,
					minStrength: parseInt(strength, 10) || 70
				};
			}
		}
		return { minLength: 10, minStrength: 70 };
	};

	const pwRe = [/[^0-9A-Za-z]+/g, /[0-9]+/g, /[A-Z]+/g, /[a-z]+/g];
	const getPassStrength = value => {
		let m, i = value.length, max = Math.min(100, i * 8), s = 0, c = 0, ii;
		while (i--) {
			s += (value[i] != value[i + 1] ? 1 : -0.5);
		}
		for (i = 0; i < 4; ++i) {
			m = value.match(pwRe[i]);
			if (m) {
				++c;
				for (ii = 0; ii < m.length; ++ii) {
					if (m[ii].length < 5) {
						++s;
					}
				}
			}
		}
		return Math.max(0, Math.min(max, s * c * 1.5));
	};

	runWhenReady(rl => {
		const policy = getPluginSettings(rl);
		let pendingGate = false;

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
						Mínimo ${policy.minLength} caracteres y ${policy.minStrength}% de fortaleza.
					</p>
					<label style="display:block;margin-bottom:.75rem;font-size:.85rem;">Contraseña actual</label>
					<input id="softi-flp-current" type="password" style="width:100%;margin-bottom:.75rem;padding:.5rem;border:1px solid #cbd5e1;border-radius:6px;">
					<label style="display:block;margin-bottom:.75rem;font-size:.85rem;">Nueva contraseña</label>
					<input id="softi-flp-new" type="password" style="width:100%;margin-bottom:.35rem;padding:.5rem;border:1px solid #cbd5e1;border-radius:6px;">
					<meter id="softi-flp-meter" min="0" max="100" low="${policy.minStrength}" high="90" optimum="100" value="0" style="width:100%;margin-bottom:.75rem;"></meter>
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
			const meter = overlay.querySelector('#softi-flp-meter');
			const newInput = overlay.querySelector('#softi-flp-new');
			newInput.addEventListener('input', () => {
				meter.value = getPassStrength(newInput.value);
			});

			overlay.querySelector('#softi-flp-submit').addEventListener('click', () => {
				err.style.display = 'none';
				const newPassword = newInput.value;
				const confirmPassword = overlay.querySelector('#softi-flp-confirm').value;

				if (newPassword.length < policy.minLength) {
					err.textContent = `La contraseña debe tener al menos ${policy.minLength} caracteres`;
					err.style.display = 'block';
					return;
				}
				if (getPassStrength(newPassword) < policy.minStrength) {
					err.textContent = `La contraseña es demasiado débil (mínimo ${policy.minStrength}%)`;
					err.style.display = 'block';
					return;
				}
				if (newPassword !== confirmPassword) {
					err.textContent = 'Las contraseñas nuevas no coinciden';
					err.style.display = 'block';
					return;
				}

				rl.pluginRemoteRequest(
					(iError, data) => {
						if (iError) {
							err.textContent = (data && (data.messageAdditional || data.ErrorMessageAdditional))
								? (data.messageAdditional || data.ErrorMessageAdditional)
								: 'Error al cambiar la contraseña';
							err.style.display = 'block';
							return;
						}
						pendingGate = false;
						overlay.remove();
						if (data?.Result?.Auth) {
							rl.setData(data.Result);
							return;
						}
						window.location.reload();
					},
					'FirstLoginChangePassword',
					{
						CurrentPassword: overlay.querySelector('#softi-flp-current').value,
						NewPassword: newPassword,
						ConfirmPassword: confirmPassword
					}
				);
			});
		};

		const mustChangeFromAppData = () =>
			mustChangeInPlugins(rl.settings?.get?.('Plugins'));

		const mustChangeFromLoginResult = result =>
			mustChangeInPlugins(result?.Plugins);

		const mustChangeFromResponse = data =>
			truthyFlag(data?.Result?.mustChange) || truthyFlag(data?.mustChange);

		const scheduleShowGate = () => {
			pendingGate = true;
			const tryShow = (attempt = 0) => {
				if (!pendingGate) {
					return;
				}
				if (mustChangeFromAppData()) {
					showGate();
					return;
				}
				if (attempt < 50) {
					setTimeout(() => tryShow(attempt + 1), 200);
				}
			};
			tryShow();
		};

		const runCheck = () => {
			if (!rl.settings?.get?.('Auth')) {
				return;
			}
			if (mustChangeFromAppData()) {
				showGate();
				return;
			}
			rl.pluginRemoteRequest((iError, data) => {
				if (!iError && mustChangeFromResponse(data)) {
					showGate();
				}
			}, 'FirstLoginCheck', {});
		};

		// SnappyMail usa window.dispatchEvent, no document.
		window.addEventListener('sm-user-login-response', event => {
			const detail = event.detail;
			if (!detail || detail.error) {
				return;
			}
			if (mustChangeFromLoginResult(detail.data?.Result)) {
				scheduleShowGate();
			}
		});

		window.addEventListener('sm-show-screen', () => {
			if (pendingGate && mustChangeFromAppData()) {
				showGate();
			}
		});

		if (!rl.__softiFlpSetDataPatched) {
			rl.__softiFlpSetDataPatched = true;
			const origSetData = rl.setData.bind(rl);
			rl.setData = appData => {
				origSetData(appData);
				if (appData?.Auth && mustChangeInPlugins(appData.Plugins)) {
					scheduleShowGate();
				}
			};
		}

		setTimeout(runCheck, 800);
	});
})(window.rl);
