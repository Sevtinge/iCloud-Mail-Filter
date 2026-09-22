# iCloud Mail Filter

这是一个通过 iCloud IMAP 定时扫描并移动邮件的 Docker 服务。

## 使用

1. 将 `.env.example` 复制为 `.env`。
2. 填写 iCloud 邮箱地址和 Apple **应用专用密码**（不是 Apple ID 登录密码）。
3. 根据需要修改筛选条件和目标文件夹。
4. 启动：

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f
```

## 筛选规则

- `MATCH_TEXT`：在主题、纯文本正文或 HTML 正文中进行不区分大小写的包含匹配。
- `MATCH_FROM`：在发件人的完整 `From` 头、显示名或邮箱地址中进行不区分大小写的包含匹配。
- `MATCH_FROM=null`（或留空）表示不按发件人筛选；也接受别名 `MATCH_SENDER`。
- `MATCH_TEXT=null`（或留空）表示不按正文/主题筛选。两个条件都为 `null` 时会移动所有候选邮件，请谨慎使用。
- 两个条件同时启用时，必须同时满足（AND）才会移动邮件。

首次运行只扫描最近 `FIRST_RUN_HOURS` 小时的邮件；之后只扫描未读邮件。每次最多处理 `MAX_PER_RUN` 封。

## 可用性注意事项

- iCloud IMAP 服务器为 `imap.mail.me.com:993`，容器需要能够访问外网。
- `.env` 含有邮箱凭据，已被 `.gitignore` 排除，不要提交到代码仓库。如果该凭据曾经公开，请立即在 Apple 账户中撤销并重新生成应用专用密码。
- `data/state.json` 用于记录是否完成首次扫描，删除 `data/` 后会重新执行首次扫描。
