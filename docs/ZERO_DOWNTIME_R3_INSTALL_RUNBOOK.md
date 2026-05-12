# R3 近零停机基础设施安装 Runbook

本 runbook 用于第一次启用近零停机发布。它会改 systemd、nginx 和 sudoers，属于 R3 运维变更。执行前必须得到用户明确允许。

## 当前预检查结论

最近一次只读预检查结果：

- 当前服务健康：`game-video-tool.service` active，`/health` 200。
- 当前 active 端口：`57991`。
- standby 端口：`57992` 空闲。
- 磁盘：约 64%，剩余约 19GB。
- 阻塞点：
  - 线上还没有部署 `zero-downtime-release.py`、systemd 模板、nginx 蓝绿模板和切流脚本。
  - nginx 仍有直接 `127.0.0.1:57991` 代理入口，包括 `/etc/nginx/conf.d/game-video-tool.conf` 和 `/etc/nginx/nginx.conf`。
  - deploy 用户还没有最小 sudoers 授权。

## 安装前备份

必须先备份系统配置：

```bash
ts="$(date +%Y%m%d-%H%M%S)"
mkdir -p /home/deploy/game-video-backups/r3-zero-downtime-$ts
cp -a /etc/nginx/nginx.conf /home/deploy/game-video-backups/r3-zero-downtime-$ts/nginx.conf
cp -a /etc/nginx/conf.d /home/deploy/game-video-backups/r3-zero-downtime-$ts/conf.d
cp -a /etc/systemd/system/game-video-tool.service /home/deploy/game-video-backups/r3-zero-downtime-$ts/game-video-tool.service
```

同时保留 DB 定向备份记录：

```bash
cd /home/deploy/game-video-tool
deploy/backup-game-video-dbs.sh
```

## 安装步骤

以下命令需要 root 权限。

1. 安装发布工具文件到线上代码目录。

   这一步由常规代码发布包完成，只覆盖 `/home/deploy/game-video-tool` 的代码，不覆盖 `.env`、`.venv`、`/home/deploy/game-video-data`。

2. 创建 runtime 目录。

   ```bash
   mkdir -p /home/deploy/game-video-runtime/{logs,releases,slots/57991,slots/57992}
   chown -R deploy:deploy /home/deploy/game-video-runtime
   echo 57991 > /home/deploy/game-video-runtime/active-port
   chown deploy:deploy /home/deploy/game-video-runtime/active-port
   ```

3. 安装 systemd 模板。

   ```bash
   install -o root -g root -m 0644 \
     /home/deploy/game-video-tool/deploy/game-video-tool@.service \
     /etc/systemd/system/game-video-tool@.service
   systemctl daemon-reload
   ```

4. 安装受控切流脚本。

   ```bash
   install -o root -g root -m 0755 \
     /home/deploy/game-video-tool/deploy/game-video-switch-upstream.sh \
     /usr/local/sbin/game-video-switch-upstream
   ```

5. 安装 nginx 蓝绿 upstream include。

   ```bash
   cat > /etc/nginx/conf.d/game-video-tool-upstream.inc <<'EOF'
   set $game_video_backend http://127.0.0.1:57991;
   EOF
   ```

6. 替换 nginx 入口。

   把 `/etc/nginx/conf.d/game-video-tool.conf` 改成蓝绿模板内容，并确认 `/etc/nginx/nginx.conf` 不再包含额外的 `proxy_pass http://127.0.0.1:57991;` server。

   关键要求：

   - 所有入口都必须使用 `proxy_pass $game_video_backend;`
   - 必须保留 `limit_req_zone` 和 `/api/auth/login` 限流。
   - `nginx -t` 必须通过。

7. 安装最小 sudoers。

   使用 `visudo -f /etc/sudoers.d/game-video-zero-downtime` 写入：

   ```text
   Cmnd_Alias GAME_VIDEO_SYSTEMD = \
     /usr/bin/systemctl start game-video-tool@57991.service, \
     /usr/bin/systemctl start game-video-tool@57992.service, \
     /usr/bin/systemctl restart game-video-tool@57991.service, \
     /usr/bin/systemctl restart game-video-tool@57992.service, \
     /usr/bin/systemctl stop game-video-tool@57991.service, \
     /usr/bin/systemctl stop game-video-tool@57992.service

   Cmnd_Alias GAME_VIDEO_SWITCH = \
     /usr/local/sbin/game-video-switch-upstream 57991, \
     /usr/local/sbin/game-video-switch-upstream 57992

   deploy ALL=(root) NOPASSWD: GAME_VIDEO_SYSTEMD, GAME_VIDEO_SWITCH
   ```

## 安装后验证

以 deploy 用户执行：

```bash
cd /home/deploy/game-video-tool
deploy/zero-downtime-infra-preflight.py --json
```

必须满足：

- `success: true`
- `blockers: []`
- `nginx_blue_green_ready` 为 true
- `sudoers_minimal_commands_ready` 为 true
- `standby_port_free` 为 true

## 首次蓝绿演练

首次只做 standby 启动，不切流：

```bash
cd /home/deploy/game-video-tool
deploy/zero-downtime-release.py prepare \
  --package /home/deploy/game-video-tool-<release-id>.tar.gz \
  --release-id <release-id> \
  --execute

deploy/zero-downtime-release.py start-standby \
  --release-id <release-id> \
  --execute

curl -i http://127.0.0.1:57992/health
```

确认 `57992` 健康后，再单独请求允许切流。

## 回滚

如果 nginx 配置异常：

```bash
cp -a /home/deploy/game-video-backups/r3-zero-downtime-$ts/nginx.conf /etc/nginx/nginx.conf
rm -rf /etc/nginx/conf.d
cp -a /home/deploy/game-video-backups/r3-zero-downtime-$ts/conf.d /etc/nginx/conf.d
nginx -t
nginx -s reload
```

如果 systemd 模板异常：

```bash
rm -f /etc/systemd/system/game-video-tool@.service
systemctl daemon-reload
systemctl start game-video-tool.service
```

如果 sudoers 异常：

```bash
rm -f /etc/sudoers.d/game-video-zero-downtime
```

回滚后必须重新确认：

```bash
curl -i http://127.0.0.1:57991/health
curl -i http://106.53.49.23/health
```
