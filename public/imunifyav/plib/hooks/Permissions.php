<?php

use \Imunify360\ImunifyLocale;
use \Imunify360\ImunifyPermissions;

class Modules_Imunify360_Permissions extends pm_Hook_Permissions
{
    public function getPermissions()
    {
        return [
            ImunifyPermissions::PERMISSION_END_USER_IMUNIFY_ON => [
                'default'     => true,
                'place'       => self::PLACE_MAIN,
                'name'        => ImunifyLocale::lmsg('permissions.imunify_end_user_on.name'),
                'description' => ImunifyLocale::lmsg('permissions.imunify_end_user_on.description'),
            ],
            ImunifyPermissions::PERMISSION_IMUNIFY_SCAN_ALLOWED => [
                'default'     => true,
                'place'       => self::PLACE_MAIN,
                'name'        => ImunifyLocale::lmsg('permissions.scanning_allowed.name'),
                'description' => ImunifyLocale::lmsg('permissions.scanning_allowed.description'),
                'master'      => ImunifyPermissions::PERMISSION_END_USER_IMUNIFY_ON,
            ],
            ImunifyPermissions::PERMISSION_IMUNIFY_CLEANUP_ALLOWED => [
                'default'     => true,
                'place'       => self::PLACE_MAIN,
                'name'        => ImunifyLocale::lmsg('permissions.cleanup_allowed.name'),
                'description' => ImunifyLocale::lmsg('permissions.cleanup_allowed.description'),
                'master'      => ImunifyPermissions::PERMISSION_END_USER_IMUNIFY_ON,
            ],
        ];
    }
}
