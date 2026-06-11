<?php

namespace Imunify360;

class ImunifyNotification
{
    private $im_client = null;
    private $malicious_total = 0;
    private $subject = '';
    private $text = '';

    private string $defaultMessage = '<event_details>';
    static string $overriddenMessage = '<event_details>';

    public function __construct(ImunifyClient $im_client, $request)
    {

        $this->im_client = $im_client;
        $this->buildNotification($request);
    }

    public static function getDefaults(): array
    {
        $defaultSubject = '<event_subject>';

        return [
            'admin_notification' => [
                'title'             => ImunifyLocale::lmsg('hooks.notification.title.admin'),
                'notifyAdmin'       => true,
                'notifyResellers'   => false,
                'notifyClients'     => false,
                'notifyCustomEmail' => false,
                'customEmail'       => '',
                'subject'           => $defaultSubject,
                'message'           => self::$overriddenMessage,
            ],
            'reseller_notification' => [
                'title'             => ImunifyLocale::lmsg('hooks.notification.title.reseller'),
                'notifyAdmin'       => false,
                'notifyResellers'   => true,
                'notifyClients'     => false,
                'notifyCustomEmail' => false,
                'customEmail'       => '',
                'subject'           => $defaultSubject,
                'message'           => self::$overriddenMessage,
            ],
            'client_notification' => [
                'title'             => ImunifyLocale::lmsg('hooks.notification.title.client'),
                'notifyAdmin'       => false,
                'notifyResellers'   => false,
                'notifyClients'     => true,
                'notifyCustomEmail' => false,
                'customEmail'       => '',
                'subject'           => $defaultSubject,
                'message'           => self::$overriddenMessage,
            ],
        ];
    }

    public function send($isGeneric): void
    {
        $customer_type = $this->getCustomerType();
        if (empty($customer_type)) {
            ImunifyLog::err('Failed to define customer type');
            return;
        }

        $subject = $this->getSubject();
        $notificationManager = new \pm_Notification();
        $emailMessage = $this->getText();

        if ($isGeneric) {
            self::$overriddenMessage = $emailMessage;
            $emailMessage = '';
        }

        try {
            $notificationManager->send(
                $customer_type . '_notification',
                [
                    'event_subject' => $subject,
                    'event_details' => $emailMessage,
                ],
                $this->im_client->getPMClient()
            );
            ImunifyLog::info('Notification with subject "' . $subject . '" was sent to ' . $customer_type);
        } catch (\pm_Exception $e) {
            ImunifyLog::err('Failed to send notification: ' . $e->getMessage());
        } finally {
            // restore original default message
            self::$overriddenMessage = $this->defaultMessage;
        }
    }


    public function getSubject()
    {
        return $this->subject;
    }

    public function getText()
    {
        return $this->text;
    }

    private function getCustomerType(): string
    {
        if ($this->im_client->isAdmin()) {
            return 'admin';
        } elseif ($this->im_client->isReseller()) {
            return 'reseller';
        } elseif ($this->im_client->isClient()) {
            return 'client';
        }
        return '';
    }

    private function buildNotification($request): void
    {
        // Generic notification: subject/body are passed directly via params
        if (isset($request->message_type) && strtolower($request->message_type) === 'generic') {
            $params = [];
            if (isset($request->params)) {
                if (is_object($request->params)) {
                    $params = get_object_vars($request->params);
                } elseif (is_array($request->params)) {
                    $params = $request->params;
                }
            }
            $this->subject = isset($params['subject']) ? (string)$params['subject'] : 'Imunify notification';
            // Prefer HTML if provided, otherwise fall back to plain text/body
            if (isset($params['body_html'])) {
                $this->text = (string)$params['body_html'];
            } elseif (isset($params['body'])) {
                $this->text = nl2br((string)$params['body']);
            } elseif (isset($params['text'])) {
                $this->text = nl2br((string)$params['text']);
            } else {
                $this->text = '';
            }
            return;
        }

        if (isset($request->total_malicious)) {
            $this->malicious_total = $request->total_malicious;
        } elseif (isset($request->malicious_total)) {
            $this->malicious_total = $request->malicious_total;
        } else {
            $this->malicious_total = 0;
        }
        $this->buildSubject();
        $this->buildText($request);
    }

    private function buildSubject()
    {
        $this->subject = ImunifyLocale::lmsg('hooks.notification.message.subject');
    }

    private function buildText($jsonEvents)
    {
        if (!is_array($jsonEvents)) {
            $jsonEvents = array($jsonEvents);
        }
        $events = array();
        foreach ($jsonEvents as $ev) {
            if (is_string($ev)) {
                $ev = json_decode($ev, true);
            } elseif (is_object($ev)) {
                $ev = get_object_vars($ev);
            }

            if (is_array($ev)) {
                $events[] = $ev;
            }
        }
        if (!$events) {
            return '';
        }

        $prettyId = array(
            'REALTIME_MALWARE_FOUND' => 'Real-Time Scan',
            'CUSTOM_SCAN_MALWARE_FOUND' => 'On-Demand Scan',
            'USER_SCAN_MALWARE_FOUND' => 'User-Initiated Scan',
        );

        $lines = array();
        foreach ($events as $ev) {
            $id = isset($ev['event_id']) ? $ev['event_id'] : 'UNKNOWN_EVENT';
            $label = isset($prettyId[$id]) ? $prettyId[$id] : $id;

            $started = isset($ev['started'])
                ? $ev['started']
                : (isset($ev['period_started']) ? $ev['period_started'] : time());

            $finished = isset($ev['completed'])
                ? $ev['completed']
                : (isset($ev['period_finished']) ? $ev['period_finished'] : null);

            $ts = $finished ? $finished : $started;
            $when = date('Y-m-d H:i', $ts);

            $initiator = isset($ev['initiator']) ? $ev['initiator'] : 'system';

            $total = isset($ev['malicious_total'])
                ? $ev['malicious_total']
                : (isset($ev['total_malicious']) ? $ev['total_malicious'] : 0);

            $filesRaw = isset($ev['malicious_files']) ? $ev['malicious_files'] : array();
            $files = array();


            foreach ($filesRaw as $k => $v) {

                if (is_int($k)) {

                    $files[] = $v;
                } elseif (is_array($v)) {

                    $files = array_merge($files, $v);
                }
            }
            $lines[] =
                "⏰  " . $when . " — " . $label . "\n" .
                "Initiator : " . $initiator . "\n" .
                "Malicious : " . $total . " file(s)\n" .
                "Files     :\n  • " . implode("\n  • ", $files) . "\n";
        }

        $product = ImunifyHelper::getAppMode();
        $product = $product == ImunifyHelper::IMUNIFY_360 ? 'Imunify360' : 'ImunifyAV';

        $header =  $product . " Security Events Digest\n\n";
        $this->text = $header . implode("\n", $lines);
    }

}
