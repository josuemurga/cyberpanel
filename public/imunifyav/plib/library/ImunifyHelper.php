<?php

namespace Imunify360;


class ImunifyHelper
{

    // Name of the Imunify360 plugin
    const IMUNIFY_360 = "360";
    // Name of the ImunifyAV plugin
    const IMUNIFY_AV = "AV";
    // Flag that define that extension was installed from the marketplace
    const MARKETPLACE_FLAG = "/var/imunify360/plesk-ext-marketplace";
    // Script that deploy the Imunify360
    const IMUNIFY_360_DEPLOY_SCRIPT = "i360deploy.sh";
    // Script that deploy the ImunifyAV
    const IMUNIFY_AV_DEPLOY_SCRIPT = "imav-deploy.sh";

    const REVISIUM_MODULE_ID = "revisium-antivirus";
    // JS Config file that store the app mode
    const APP_CONFIG_FILE = "/usr/local/psa/admin/htdocs/modules/imunify360/assets/js/config.js";

    // Temporary license key for period while the extension migration
    private static $temporaryLicenseKey = "IMAVPqFnwh8YAAeg4zrO";

    /**
     * Check if any domain in the current session has web hosing type
     *
     * @param $domains - domains from current user.
     * @return bool True if any domain has hosting, false otherwise.
     */
    public static function checkHosting($domains): bool {
        foreach ($domains as $domain) {
            if ($domain->hasHosting()) {
                return true;
            }
        }
        return false;
    }

    /**
     * Check hasPermission for current user
     * @param \pm_Client $client - current user
     * @param \pm_Domain[] $domains - array of domains from current user
     * @param string $name - permission name
     * @return bool True if at least one domain has this permission, false otherwise.
     */
    public static function checkPermission(string $name, \pm_Client $client, array $domains): bool {
        foreach ($domains as $domain) {
            if ($client->hasPermission($name, $domain)) {
                return true;
            }
        }
        return false;
    }

    /**
     * Check if the client plugin for Imunify is enabled.
     *
     * @return bool True if the client plugin is enabled, false otherwise.
     */
    public static function isClientPluginEnabled()
    {
        $serverFileManager = new \pm_ServerFileManager();
        return $serverFileManager->fileExists('/var/imunify360/av-userside-plugin.installed');
    }

    /**
     * Check if the imunify360-agent binary present.
     *
     * @return bool True if the binary present, false otherwise.
     */
    public static function isAgentInstalled()
    {
        $serverFileManager = new \pm_ServerFileManager();
        return $serverFileManager->fileExists('/usr/bin/imunify360-agent');
    }

    /**
     * Retrieve the Imunify license key.
     *
     * @return string|null The license key if available, null otherwise.
     */
    public static function getImunifyLicenseKey() {
        $license = \pm_License::getAdditionalKey();
        $licenseKey = $license ? $license->getProperties()['key-body'] : null;
        // Use the temporary license key if the revisium-antivirus has AV+ license
        if (!$licenseKey && \pm_License::hasAdditionalKey(self::REVISIUM_MODULE_ID)) {
            $licenseKey = self::$temporaryLicenseKey;
        }
        return $licenseKey;
    }

    /**
     * Determine the Imunify plugin to be installed based on the license key.
     *
     * @return string The plugin type, either IMUNIFY_AV or IMUNIFY_360.
     */
    public static function getImunifyPluginForInstall() {
        $licenseKey = self::getImunifyLicenseKey();
        if ($licenseKey) {
            return strpos($licenseKey, 'IMAV') === 0 ? self::IMUNIFY_AV : self::IMUNIFY_360;
        }
        return self::IMUNIFY_AV;
    }

    /**
     * Get the parameters required for Imunify installation.
     *
     * @return array The installation parameters.
     */
    public static function getImunifyInstallationParams() {
        return [
            "command" => "installation",
            "method" => ["start"],
            "params" => [
                "plugin_name" => self::getImunifyPluginForInstall(),
                "license_key" => self::getImunifyLicenseKey()
            ]
        ];
    }

