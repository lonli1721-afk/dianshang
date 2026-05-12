# 近零停机发布方案

目标：发布时不再停止唯一线上进程后等待 systemd 拉起，而是先启动备用实例，健康检查通过后再把 nginx 流量切过去。

## 为什么需要这套方案

当前线上是单实例：

- nginx 直接代理到 `127.0.0.1:57991`。
- `game-video-tool.service` 只有一个 FastAPI 进程。
- 旧进程收到停止信号后，如果还有模型请求、媒体预览、任务轮询或保存请求未结束，就可能长时间不释放端口。
- 在旧进程停掉、新进程未起来的窗口里，用户会遇到 502、Failed to fetch 或页面空白。

近零停机发布改成：

1. 当前实例继续承接用户流量。
2. 新发布包解压到独立 release 目录。
3. 新 release 合并上一版 `react-ui/dist/assets/*.js` 和 `*.css`，避免已打开旧页面的用户在切流后请求旧 hashed chunk 404。
4. 新实例先在备用端口启动，例如 `57992`。
5. 备用实例通过 `/health` 和首页 smoke。
6. nginx 切到备用端口。
7. 观察通过后再停旧端口实例。

## 目录约定

```text
/home/deploy/game-video-tool                  # 现有稳定代码目录，保留 .venv 与 .env
/home/deploy/game-video-data                  # 生产数据目录，绝不覆盖
/home/deploy/game-video-backups               # 备份目录
/home/deploy/game-video-runtime
  active-port                                  # 当前 nginx 指向的端口
  logs/app-57991.log
  logs/app-57992.log
  releases/<release-id>/game-video-tool        # 解压后的发布版本
  slots/57991/current -> releases/.../game-video-tool
  slots/57992/current -> releases/.../game-video-tool
```

## 一次性基础设施安装

这一步需要 root 权限，属于 R3 运维变更。执行前必须备份当前 nginx 配置和 systemd 配置。
详细步骤见 [`docs/ZERO_DOWNTIME_R3_INSTALL_RUNBOOK.md`](/Users/jinyu/Documents/game-video-tool/docs/ZERO_DOWNTIME_R3_INSTALL_RUNBOOK.md)。

建议安装内容：

1. systemd 模板：`deploy/game-video-tool@.service`
2. nginx 蓝绿模板：`deploy/nginx-game-video-tool-blue-green.conf.example`
3. root 受控切流脚本：`deploy/game-video-switch-upstream.sh`
4. sudoers 最小授权，只允许 deploy 执行以下命令：
   - `systemctl start/restart/stop game-video-tool@57991.service`
   - `systemctl start/restart/stop game-video-tool@57992.service`
   - `/usr/local/sbin/game-video-switch-upstream 57991`
   - `/usr/local/sbin/game-video-switch-upstream 57992`

不要给 deploy 通用 sudo，不要允许任意 nginx 配置写入。

安装 nginx 蓝绿模板时，必须同时检查 `/etc/nginx/nginx.conf` 和 `/etc/nginx/conf.d/*.conf` 里是否还存在直接写死 `127.0.0.1:57991` 的 server。所有线上入口都必须走 `game-video-tool-upstream.inc`，否则会出现部分流量绕过切流、仍打到旧端口的问题。

## 日常发布流程

本地打包后上传到服务器，例如：

```bash
scp /tmp/game-video-tool-<release-id>.tar.gz \
  deploy@106.53.49.23:/home/deploy/game-video-tool-<release-id>.tar.gz
```

线上执行：

```bash
cd /home/deploy/game-video-tool

deploy/zero-downtime-release.py preflight \
  --package /home/deploy/game-video-tool-<release-id>.tar.gz

deploy/backup-game-video-dbs.sh

deploy/zero-downtime-release.py prepare \
  --package /home/deploy/game-video-tool-<release-id>.tar.gz \
  --release-id <release-id> \
  --execute

deploy/zero-downtime-release.py start-standby \
  --release-id <release-id> \
  --execute

deploy/zero-downtime-release.py cutover \
  --standby-port 57992 \
  --execute
```

如果当前 active-port 是 `57992`，脚本会默认选择 `57991` 作为备用端口。

切流后先观察 15 分钟。确认无异常后，再停止旧端口：

```bash
sudo -n systemctl stop game-video-tool@57991.service
```

不要在切流命令里立即停旧端口，除非已经确认没有旧请求且显式使用 `--force-stop-old`。

## 回滚方式

如果切流后健康检查失败，立即切回旧端口：

```bash
sudo -n /usr/local/sbin/game-video-switch-upstream 57991
```

如果旧端口已停止，先启动旧端口：

```bash
sudo -n systemctl start game-video-tool@57991.service
sudo -n /usr/local/sbin/game-video-switch-upstream 57991
```

本方案不默认回滚 DB。只有出现明确数据异常时，才按 DB 定向备份处理。

## 验收标准

切流前：

- 备用端口 `/health` 200。
- 备用端口首页 200。
- `compileall server` 通过。
- 发布包不包含 `.env`、`.git`、`.local-data`、`.venv`、`node_modules`、`._*`。
- 新 release 已保留上一版 `react-ui/dist/assets/*.js` 和 `*.css`，除非是首次启用蓝绿发布且已接受短暂静态资源兼容风险。

切流后：

- 外网 `/health` 200。
- 首页 200。
- 当前 JS/CSS 资源 200。
- provider queue 没有持续 waiting。
- stale processing 不增长。
- 日志无新增 traceback、502、504、Failed to fetch、前端语法错误。

## 当前限制

这套脚本本身不会绕过权限。在线上没有安装 systemd 模板、nginx 蓝绿配置和 sudoers 最小授权前，`zero-downtime-release.py` 只能完成发布包检查和 dry-run 计划，不能真正切流。
