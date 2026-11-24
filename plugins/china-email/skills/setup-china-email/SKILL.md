---
name: setup-china-email
description: 在本机浏览器打开配置向导，用于首次设置插件或新增 QQ、网易等国内邮箱账号。
---

# 配置国内邮箱

1. 调用 `china_email_start_setup`，传入 `open_browser: true`。用户已经明确邮箱服务商时，传入对应的 `provider`。其他情况由用户在向导里选择。
2. 如果 `opened_browser` 为真，告诉用户在打开的网页填入邮箱地址和客户端授权码。如果为假，提供工具返回的本机向导链接供用户点击。
3. 让用户在本机向导里输入授权码。工具无法调用时，提示用户在 ChatGPT 桌面端新开本机 Work 或 Codex 会话后重试。
