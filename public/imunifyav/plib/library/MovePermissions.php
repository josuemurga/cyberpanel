<?php
/**
 * Class MovePermissions
 *
 * Static migration class to update service plans with new permissions
 * Migrates Revisium Antivirus permissions to Imunify360 permissions
 * by updating service plan permissions through the Plesk XML API.
 * Only migrates permissions that were explicitly set for the old extension.
 */

namespace Imunify360;

class MovePermissions {
    /** @var string Permission for Revisium Antivirus on/off */
    private static $RA_ON = "ext_permission_revisium_antivirus_ra_on";

    /** @var string Permission for Revisium Antivirus scanning */
    private static $RA_SCANNING_ALLOWED = "ext_permission_revisium_antivirus_ra_scanning_allowed";

    /** @var string Permission for Revisium Antivirus cleanup */
    private static $RA_CLEANUP_ALLOWED = "ext_permission_revisium_antivirus_ra_cleanup_allowed";

    /** @var array Mapping from old to new permissions */
    private static $PERMISSION_MAPPING;

    private static $log_filename = 'permissions-migration.log';
    private static $premission_migrated = 'imunify360-permissions-migrated';

    /**
     * Migration function from Revisium Antivirus to Imunify360 permissions.
     * Only sets a new permission if the corresponding old permission was explicitly defined.
     *
     * @return void
     */
    public static function migrate() {
        if (!ImunifyHelper::isInstalledRevisiumAV()) {
            self::logger(ImunifyLog::INFO, "Revisium Antivirus extension not detected - skipping permission migration.");
            return;
        }

        // check if migration already done and skip
        if (\pm_Settings::get(self::$premission_migrated, false)) {
            self::logger(ImunifyLog::INFO, "Permission migration already done - skipping.");
            return;
        }


        // Initialize Plesk SDK if not already initialized
        require_once("sdk.php");

        // Initialize permission mapping
        self::$PERMISSION_MAPPING = [
            self::$RA_ON => "ext_permission_imunify360_imunify_end_user_on",
            self::$RA_SCANNING_ALLOWED => "ext_permission_imunify360_imunify_scanning_allowed",
            self::$RA_CLEANUP_ALLOWED => "ext_permission_imunify360_imunify_cleanup_allowed",
        ];


        try {
            // 1. Get all service plans from Plesk
            self::logger(ImunifyLog::INFO, "Getting service plans...");
            $servicePlans = self::getServicePlansPermissions();
            self::logger(ImunifyLog::INFO, "Starting migration from Revisium Antivirus to Imunify360 permissions");

            if (empty($servicePlans)) {
                self::logger(ImunifyLog::INFO, "No service plans found. Skipping...");
                return;
            }

            self::logger(ImunifyLog::INFO, "Found " . count($servicePlans) . " service plans");

            $plansUpdated = 0;
            $permissionsMigratedCount = 0;

            // 2. Process each Service Plan
            foreach ($servicePlans as $plan) {
                $servicePlanId = isset($plan['id']) ? $plan['id'] : null;
                $servicePlanName = isset($plan['name']) ? $plan['name'] : 'Unknown'; // For logging

                if (!$servicePlanId) {
                    self::logger(ImunifyLog::WARN, "Skipping a plan due to missing ID.");
                    continue;
                }

                $explicitOldPermissions = isset($plan['permissions']) ? $plan['permissions'] : [];
                $permissionsToSet = []; // Array to hold only the permissions we need to explicitly set

                foreach (self::$PERMISSION_MAPPING as $oldPerm => $newPerm) {
                    if (array_key_exists($oldPerm, $explicitOldPermissions)) {
                        $value = $explicitOldPermissions[$oldPerm];
                        $permissionsToSet[$newPerm] = $value;
                        self::logger(ImunifyLog::DEBUG, "Plan {$servicePlanId} ('{$servicePlanName}'): Mapping old '{$oldPerm}' (".($value?'true':'false').") to new '{$newPerm}'.");
                        $permissionsMigratedCount++;
                    } else {
                        self::logger(ImunifyLog::DEBUG, "Plan {$servicePlanId} ('{$servicePlanName}'): Old permission '{$oldPerm}' was not explicitly set. Skipping mapping for '{$newPerm}'.");
                    }
                }

                if (!empty($permissionsToSet)) {
                    self::logger(ImunifyLog::INFO, "Updating service plan {$servicePlanId} ('{$servicePlanName}') with " . count($permissionsToSet) . " explicitly migrated permission(s)...");

                    try {
                        $result = self::updateServicePlanPermissions($servicePlanId, $permissionsToSet);

                        if (isset($result['status']) && $result['status'] === 'ok') {
                            self::logger(ImunifyLog::INFO, "Successfully updated service plan {$servicePlanId} ('{$servicePlanName}')");
                            $plansUpdated++;
                        } else {
                            $errorMessage = isset($result['errtext']) ? $result['errtext'] : (isset($result['error']) ? $result['error'] : 'Unknown API error');
                            self::logger(ImunifyLog::WARN, "Failed to update service plan {$servicePlanId} ('{$servicePlanName}'): {$errorMessage}");
                        }
                    } catch (\Exception $e) {
                        self::logger(ImunifyLog::ERR, "Error updating service plan {$servicePlanId} ('{$servicePlanName}'): " . $e->getMessage());
                    }
                } else {
                    self::logger(ImunifyLog::INFO, "No explicit Revisium permissions found for service plan {$servicePlanId} ('{$servicePlanName}'). No update needed.");
                }
            }

            \pm_Settings::set(self::$premission_migrated, true);
            self::logger(ImunifyLog::INFO, "Migration check completed. {$plansUpdated} plan(s) updated with a total of {$permissionsMigratedCount} explicit permission setting(s).");

        } catch (\Exception $e) {
            self::logger(ImunifyLog::ERR, "Error during migration: " . $e->getMessage());
        }
    }

