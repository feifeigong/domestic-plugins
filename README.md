# 国内 Codex 插件市场

这个仓库是一个本地 Codex 插件市场。入口文件是：

- `.agents/plugins/marketplace.json`

当前已接入插件：

- `china-email`：国内邮箱插件，支持 QQ 邮箱、网易 163/126/yeah、腾讯企业邮箱、阿里企业邮箱、139 邮箱和自定义 IMAP/SMTP 邮箱。

## 更新到 0.2.5

用 Git 克隆的用户可在仓库目录运行 `git pull`。用 ZIP 安装的用户请从 GitHub 重新下载。用 GitHub 地址添加市场的用户，请在 ChatGPT 桌面端升级「国内插件市场」，再到「国内邮箱」详情页确认版本为 `0.2.5`。已有邮箱配置可继续使用。

现在可以让 Codex「列出已发送的最近 30 封邮件」，也可以让它继续往前查。若收件箱返回空结果，可让 Codex「检查 INBOX 在 IMAP 服务器上的邮件数量，不加任何筛选，报告读取失败数」。

## 在 Codex 中使用

Windows x64 和 ARM64 版插件自带运行时，安装后即可打开邮箱配置向导。macOS 和 Linux 用户需要在本机安装 Python 3.10 或更新版本。

在 Codex App 中打开这个仓库后，插件市场会读取 `.agents/plugins/marketplace.json`，并展示 `国内插件市场` 下的 `国内邮箱` 插件。

安装后，如果 ChatGPT 显示设置提示，点击「设置国内邮箱」。也可以在「国内邮箱」详情页点击「打开国内邮箱配置向导」，或在桌面端的新建本机 Work 或 Codex 会话中发送：

```text
@国内邮箱 打开国内邮箱配置向导
```

向导会在本机浏览器打开，用户选择邮箱服务商，填写邮箱地址和授权码，然后点保存即可，不需要手动改 JSON。

如果当前会话无法调用邮箱工具，可在本机 Codex 会话输入 `/mcp`，确认连接列表里是否有 `china-email`。Windows 用户也可以在下载的仓库目录打开 PowerShell，运行 `.\plugins\china-email\bin\china-email.cmd setup`，直接打开同一个本机配置向导。查询或发送邮件时，仍需要会话成功连接邮箱服务。

也可以手动配置：

```bash
mkdir -p ~/.china-email
cp ./plugins/china-email/config/accounts.example.json ~/.china-email/accounts.json
```

编辑 `~/.china-email/accounts.json`，填入邮箱地址、账号名和客户端授权码。

不要使用网页登录密码；QQ、网易等邮箱通常需要先在网页端设置里开启 IMAP/SMTP，并生成授权码或客户端专用密码。

## 从 GitHub 安装

把这个仓库发布到 GitHub 后，其他用户在 Codex App 中打开或克隆该仓库即可看到这个本地插件市场。
如果要进入官方公共插件市场，还需要按官方发布流程提交审核；本仓库已经具备本地 marketplace 结构。

本仓库只提交插件源码和示例配置，不包含任何真实邮箱账号、授权码或本机缓存。真实账号配置会保存在使用者自己的 `~/.china-email/accounts.json`。
