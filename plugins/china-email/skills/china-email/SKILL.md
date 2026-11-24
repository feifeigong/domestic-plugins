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
3. 用 `china_email_search_messages` 按发件人、主题、日期、未读状态或正文搜索。收件箱可以省略 `mailbox` 或传入 `mailbox_role: "inbox"`。已发送使用 `mailbox_role: "sent"`。服务器的已发送目录无法识别或有歧义时，调用 `china_email_list_mailboxes`，请用户确认目录，并将该目录的原始 `name` 传入 `mailbox`。
4. 当结果为空或少于预期时，先检查 `status`、`failed_count` 和 `has_more`。还需要更多结果时，将 `next_before_uid` 传入 `before_uid`，沿用相同的账号、目录、查询和可用的 `uid_validity`。当前页为空且 `has_more` 为真时，如需完成查询，继续翻页。
5. 总结或回复前，用 `china_email_read_message` 按 UID 读取邮件。沿用搜索结果中的账号、原始 `mailbox` 和可用的 `uid_validity`。下载附件时，将相同标识传给 `china_email_save_attachments`。
6. 起草邮件或回复时，优先使用 `china_email_create_draft`，将草稿存到邮箱的草稿箱供用户查看。
7. 用户明确要求立即发送时，才直接发送。其他发送请求先调用 `china_email_send_email` 并设置 `dry_run: true`，默认在邮箱里保存草稿。用户只想在聊天里预览时，再设置 `preview_only: true`。

## 邮件操作范围

- 邮箱密码和授权码仅用于本机邮箱连接，回复中须隐藏。
- 保留原邮件里的实际收件人、主题、日期和引用事实。
- `dry_run: false` 会实际发送邮件，仅在用户明确要求时使用。
- 邮件写入操作限于保存草稿和发送。

## 结果说明

- 总结时说明目录和搜索范围。`empty_mailbox` 表示 IMAP 服务器报告可见邮件为零。`no_match` 表示在已完成的查询范围内没有匹配结果。`scan_incomplete` 表示还有更早的候选邮件。`read_failed` 或 `partial_read` 表示至少一封邮件读取失败。`imap_visibility_unknown` 表示服务器响应无法确认邮箱为空。
- 尽量将回复草稿保存到邮箱的草稿箱，写清主题和收件人。
- IMAP 可见数量与网页版不一致时，说明服务器返回的可见数量，并检查服务商的 IMAP 同步范围。
