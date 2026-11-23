# China Email Codex Plugin

This plugin connects Codex to domestic email providers through standard IMAP and SMTP.
It is provider-neutral: QQ Mail, NetEase 163/126/yeah, Ali Mail, Tencent Exmail, 139 Mail,
and custom enterprise mailboxes can all be configured with the same account format.

## MVP Scope

- List configured accounts without exposing secrets.
- Test IMAP and SMTP login.
- List IMAP folders, find the Sent mailbox, and search mailbox messages page by page.
- Read a single message by mailbox and IMAP UID.
- Save message attachments to a local folder.
- Create real mailbox drafts for review by default, and send only when `dry_run` is explicitly `false`.

## Marketplace Entry

This plugin is registered by the repository marketplace file:

```text
.agents/plugins/marketplace.json
```

When this repository is opened in Codex App, it appears as `国内邮箱` in the `国内插件市场` marketplace.

## Reading inbox and sent mail

`china_email_search_messages` defaults to `INBOX`. For sent mail, pass `mailbox_role: "sent"` to resolve the server's Sent folder. Use `china_email_list_mailboxes` to check available folders and pass the exact `name` as `mailbox` when selecting one manually.

Each page returns up to 10 results by default. Set `limit` up to 50 and `scan_limit` up to 500 per page. If `has_more` is true, pass `next_before_uid` as `before_uid` with the same account, returned `mailbox`, query, and `uid_validity` when available. This also works when a page contains no matches. Pass the same mailbox and UID validity when reading a result or downloading its attachments.

The response includes the IMAP-visible mailbox count, search candidate count, scanned count, and fetch failures. `empty_mailbox` means the IMAP server reported zero messages. `no_match`, `scan_incomplete`, `read_failed`, `partial_read`, and `imap_visibility_unknown` describe distinct results. Check the provider's IMAP sync range if webmail shows more messages than the server reports to the plugin.

## Configuration

The recommended path is the local setup wizard. After installing the plugin, ask Codex:

```text
打开国内邮箱配置向导
```

The plugin starts a local browser page on `127.0.0.1`. Choose the provider, enter the email address and mailbox authorization code, then click save. The wizard writes the account file for you.

You can also run the wizard directly:

```bash
python3 ./src/china_email_mcp.py setup
```

Manual configuration is still supported. Create an account file outside the plugin directory:

```bash
mkdir -p ~/.china-email
cp ./config/accounts.example.json ~/.china-email/accounts.json
```

Then edit `~/.china-email/accounts.json`.

Use email client authorization codes or app passwords, not normal web login passwords.
For many domestic providers, IMAP/SMTP must be enabled in the web mailbox settings first.

You can also point the plugin at another file:

```bash
export CHINA_EMAIL_CONFIG=/absolute/path/to/accounts.json
```

Or configure one account directly with environment variables:

```bash
export CHINA_EMAIL_ACCOUNT_NAME=work
export CHINA_EMAIL_PROVIDER=qq
export CHINA_EMAIL_ADDRESS=your-name@qq.com
export CHINA_EMAIL_USERNAME=your-name@qq.com
export CHINA_EMAIL_PASSWORD=your-authorization-code
```

## Provider Presets

| Provider | IMAP | SMTP |
| --- | --- | --- |
| `qq` | `imap.qq.com:993` | `smtp.qq.com:465` |
| `163` | `imap.163.com:993` | `smtp.163.com:465` |
| `126` | `imap.126.com:993` | `smtp.126.com:465` |
| `yeah` | `imap.yeah.net:993` | `smtp.yeah.net:465` |
| `tencent-exmail` | `imap.exmail.qq.com:993` | `smtp.exmail.qq.com:465` |
| `aliyun-mail` | `imap.qiye.aliyun.com:993` | `smtp.qiye.aliyun.com:465` |
| `139` | `imap.139.com:993` | `smtp.139.com:465` |

If a provider, company mailbox, or school mailbox uses different hosts, set `provider` to
`custom` and provide explicit `imap` and `smtp` blocks.

## Local MCP Test

Run the server directly:

```bash
python3 ./src/china_email_mcp.py
```

Then send JSON-RPC messages over stdin. For example:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"0.0.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"china_email_list_providers","arguments":{}}}
```

## Security Notes

- Do not commit real account configuration.
- Prefer provider authorization codes over account passwords.
- Prefer the local setup wizard over sending passwords or authorization codes in a Codex chat message.
- Keep sending as an explicit action. The `china_email_send_email` tool defaults to `dry_run`, which writes a mailbox draft unless `preview_only` is set.
- Attachment writes default to `~/Downloads/china-email-attachments`.

## Windows Notes

The checked-in `.mcp.json` uses `python3`, which works on macOS and many developer machines.
For Windows, change the command to `py` or the absolute path to the Python executable if needed:

```json
{
  "mcpServers": {
    "china-email": {
      "command": "py",
      "args": ["-3", "./src/china_email_mcp.py"],
      "cwd": "."
    }
  }
}
```

Longer term, this plugin should be packaged with a launcher so users do not need to edit `.mcp.json`.
