<?php

namespace Imunify360;

class ImunifyLocale
{

    public static function lmsg($key, $params = [])
    {
        $text = \pm_Locale::lmsg($key, $params);
        if (strpos($text, '{{') !== false || strpos($text, '}}') !== false) {
            $text = self::replace($text);
        }
        return $text;
    }

    private static function replace($text)
    {
        $text = preg_replace_callback('~\{\{(\d+):([^,]*),([^,]*)\}\}~', [self::class, 'enReplace'], $text);
        return preg_replace('~\{\{[^\]]*\}\}~', '', $text);
    }

    private static function enReplace($matches)
    {
        $cnt = $matches[1];
        $tr1 = $matches[2];
        $tr2 = $matches[3];

        if ($cnt == 1) {
            return $tr1;
        }
        return $tr2;
    }

}
