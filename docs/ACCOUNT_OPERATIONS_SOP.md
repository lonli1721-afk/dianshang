# 账号运维 SOP

本文档用于新增账号、修改管理员账号、排查登录失败和回滚账号变更。账号属于生产数据，默认按 R2 数据变更处理：先只读检查，再备份 `auth.db`，再执行变更，最后验证登录和健康状态。

## 1. 硬规则

1. 账号变更只允许修改 `/home/deploy/game-video-data/auth.db`。
2. 变更前必须先备份数据库，不需要重启服务。
3. 不在终端、文档、提交信息里打印真实密码。
4. 新账号默认使用临时密码，并设置首次登录强制改密。
5. 管理员账号至少保留一个 active admin。
6. 如果用户绑定 `169.254.x.x` 这类链路本地 IP，网页登录失败时优先核对真实出口 IP。
7. 账号变更后必须检查 `/health`、服务状态、认证日志和任务审计。

## 2. 当前线上账号数据位置

- 服务器：`deploy@106.53.49.23`
- 代码目录：`/home/deploy/game-video-tool`
- 数据目录：`/home/deploy/game-video-data`
- 认证库：`/home/deploy/game-video-data/auth.db`
- 服务：`game-video-tool.service`
- 健康检查：`http://127.0.0.1:57991/health`

## 3. 只读账号审计

上线或账号变更后，先运行只读审计：

```bash
cd /home/deploy/game-video-tool
GAME_VIDEO_DATA_DIR=/home/deploy/game-video-data .venv/bin/python deploy/auth-account-audit.py
```

如果需要确认指定管理员和指定账号：

```bash
cd /home/deploy/game-video-tool
GAME_VIDEO_DATA_DIR=/home/deploy/game-video-data .venv/bin/python deploy/auth-account-audit.py \
  --expected-admin 'zhise!' \
  --expected-user wujunchao \
  --expected-user jiangjinglei \
  --expected-user hehongjian \
  --expected-user yangnan
```

审计脚本只读打开 `auth.db`，不会验证密码、不会刷新 `last_login`、不会写入任何账号字段。

## 4. 新增账号默认流程

1. 明确账号资料：
   - 用户名
   - 姓名
   - 部门或小组
   - 允许登录 IP
   - 临时密码策略
2. 只读检查用户名是否已经存在。
3. 执行 DB 定向备份：

```bash
cd /home/deploy/game-video-tool
deploy/backup-game-video-dbs.sh
```

4. 通过受控脚本或后端 `auth.upsert_imported_user` 写入账号。
5. 新账号必须是：
   - `role='user'`
   - `is_active=1`
   - `must_change_password=1`
6. 变更后运行只读审计和 `/health`。
7. 让用户网页登录验证；不要用脚本反复验证密码，避免刷新 `last_login` 造成误判。

## 5. 修改管理员用户名

管理员用户名变更前必须确认目标用户名不存在，并确认源账号是 active admin。

变更后必须验证：

1. 新管理员用户名可以登录。
2. 旧管理员用户名不能登录。
3. active admin 数量不少于 1。
4. `/health` 返回 200。

如需修改管理员密码，应单独记录为“密码变更”，不要和“用户名变更”混写。

## 6. 登录失败排查

按以下顺序查：

1. 用户名是否存在、是否 active。
2. `must_change_password` 是否为 1。
3. `allowed_ips` 是否匹配用户真实出口 IP。
4. 浏览器是否还带旧 token，可让用户重新登录或清理登录状态。
5. `app.log` 是否有集中 `401/403/500`。
6. `/health`、服务状态、磁盘是否正常。

常用只读命令：

```bash
curl -sS -i http://127.0.0.1:57991/health | head -20
systemctl is-active game-video-tool.service
tail -160 /home/deploy/game-video-tool/app.log
```

## 7. 回滚

如果账号变更后出现严重登录事故，优先恢复最近一次 DB 定向备份里的 `auth.db`，不要回滚代码目录。

回滚前先保存事故现场：

1. 当前 `auth.db` 文件。
2. 最近 `app.log` 尾部。
3. `/health` 结果。
4. `auth-account-audit.py` 输出。

如果只是单个用户 IP 错误，不需要恢复 DB，直接修正该用户的 `allowed_ips` 并重新审计。

## 8. 本次账号变更记录

2026-05-07 已完成：

1. 管理员用户名从旧默认用户名改为新的管理员用户名。
2. 新增直投组账号：吴军超、蒋菁蕾。
3. 新增产品部账号：贺宏健、杨楠。
4. 变更前后均已做 DB 定向备份。
5. `/health` 返回 200，服务 active。

注意：蒋菁蕾绑定的 `169.254.179.52` 是链路本地 IP。如果网页登录失败，应优先改成真实出口 IP。