    /**
     * Deploy the Imunify plugin by executing necessary shell scripts.
     *
     * This method deploys the core UI part and initializes the plugin installation in the background.
     * @param $force Force run the i360deploy.sh or imav-deploy.sh
     */
    public static function deploy($force = false) {
        // Detect if we have to run deploy scripts (i360deploy.sh or imav-deploy.sh)
        $skipDeploy = self::isAgentInstalled() && !$force;

        if (!empty($skipDeploy)) {
            ImunifyLog::info('Deploy only core UI without executing deploy scripts');
            \pm_ApiCli::callSbin('deploy.sh', ['-i', 'CORE']);
        } else {
            $pluginType = self::getImunifyPluginForInstall();
            ImunifyLog::info('Deploy ' . $pluginType . ' plugin');
            \pm_ApiCli::callSbin('deploy.sh', ['-i', $pluginType]);
            if (file_exists(self::MARKETPLACE_FLAG)) {
                ImunifyLog::info('Initialize and start the plugin installation in the background');
                \pm_ApiCli::callSbin('installation.sh', [base64_encode(json_encode(self::getImunifyInstallationParams()))]);
            }
        }
    }

    /**
     * Check if the deployment process is running.
     *
     * @return bool true if the deployment process is running, false otherwise.
     */
    public static function isDeployRunning() {
        $output = shell_exec("ps ax");
        $is_i360_running = strpos($output, self::IMUNIFY_360_DEPLOY_SCRIPT) !== false;
        $is_imav_running = strpos($output, self::IMUNIFY_AV_DEPLOY_SCRIPT) !== false;

        return $is_i360_running || $is_imav_running;
    }

    /**
     * This method is used to define the app mode.
     *
     * This method is calling the "define-app-mode.sh" script that set the app mode based on the license and installed
     * imunify package. Changes are applying to the /usr/local/psa/admin/htdocs/modules/imunify360/assets/js/config.js
     */
    public static function defineAppMode() {
        \pm_ApiCli::callSbin('define-app-mode.sh', []);
    }

    /**
     * Get the app mode from the config.js file.
     *
     * @return string|null The app mode, either IMUNIFY_AV or IMUNIFY_360, or null if the mode is not defined.
     */
    public static function getAppMode() {
        $configContents = file_get_contents(self::APP_CONFIG_FILE);

        if (preg_match("/IMUNIFY_PACKAGE\s*=\s*['\"]?\s*AV\s*['\"]?;/", $configContents)) {
            return self::IMUNIFY_AV;
        }
        if (preg_match("/IMUNIFY_PACKAGE\s*=\s*['\"]?\s*360\s*['\"]?;/", $configContents)) {
            return self::IMUNIFY_360;
        }
        return null;
    }

    public static function isImunify360Installed() {
        return self::getAppMode() === self::IMUNIFY_360 && self::isAgentInstalled();
    }

    /**
     * Method to wait until the installation process finishes.
     * We need this to prevent the termination of the child processes.
     */
    public static function waitForDeployProcessFinish()
    {
        $maxRetries = 900; // Maximum retries (e.g., 30 minutes)
        $retries = 0;

        while ($retries < $maxRetries) {
            if (!ImunifyHelper::isDeployRunning()) {
                break;
            }
            sleep(2); // Wait for 2 second before checking again
            $retries++;
        }
    }

    /**
     * Checks if the 'revisium-antivirus' extension is installed via Plesk API.
     *
     * @return bool True if installed, false otherwise.
     */
    public static function isInstalledRevisiumAV(): bool
    {
        $extensions = \pm_Extension::getExtensions();
        return isset($extensions[self::REVISIUM_MODULE_ID]);
    }

    /**
     * Disables the 'revisium-antivirus' extension if it is installed.
     * It will also log the actions.
     */
    public static function disableRevisiumAntivirus()
    {
        if (self::isInstalledRevisiumAV()) {
            ImunifyLog::info("ImunifyAV (revisium-antivirus) is installed. Attempting to disable it.");
            try {
                $revisium = \pm_Extension::getById(self::REVISIUM_MODULE_ID);
                if ($revisium->isActive()) {
                    $revisium->disable();
                    ImunifyLog::info("Extension revisium-antivirus was disabled.");
                }
            } catch (\Exception $e) {
                ImunifyLog::err("Exception while trying to disable revisium-antivirus: " . $e->getMessage());
            }
        }
    }
}