    /**
     * Log messages using ImunifyLog directed to a specific file.
     *
     * @param int $level Log level (ImunifyLog::INFO, ImunifyLog::WARN, ImunifyLog::ERR, ImunifyLog::DEBUG)
     * @param string $message Message to log
     * @return void
     */
    private static function logger(int $level, string $message) {
        switch ($level) {
            case ImunifyLog::ERR:
                ImunifyLog::err($message, self::$log_filename);
                break;
            case ImunifyLog::INFO:
                ImunifyLog::info($message, self::$log_filename);
                break;
            case ImunifyLog::WARN:
                ImunifyLog::warn($message, self::$log_filename);
                break;
            default: // Catches DEBUG and any unexpected level
                ImunifyLog::debug($message, self::$log_filename);
        }
    }

    /**
     * Get all service plans with their permissions from Plesk
     *
     * @return array Service plans with their IDs and permissions
     */
    private static function getServicePlansPermissions(): array {
        try {
            $xmlString = '<packet><service-plan><get><filter/></get></service-plan></packet>';
            $xml = new \SimpleXMLElement($xmlString);
            $response = \pm_ApiRpc::getService()->call($xml);
            $plans = [];

            if (isset($response->{'service-plan'}->get->result)) {
                $results = $response->{'service-plan'}->get->result;
                foreach ($results as $result) {
                    if (isset($result->status) && (string)$result->status === 'ok') {
                        $plan = [
                            'id' => isset($result->id) ? (string)$result->id : null,
                            'name' => isset($result->name) ? (string)$result->name : 'Unknown',
                            'permissions' => []
                        ];

                        if (!$plan['id']) {
                            self::logger(ImunifyLog::WARN, "Found a service plan result with status 'ok' but no ID.");
                            continue; // Skip plans without ID
                        }

                        if (isset($result->permissions->permission)) {
                            foreach ($result->permissions->permission as $permission) {
                                if (isset($permission->name) && isset($permission->value)) {
                                    // Store only explicitly returned permissions
                                    $plan['permissions'][(string)$permission->name] = ((string)$permission->value === 'true');
                                }
                            }
                        }
                        $plans[] = $plan;
                    } elseif (isset($result->status) && (string)$result->status === 'error') {
                        $errText = isset($result->errtext) ? (string)$result->errtext : 'Unknown error';
                        $errCode = isset($result->errcode) ? (string)$result->errcode : 'N/A';
                        $planId = isset($result->id) ? (string)$result->id : 'N/A';
                        self::logger(ImunifyLog::WARN, "Error retrieving details for service plan ID {$planId}: [{$errCode}] {$errText}");
                    }
                }
            } else {
                self::logger(ImunifyLog::WARN, "Unexpected response structure or no results found when getting service plans.");
            }

            return $plans;
        } catch (\Exception $e) {
            self::logger(ImunifyLog::ERR, "Failed to get Plesk service plans: " . $e->getMessage());
            return [];
        }
    }

    /**
     * Update a service plan with new permissions
     *
     * @param string $servicePlanId ID of the service plan to update
     * @param array $permissionsDict Dictionary of permission names and boolean values
     * @return array Response status of the update operation
     */
    private static function updateServicePlanPermissions($servicePlanId, $permissionsDict) {
        try {
            $permissionsXml = '';
            foreach ($permissionsDict as $name => $value) {
                $boolValue = $value ? 'true' : 'false';
                $permissionsXml .= "<permission><name>{$name}</name><value>{$boolValue}</value></permission>";
            }

            $xmlString = '<packet><service-plan><set>'
                . '<filter><id>' . $servicePlanId . '</id></filter>'
                . '<permissions>' . $permissionsXml . '</permissions>'
                . '</set></service-plan></packet>';

            $xml = new \SimpleXMLElement($xmlString);
            $response = \pm_ApiRpc::getService()->call($xml);

            $result = [];

            if (isset($response->{'service-plan'}->{'set'}->{'result'})) {
                $resultNode = $response->{'service-plan'}->{'set'}->{'result'};
                $result['status'] = isset($resultNode->status) ? (string)$resultNode->status : 'error'; // Default to error if status missing

                if (isset($resultNode->id)) {
                    $result['id'] = (string)$resultNode->id;
                }

                if ($result['status'] === 'error') {
                    $result['errcode'] = isset($resultNode->errcode) ? (string)$resultNode->errcode : 'UNKNOWN';
                    $result['errtext'] = isset($resultNode->errtext) ? (string)$resultNode->errtext : 'Unknown error details';
                }
            } else {
                $result['status'] = 'error';
                $result['errtext'] = 'Unexpected API response format for service-plan set operation.';
                self::logger(ImunifyLog::WARN, "Unexpected API response for plan {$servicePlanId}: " . $response->asXML());
            }

            return $result;
        } catch (\Exception $e) {
            self::logger(ImunifyLog::ERR, "Exception during API call to update service plan {$servicePlanId}: " . $e->getMessage());
            return [
                'status' => 'error',
                'errtext' => 'Exception during API call: ' . $e->getMessage(),
                'error' => $e->getMessage(),
                'code' => $e->getCode()
            ];
        }
    }
}