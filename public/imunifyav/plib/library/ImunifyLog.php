<?php

namespace Imunify360;

class ImunifyLog
{
    const PSAADM_USER = 'psaadm';
    private static $def_log_local_filename = 'imunify360-local.log';
    private static $def_log_local_filepath = null;

    const ERR   = 0;
    const WARN  = 1;
    const INFO  = 2;
    const DEBUG = 3;

    private static $default_zend_logger = null;

    public static function err($message, $logFileName = null)
    {
        if (!self::mayLog(self::ERR)) {
            return;
        }
        \pm_Log::err($message);
        self::log(self::ERR, $message, $logFileName);
    }

    public static function warn($message, $logFileName = null)
    {
        if (!self::mayLog(self::WARN)) {
            return;
        }
        \pm_Log::warn($message);
        self::log(self::WARN, $message, $logFileName);
    }

    public static function info($message, $logFileName = null)
    {
        if (!self::mayLog(self::INFO)) {
            return;
        }
        \pm_Log::info($message);
        self::log(self::INFO, $message, $logFileName);
    }

    public static function debug($message, $logFileName = null)
    {
        if (!self::mayLog(self::DEBUG)) {
            return;
        }
        \pm_Log::debug($message);
        self::log(self::DEBUG, $message, $logFileName);
    }

    /**
     * Internal log method using \Zend_Log.
     *
     * @param int $level The log level (self::ERR, self::WARN, etc.).
     * @param string $message The message to log.
     * @param string|null $logFileName If provided, logs to this file instead of the default.
     *                                  The filename should be relative to Plesk's var directory.
     *        By default, error logs will be in /var/log/plesk/panel.log
     *        Logs with other log levels will be in logFileName if it present or in imunify360-local.log
     *        here: /usr/local/psa/var/modules/imunify360/imunify-notifications.log
     */
    private static function log(int $level, string $message, ?string $logFileName = null)
    {
        $priority = \Zend_Log::DEBUG; // Default priority
        if ($level == self::ERR) {
            $priority = \Zend_Log::ERR;
        } elseif ($level == self::WARN) {
            $priority = \Zend_Log::WARN;
        } elseif ($level == self::INFO) {
            $priority = \Zend_Log::INFO;
        }

        $logger = null;
        $log_filepath = '';

        if (is_null($logFileName)) {
            $log_filepath = self::getLogLocalFilepath();
            if (is_null(self::$default_zend_logger)) {
                $writer = new \Zend_Log_Writer_Stream($log_filepath);
                self::$default_zend_logger = new \Zend_Log($writer);
                self::$default_zend_logger->setTimestampFormat('y.m.d G:i:s');
                self::setupLogFilePermissions($log_filepath);
            }
            $logger = self::$default_zend_logger;

        } else {
            $safeLogFileName = basename($logFileName);
            if (empty($safeLogFileName)) {
                self::err("Invalid custom log filename provided: '{$logFileName}'");
                return;
            }
            $log_filepath = \pm_Context::getVarDir() . DIRECTORY_SEPARATOR . $safeLogFileName;

            try {
                $writer = new \Zend_Log_Writer_Stream($log_filepath);
                $logger = new \Zend_Log($writer);
                $logger->setTimestampFormat('y.m.d G:i:s');
                self::setupLogFilePermissions($log_filepath);
            } catch (\Exception $e) {
                self::err("Failed to create or write to custom log file '{$log_filepath}': " . $e->getMessage());
                return;
            }
        }

        if ($logger) {
            if (!is_scalar($message)) {
                $message = print_r($message, true);
            }
            $logger->log((string)$message, $priority);
        }
    }

    private static function setupLogFilePermissions(string $filepath): void
    {
        self::setOwnPleskUserForFile($filepath);
        self::setFileMod($filepath, 0600);
    }

    private static function mayLog(int $log_level): bool
    {
        return self::getLogMaxLevel() >= $log_level;
    }

    public static function getLogMaxLevel(): int
    {
        return self::INFO; // Keep INFO as default for now
    }

    public static function getLogLocalFilepath(): string
    {
        if (!is_null(self::$def_log_local_filepath)) {
            return self::$def_log_local_filepath;
        }
        $varDir = \pm_Context::getVarDir();
        if (!is_dir($varDir)) {
            @mkdir($varDir, 0755, true); // Attempt to create if missing
        }
        self::$def_log_local_filepath = $varDir . DIRECTORY_SEPARATOR . self::$def_log_local_filename;
        return self::$def_log_local_filepath;
    }


    public static function setOwnPleskUserForFile(string $filepath)
    {
        if (!self::currentUserIsRoot()) {
            return;
        }
        if (file_exists($filepath)) {
            @chown($filepath, self::PSAADM_USER);
        }
    }

    private static function currentUserIsRoot(): bool
    {
        if (function_exists('posix_getuid') && posix_getuid() === 0) {
            return true;
        }
        return false;
    }

    public static function setFileMod(string $filepath, $mod = 0600)
    {
        if (file_exists($filepath)) {
            @chmod($filepath, $mod);
        }
    }
}
