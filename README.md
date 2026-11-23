# 国内 Codex 插件市场

这个仓库是一个本地 Codex 插件市场。入口文件是：

- `.agents/plugins/marketplace.json`

当前已接入插件：

- `china-email`：国内邮箱插件，支持 QQ 邮箱、网易 163/126/yeah、腾讯企业邮箱、阿里企业邮箱、139 邮箱和自定义 IMAP/SMTP 邮箱。

## 更新到 0.2.0

用 Git 克隆的用户可在仓库目录运行 `git pull`。用 ZIP 安装的用户请从 GitHub 重新下载源码。在 Codex 中打开更新后的目录。如果仍显示旧版本，在插件市场重新安装「国内邮箱」并新建会话。已有邮箱配置可继续使用。

现在可以让 Codex「列出已发送的最近 30 封邮件」，也可以让它继续往前查。若收件箱返回空结果，可让 Codex「检查 INBOX 在 IMAP 服务器上的邮件数量，不加任何筛选，报告读取失败数」。

## 在 Codex 中使用

在 Codex App 中打开这个仓库后，插件市场会读取 `.agents/plugins/marketplace.json`，并展示 `国内插件市场` 下的 `国内邮箱` 插件。

安装后，推荐直接让 Codex 打开本地配置向导：

```text
打开国内邮箱配置向导
```

向导会在本机浏览器打开，用户选择邮箱服务商，填写邮箱地址和授权码，然后点保存即可，不需要手动改 JSON。

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
