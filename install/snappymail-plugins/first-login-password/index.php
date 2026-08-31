<?php

/**
 * SOFTI-MEJORA — Cambio obligatorio de contraseña en primer login a SnappyMail.
 */
class FirstLoginPasswordPlugin extends \RainLoop\Plugins\AbstractPlugin
{
    const
        NAME        = 'First Login Password',
        VERSION     = '1.0.0',
        RELEASE     = '2026-08-30',
        REQUIRED    = '2.36.1',
        CATEGORY    = 'Security',
        DESCRIPTION = 'Force mailbox password change on first SnappyMail login (Softi/CyberPanel)';

    /** @var \RainLoop\Config\Plugin */
    private $oConfig;

    public function Init() : void
    {
        $this->oConfig = $this->Config();
        $this->addJs('js/FirstLoginGate.js');
        $this->addJsonHook('FirstLoginCheck', 'CheckMustChange');
        $this->addJsonHook('FirstLoginChangePassword', 'ChangePassword');
    }

    public function Supported() : string
    {
        return 'First login password gate for CyberPanel e_users.must_change_password';
    }

    public static function configMapping() : array
    {
        return array(
            \RainLoop\Plugins\Property::NewInstance('pdo_dsn')->SetLabel('DSN')
                ->SetDefaultValue('mysql:host=localhost;dbname=cyberpanel;charset=utf8'),
            \RainLoop\Plugins\Property::NewInstance('pdo_user')->SetLabel('User')
                ->SetDefaultValue('root'),
            \RainLoop\Plugins\Property::NewInstance('pdo_password')->SetLabel('Password')
                ->SetType(\RainLoop\Enumerations\PluginPropertyType::PASSWORD),
        );
    }

    private function pdo() : \PDO
    {
        return new \PDO(
            $this->oConfig->Get('plugin', 'pdo_dsn', 'mysql:host=localhost;dbname=cyberpanel;charset=utf8'),
            $this->oConfig->Get('plugin', 'pdo_user', 'root'),
            $this->oConfig->Get('plugin', 'pdo_password', ''),
            array(
                \PDO::ATTR_ERRMODE => \PDO::ERRMODE_EXCEPTION,
                \PDO::ATTR_EMULATE_PREPARES => true,
            )
        );
    }

    private function accountEmail() : string
    {
        $oAccount = \RainLoop\Api::Actions()->GetAccount();
        if (!$oAccount) {
            throw new \RainLoop\Exceptions\ClientException(\RainLoop\Notifications::AuthError);
        }
        return $oAccount->Email();
    }

    private function mustChange(string $email) : bool
    {
        $stmt = $this->pdo()->prepare(
            'SELECT must_change_password FROM e_users WHERE email = :email LIMIT 1'
        );
        $stmt->execute(array(':email' => $email));
        $row = $stmt->fetch(\PDO::FETCH_ASSOC);
        return $row && (int) $row['must_change_password'] === 1;
    }

    /**
     * @return array{mustChange:bool}
     */
    public function CheckMustChange() : array
    {
        return array('mustChange' => $this->mustChange($this->accountEmail()));
    }

    private function verifyCurrentPassword(string $email, string $currentPassword) : void
    {
        $stmt = $this->pdo()->prepare('SELECT password FROM e_users WHERE email = :email LIMIT 1');
        $stmt->execute(array(':email' => $email));
        $row = $stmt->fetch(\PDO::FETCH_ASSOC);
        if (!$row) {
            throw new \RainLoop\Exceptions\ClientException(\RainLoop\Notifications::AuthError);
        }

        $stored = (string) $row['password'];
        if (0 === \strpos($stored, '{CRYPT}')) {
            $stored = \substr($stored, 7);
        }

        if (!\password_verify($currentPassword, $stored)) {
            throw new \RainLoop\Exceptions\ClientException(
                \RainLoop\Notifications::AuthError,
                null,
                'Contraseña actual incorrecta'
            );
        }
    }

    private function hashPassword(string $plain) : string
    {
        return '{CRYPT}' . \password_hash($plain, \PASSWORD_BCRYPT);
    }

    /**
     * @param string $CurrentPassword
     * @param string $NewPassword
     * @param string $ConfirmPassword
     */
    public function ChangePassword(
        string $CurrentPassword = '',
        string $NewPassword = '',
        string $ConfirmPassword = ''
    ) : bool {
        $email = $this->accountEmail();

        if (!$this->mustChange($email)) {
            return true;
        }

        if ($NewPassword === '' || $NewPassword !== $ConfirmPassword) {
            throw new \RainLoop\Exceptions\ClientException(
                \RainLoop\Notifications::ClientViewError,
                null,
                'Las contraseñas nuevas no coinciden'
            );
        }

        if (\strlen($NewPassword) < 8) {
            throw new \RainLoop\Exceptions\ClientException(
                \RainLoop\Notifications::ClientViewError,
                null,
                'La contraseña debe tener al menos 8 caracteres'
            );
        }

        $this->verifyCurrentPassword($email, $CurrentPassword);

        $stmt = $this->pdo()->prepare(
            'UPDATE e_users SET password = :newpass, must_change_password = 0 WHERE email = :email'
        );
        $stmt->execute(array(
            ':newpass' => $this->hashPassword($NewPassword),
            ':email' => $email,
        ));

        return true;
    }
}
