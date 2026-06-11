<?php

use \Imunify360\ImunifyHelper;
use \Imunify360\ImunifyPermissions;

const IMUNIFY_NAME = 'Imunify';
const COLOR_LOGO = 'logo';
const COLOR_CLIENT = 'client';

class Modules_Imunify360_CustomButtons extends pm_Hook_CustomButtons
{

    public function getButtons()
    {
        $session = new pm_Session();
        $client = $session->getClient();
        $buttons = array();

        if ($client->isAdmin()) {
            $buttons[] = $this->getButton(array(
                // Left panel for admins, in list of additional services
                self::PLACE_ADMIN_NAVIGATION,
                // Left panel for Power Users
                self::PLACE_HOSTING_PANEL_NAVIGATION,
            ), COLOR_LOGO);
        }
        if (ImunifyHelper::isClientPluginEnabled()) {
            $domains = $session->getCurrentDomains();
            if (($client->isReseller() || $client->isClient()) && !ImunifyHelper::checkHosting($domains)) {
                return $buttons;
            }
            if (!ImunifyPermissions::isAvailableForEndUser($client, $domains)) {
                return $buttons;
            }

            $use_dynamic_list = defined('pm_Hook_CustomButtons::PLACE_DOMAIN_PROPERTIES_DYNAMIC') && defined('pm_Hook_CustomButtons::SECTION_DOMAIN_PROPS_DYNAMIC_SECURITY');

            if ($use_dynamic_list) {
                $icon = version_compare(\pm_ProductInfo::getVersion(), '18.0.55', '>=') ? 'icon-colored.svg' : '16x16-dash.svg';
                $buttons[] = [
                    'place' => self::PLACE_DOMAIN_PROPERTIES_DYNAMIC,
                    'section' => self::SECTION_DOMAIN_PROPS_DYNAMIC_SECURITY,
                    'title' => IMUNIFY_NAME,
                    'description' => IMUNIFY_NAME,
                    'icon' => pm_Context::getBaseUrl() . "assets/images/$icon",
                    'contextParams' => true,
                    'link' => pm_Context::getBaseUrl(),
                    'order' => 1,
                    'visibility' => function ($options) use ($client) {
                        return $this->isAllowedForDomain($options, $client);
                    },
                ];
            } else {
                // Right panel (domains) for clients and resellers.
                // If client has 2 domains, he will be asked to choose one.
                $buttons[] = $this->getButton([
                    self::PLACE_DOMAIN,
                    self::PLACE_RESELLER_NAVIGATION,
                ], COLOR_CLIENT);
            }
        }

        return $buttons;
    }

    private function getButton($place, $color) {
        return array(
            'place' => $place,
            'title' => IMUNIFY_NAME,
            'description' => IMUNIFY_NAME,
            'link' => pm_Context::getBaseUrl(),
            'icon' => pm_Context::getBaseUrl() . 'assets/images/imunify360-' . $color . '.png',
            'newWindow' => false,
        );
    }

    private function isAllowedForDomain($options, $client): bool
    {
        if (!empty($options['alias_id'])) {
            return false;
        }
        $domain_id = isset($options['site_id']) ? $options['site_id'] : -1;
        if ($domain_id <= 0) {
            return false;
        }

        $domain = pm_Domain::getByDomainId($domain_id);
        if (!$domain->hasHosting()) {
            return false;
        }
        if (!$client->hasAccessToDomain($domain->getId())) {
            return false;
        }

        if (!$domain->hasPermission(ImunifyPermissions::PERMISSION_END_USER_IMUNIFY_ON)) {
            return false;
        }

        return true;
    }
}
