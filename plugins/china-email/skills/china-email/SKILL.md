---
name: china-email
description: Use domestic IMAP/SMTP email accounts such as QQ Mail, NetEase Mail, Ali Mail, Tencent Exmail, 139 Mail, or custom enterprise mailboxes to search messages, read email, save attachments, summarize inboxes, and draft or send replies.
---

# China Email

## Overview

Use this skill when the user wants to work with domestic Chinese email accounts through the China Email plugin.
The plugin is protocol-based, so prefer IMAP search and message reads before making claims about mailbox state.

## Setup Expectations

- The mailbox must have IMAP/SMTP enabled in the provider's web settings.
- The password should be an authorization code, app password, or client password.
- Prefer `china_email_start_setup` for setup so users do not need to edit JSON.
- The account config is saved to `~/.china-email/accounts.json` by the setup wizard, and can still be overridden with `CHINA_EMAIL_CONFIG` or single-account environment variables.

## Workflow

1. Call `china_email_list_accounts` first if the user did not specify which configured account to use.
2. If no accounts are configured, call `china_email_start_setup` and give the user the returned local URL.
3. Use `china_email_search_messages` to shortlist messages by sender, subject, date, unread state, or text. For the inbox, omit the mailbox or use `mailbox_role: "inbox"`. For 已发送, use `mailbox_role: "sent"`. If the server lists an ambiguous or unrecognized Sent mailbox, call `china_email_list_mailboxes` and ask the user which folder to use. Use the returned exact `name` as `mailbox`.
4. Check `status`, `failed_count`, and `has_more` before describing an empty or short page. Follow `next_before_uid` as `before_uid` when the request needs more results. Keep the same account, resolved `mailbox`, query, and `uid_validity` when available. Continue past an empty page when `has_more` is true and the scan is needed to answer the user.
5. Use `china_email_read_message` for the specific UID before summarizing that message or replying. Pass the search result's account name, exact `mailbox`, and `uid_validity` when available. Use the same identifiers with `china_email_save_attachments` when the user asks to download attachments.
6. For drafts or replies, prefer `china_email_create_draft` so the message appears in the provider's Drafts mailbox for user review.
7. For sending, call `china_email_send_email` with `dry_run: true` first unless the user explicitly asked to send immediately. With the current tool, `dry_run: true` saves a mailbox draft by default; use `preview_only: true` only when the user wants chat-only preview text.

## Write Safety

- Never expose configured passwords or authorization codes.
- Preserve exact recipients, subjects, dates, and quoted facts from source messages.
- Treat `dry_run: false` as a real send operation and use it only with explicit user intent.
- Do not delete, archive, mark read, move, or label messages in this MVP.

## Output Conventions

- Summaries should state the mailbox and search scope. `empty_mailbox` means the IMAP server reported zero visible messages. `no_match` means no matches in the completed search scope. `scan_incomplete` means older candidates remain. `read_failed` or `partial_read` means one or more fetches failed. `imap_visibility_unknown` means the IMAP response did not confirm an empty mailbox.
- Draft replies should be saved to the mailbox Drafts folder when possible, with a clear subject and recipient list.
- If the IMAP-visible count differs from webmail, report the visible count and check the provider's IMAP sync scope.
