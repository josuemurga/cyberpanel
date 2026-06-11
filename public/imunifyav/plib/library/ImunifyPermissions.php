<?php

namespace Imunify360;

class ImunifyPermissions
{
    const PERMISSION_END_USER_IMUNIFY_ON = 'imunify_end_user_on';
    const PERMISSION_IMUNIFY_SCAN_ALLOWED = 'imunify_scanning_allowed';
    const PERMISSION_IMUNIFY_CLEANUP_ALLOWED = 'imunify_cleanup_allowed';

    public static function isAvailableForEndUser(\pm_Client $client, array $domains): bool {
        return ImunifyHelper::checkPermission(self::PERMISSION_END_USER_IMUNIFY_ON, $client, $domains);
    }

    public static function scanningAllowed(\pm_Client $client, array $domains): bool {
        return ImunifyHelper::checkPermission(self::PERMISSION_IMUNIFY_SCAN_ALLOWED, $client, $domains);
    }

    public static function cleanupAllowed(\pm_Client $client, array $domains): bool {
        return ImunifyHelper::checkPermission(self::PERMISSION_IMUNIFY_CLEANUP_ALLOWED, $client, $domains);
    }
}
