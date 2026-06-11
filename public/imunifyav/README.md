# Imunify Plesk Notifications

## Generic notification

A new notification type "Generic" is supported via the Plesk notifications hook. It can be used to send arbitrary messages to Admin, Reseller, or Client recipients.

- Supported fields:
  - `message_type`: must be `Generic`
  - `params.subject`: email subject (string)
  - `params.body_html`: email body as HTML (preferred)
  - `params.body` or `params.text`: plain-text fallback (optional)
  - `user`: Plesk login to receive the message (optional). If omitted, the Admin user is used.

### Invocation

The Agent invokes the Plesk hook by writing JSON to stdin of the `send-notifications` script, which calls the Plesk extension entry point `send-notifications.php`.

Example JSON payload:

```json
{
  "message_type": "Generic",
  "params": {
    "subject": "Malicious activity on your server",
    "body_html": "<p>Dear Client,</p><p>...your HTML here...</p>"
  },
  "user": "client_login"
}
```

### Manual test

On a server with the Plesk extension installed, run:

```bash
echo '{"message_type":"Generic","params":{"subject":"Test Generic","body_html":"<p>Hello from Imunify</p>"},"user":"client_login"}' | sudo /opt/imunify360/venv/share/imunify360/scripts/send-notifications
```

- To notify Admin, omit `"user"` or set it to an admin login.
- Check Plesk mail delivery or the recipient mailbox to verify the email rendering.

### Notes

- HTML content from `params.body_html` is passed directly to Plesk notifications.
- If `params.body_html` is not provided, the notification falls back to plain text. 