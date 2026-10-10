<?php

/**
 * SOFTI-MEJORA — Tema / título SoftiMail según HTTP_HOST (webmail white-label).
 *
 * Default: SoftiMail@custom
 * webmail.moralestechs.com → MoralesTech@custom
 * webmail.astromike.design → Astromike@custom
 */
class SoftiHostThemePlugin extends \RainLoop\Plugins\AbstractPlugin
{
	const
		NAME        = 'Softi Host Theme',
		VERSION     = '1.0.0',
		RELEASE     = '2026-09-17',
		REQUIRED    = '2.36.0',
		CATEGORY    = 'General',
		DESCRIPTION = 'Select SoftiMail brand theme from HTTP_HOST (Softi / Morales Tech / Astromike)';

	/** @var array<string, array{theme:string,title:string,loading:string}> */
	private static $defaultMap = array(
		'webmail.moralestechs.com' => array(
			'theme'   => 'MoralesTech@custom',
			'title'   => 'Morales Tech Webmail',
			'loading' => 'Morales Tech',
		),
		'webmail.astromike.design' => array(
			'theme'   => 'Astromike@custom',
			'title'   => 'Astromike Webmail',
			'loading' => 'Astromike',
		),
	);

	public function Init() : void
	{
		$this->addHook('filter.application-config', 'FilterApplicationConfig');
		$this->addHook('filter.app-data', 'FilterAppData');
	}

	public function Supported() : string
	{
		return 'Per-host SoftiMail / distributor themes via HTTP_HOST';
	}

	protected function configMapping() : array
	{
		return array(
			\RainLoop\Plugins\Property::NewInstance('host_map_json')
				->SetLabel('Host map JSON (optional override)')
				->SetType(\RainLoop\Enumerations\PluginPropertyType::STRING_TEXT)
				->SetDescription('{"webmail.example.com":{"theme":"SoftiMail@custom","title":"Example","loading":"Example"}}')
				->SetDefaultValue(''),
		);
	}

	private function requestHost() : string
	{
		$host = (string) ($_SERVER['HTTP_X_FORWARDED_HOST'] ?? '');
		if ($host === '') {
			$host = (string) ($_SERVER['HTTP_HOST'] ?? '');
		}
		// X-Forwarded-Host may be a list
		if (\strpos($host, ',') !== false) {
			$host = \trim(\explode(',', $host)[0]);
		}
		$host = \strtolower(\trim($host));
		if ($host !== '' && \strpos($host, ':') !== false) {
			$host = \preg_replace('/:\d+$/', '', $host) ?: $host;
		}
		return $host;
	}

	/** @return array{theme:string,title:string,loading:string}|null */
	private function brandForHost(string $host) : ?array
	{
		if ($host === '') {
			return null;
		}
		$map = self::$defaultMap;
		$json = \trim((string) $this->Config()->Get('plugin', 'host_map_json', ''));
		if ($json !== '') {
			$decoded = \json_decode($json, true);
			if (\is_array($decoded)) {
				foreach ($decoded as $k => $v) {
					if (!\is_array($v)) {
						continue;
					}
					$map[\strtolower((string) $k)] = array(
						'theme'   => (string) ($v['theme'] ?? 'SoftiMail@custom'),
						'title'   => (string) ($v['title'] ?? 'SoftiMail'),
						'loading' => (string) ($v['loading'] ?? ($v['title'] ?? 'SoftiMail')),
					);
				}
			}
		}
		return $map[$host] ?? null;
	}

	public function FilterApplicationConfig(\RainLoop\Config\Application $oConfig) : void
	{
		$brand = $this->brandForHost($this->requestHost());
		if (!$brand) {
			return;
		}
		$oConfig->Set('webmail', 'theme', $brand['theme']);
		$oConfig->Set('webmail', 'title', $brand['title']);
		$oConfig->Set('webmail', 'loading_description', $brand['loading']);
	}

	public function FilterAppData(bool $bAdmin, array &$aAppData) : void
	{
		$brand = $this->brandForHost($this->requestHost());
		if (!$brand) {
			return;
		}
		$aAppData['Theme'] = $brand['theme'];
		$aAppData['title'] = $brand['title'];
		$aAppData['loadingDescription'] = $brand['loading'];
	}
}
