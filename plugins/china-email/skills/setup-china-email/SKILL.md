---
name: setup-china-email
description: 在本机浏览器打开配置向导，用于首次设置插件或新增 QQ、网易等国内邮箱账号。
---

# 配置国内邮箱

1. 调用 `china_email_start_setup`，传入 `open_browser: true`。用户已经明确邮箱服务商时，传入对应的 `provider`。其他情况由用户在向导里选择。
2. 如果 `opened_browser` 为真，告诉用户在打开的网页填入邮箱地址和客户端授权码。如果为假，提供工具返回的本机向导链接供用户点击。
3. 让用户在本机向导里输入授权码。工具无法调用时，说明向导尚未打开。请用户在本机 Codex 会话输入 `/mcp`，核对 `china-email` 的连接状态。Windows 用户可以从已下载的仓库目录运行 `.\plugins\china-email\bin\china-email.cmd setup` 独立打开向导。
