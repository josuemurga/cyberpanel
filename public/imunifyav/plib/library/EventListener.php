<?php

use \Imunify360\ImunifyHelper;
use \Imunify360\ImunifyLog;

class Modules_Imunify360_EventListener implements EventListener
{
    /**
     * Method to filter events for handling (license update in our case only needed to be processed)
     *
     * See: https://docs.plesk.com/en-US/obsidian/extensions-guide/plesk-features-available-for-extensions/subscribe-to-plesk-events.71093/#handling-selected-events-only
     */
    public function filterActions()
    {
        return ['license_update'];
    }

    /**
     * Method for handling the following events for "license_update":
     * - install additional license {"License":"xxx","License type":"additional","License name":"ext-imunify360"}
     * - upgrade plesk license {"License":"xxx","License type":"plesk","License name":"Plesk license"}
     *
     * See: https://docs.plesk.com/en-US/obsidian/extensions-guide/plesk-features-available-for-extensions/subscribe-to-plesk-events.71093/#how-to-create-a-handler
     */
    public function handleEvent($objectType, $objectId, $action, $oldValues, $newValues)
    {
        ImunifyLog::info('Imunify360: handleEvent: ' . json_encode($newValues));
        // We don't need to upgrade, if we already have Imunify360
        if (ImunifyHelper::isImunify360Installed()) {
            return;
        }

        if ($this->isRelevantLicense($newValues) && ImunifyHelper::getAppMode() != ImunifyHelper::getImunifyPluginForInstall()) {
            ImunifyHelper::deploy(true);
        }
    }

    /**
     * Check if the license is relevant for deployment
     *
     * @param array $newValues: {"License":"","License type":"","License name":""}
     * @return bool
     */
    private function isRelevantLicense($newValues)
    {
        $licenseName = $newValues['License name'] ?? null;
        $licenseType = $newValues['License type'] ?? null;

        return ($licenseName === 'ext-imunify360' && $licenseType === 'additional') ||
               ($licenseName === 'Plesk license' && $licenseType === 'plesk');
    }
}

return new Modules_Imunify360_EventListener();
