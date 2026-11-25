---
name: china-email
description: 查阅 QQ、网易、阿里、腾讯企业邮、139 邮箱和自定义企业邮箱的邮件，整理收件箱、保存附件、起草和发送邮件。
---

# 邮箱收发与管理

## 邮箱状态

先通过 IMAP 搜索或读取邮件，再说明邮箱状态。

## 邮箱配置

- 在邮箱网页端启用 IMAP 和 SMTP。
- 使用邮箱授权码、应用专用密码或客户端密码。
- 优先调用 `china_email_start_setup` 打开配置向导。
- 向导将账户配置保存在 `~/.china-email/accounts.json`。也可以通过 `CHINA_EMAIL_CONFIG` 或单账号环境变量指定配置。

## 操作步骤

1. 用户未指定已配置的邮箱时，先调用 `china_email_list_accounts`。
2. 如果还没有邮箱账号，调用 `china_email_start_setup`，提供返回的本机向导链接。
3. 用 `china_email_search_messages` 按发件人、主题、日期、未读状态或正文搜索。查收件箱可以省略 `mailbox` 或传入 `mailbox_role: "inbox"`，查已发送使用 `mailbox_role: "sent"`。用户要求查整个邮箱时，先用 `china_email_list_mailboxes` 列出目录，按请求范围查相关且 `selectable` 为真的目录。找不到「已发送」或有多个候选时，请用户确认。向用户展示 `display_name`，查询时把目录的原始 `name` 传入 `mailbox`。
4. 日期使用 `YYYY-MM-DD`。`since` 和 `through` 都包含当天，`before` 不含当天，`through` 和 `before` 只选一个。查询 2026 年 9 月可传入 `since: "2026-09-01"` 和 `through: "2026-09-30"`。默认 `date_field: "received"` 按服务器记录的收件日期查询。用户明确按邮件头日期查询时，传入 `date_field: "sent"`，并沿用原目录。
5. 结果为空或少于预期时，检查 `mailbox_message_count`、`candidate_count`、`failed_count` 和 `has_more`。如需查完当前范围，沿用相同账号、目录、查询和可用的 `uid_validity`，把每页的 `next_before_uid` 传给下一页的 `before_uid`，即使某页没有结果。各目录分别分页。
6. 用户查历史邮件无结果或反馈漏信时，先在原目录复查。若用户没有限定必须按服务器收件日期，另用 `date_field: "sent"` 复查同一日期范围，并注明这些结果按邮件上显示的日期命中。目录总数很少时，去掉日期筛选核对可见邮件。若仍查不到且需要排查邮件位置，列出同一邮箱的可见目录，在请求范围内查归档和自定义目录。单独报告各目录的结果。
7. 总结或回复前，用 `china_email_read_message` 按 UID 读取邮件。沿用搜索结果中的账号、原始 `mailbox` 和可用的 `uid_validity`。下载附件时，将相同标识传给 `china_email_save_attachments`。
8. 起草邮件或回复时，优先使用 `china_email_create_draft`，将草稿存到邮箱的草稿箱供用户查看。
9. 用户明确要求立即发送时，才直接发送。其他发送请求先调用 `china_email_send_email` 并设置 `dry_run: true`，默认在邮箱里保存草稿。用户只想在聊天里预览时，再设置 `preview_only: true`。

## 邮件操作范围

- 邮箱密码和授权码仅用于本机邮箱连接，回复中须隐藏。
- 保留原邮件里的实际收件人、主题、日期和引用事实。
- `dry_run: false` 会实际发送邮件，仅在用户明确要求时使用。
- 邮件写入操作限于保存草稿和发送。

## 结果说明

- 总结时说明已查目录、日期口径和读取失败数。`empty_mailbox` 表示 IMAP 服务器报告该目录可见邮件为零。`no_match` 表示在已完成的查询范围内没有匹配结果。`scan_incomplete` 表示还有更早的候选邮件。`read_failed` 或 `partial_read` 表示至少一封邮件读取失败。`imap_visibility_unknown` 表示服务器响应无法确认该目录为空。只在查完指定范围且无读取失败时报告无匹配，同时区分尚未查询的目录。
- 尽量将回复草稿保存到邮箱的草稿箱，写清主题和收件人。
- `imap_count_mismatch: true` 表示首页在 IMAP 服务器上执行全量搜索时，服务器报告的目录总数与搜索返回的候选数不一致。报告这两个数并说明只能确认 IMAP 返回的结果。若与网页版也不同，请用户核对同一账号、实际目录和服务商的 IMAP 同步范围。
