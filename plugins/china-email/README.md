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

## 搜索邮件

`china_email_search_messages` 默认查收件箱 `INBOX`。查询已发送目录时，使用 `mailbox_role: "sent"`。查整个邮箱时，先用 `china_email_list_mailboxes` 查看 IMAP 可见目录，再按需要查询收件箱、归档或自定义目录。指定目录时，将列表返回的原始 `name` 传给 `mailbox`。

日期使用 `YYYY-MM-DD`。`since` 和 `through` 都包含当天，`before` 不包含当天，`through` 与 `before` 只能选一个。例如查询 2026 年 9 月，可用以下条件。

```json
{"query": {"since": "2026-09-01", "through": "2026-09-30", "date_field": "received"}}
```

`date_field` 默认是 `received`，按服务器记录的收件日期筛选。若按邮件上展示的邮件头日期筛选，使用 `date_field: "sent"`。日期口径与邮件所在目录独立设置。

每页默认最多返回 10 个结果，`limit` 最大 50，`scan_limit` 每页最大 500。要查完指定范围，`has_more` 为真时，将 `next_before_uid` 传给下一页的 `before_uid`。沿用相同的账号、目录、查询和可用的 `uid_validity`，即使某一页没有结果也可继续。各目录分别分页。读取邮件和下载附件时也沿用相同的目录与可用的 `uid_validity`。

结果会区分 IMAP 报告的目录总数、搜索候选数、已扫描数和读取失败数。`empty_mailbox` 表示服务器报告该目录有零封可见邮件。`no_match` 表示已查范围内没有匹配结果。`scan_incomplete` 表示仍有候选未扫描。`read_failed` 和 `partial_read` 表示有邮件读取失败。`imap_visibility_unknown` 表示无法确认该目录是否为空。`imap_count_mismatch: true` 表示首页在 IMAP 服务器上执行全量搜索时，服务器报告的目录总数与搜索候选数不一致。

如果只查了收件箱却找不到历史邮件，先核对日期口径。若依据邮件头日期，可在同一目录用 `date_field: "sent"` 复查。有已知主题或发件人时，也可去掉日期条件复查。若需要核对归档或自定义目录，请分别查询并区分各目录结果。网页版与 IMAP 不一致时，先确认账号和实际目录一致，再检查服务商的 IMAP 同步范围。

## Configuration

After installing the plugin, select **Run setup** to open the local setup wizard. You can also
open it from a local Work or Codex conversation:

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

## Runtime Requirements

Use a local Work or Codex conversation in the ChatGPT desktop app.
Windows x64 and ARM64 ship with an embedded Python runtime under `runtime/windows`.
To open the wizard independently on Windows, run `bin\china-email.cmd setup`.
On macOS and Linux, install Python 3.10 or newer. The launcher tries `python3` and then `python`.
