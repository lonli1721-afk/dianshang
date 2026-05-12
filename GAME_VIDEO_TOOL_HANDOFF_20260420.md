# game-video-tool 交接与部署（B+C 方案）

更新时间：2026-04-20  
线上地址：`http://106.53.49.23`  
本地代码：`D:\Codex-Kit\game-video-tool`  
本地交接目录：`D:\fwq`  
服务器代码目录：`/home/deploy/game-video-tool`  
服务器数据目录：`/home/deploy/game-video-data`（重要：不要覆盖/删除）

> 安全提醒：不要在本文档里保存 deploy/root 密码、JWT_SECRET、任何 API Key、云端 token 等敏感信息。

---

## 当前线上状态（已自检）

- **服务存活**：`nginx`、`game-video-tool` 均为 active（systemd）。
- **前端资源 hash**（用于确认已发布版本）：
  - JS：`/assets/index-CAj1_GF5.js`
  - CSS：`/assets/index-DFWThQmO.css`
- **健康检查**：`GET /health` 返回 200。

---

## 本轮关键完成项（高优先级变更汇总）

### 1) 性能与稳定性（解决“全站变慢/模型等待久”）

- **根因**：`/api/auth/login` 在错误配置下会回连自身（cloud_url 指向自己）导致递归登录；叠加 bcrypt 校验，出现单核 100% CPU，进而把全站 TTFB 拉到数秒。
- **修复**：
  - 阻断“cloud_url 指向本机时回连自身登录”的递归链路。
  - 登录鉴权的 bcrypt/sqlite 迁移到线程池执行，避免阻塞事件循环。
  - 复用 `httpx.AsyncClient`（连接池），减少重复创建 SSL context 的开销。
- **防护**：Nginx 对 `location = /api/auth/login` 增加限流（防撞库拖垮服务）。

### 2) 用量统计与权限

- 普通用户：`/api/account/usage?days=7`（最近 7 天）
- 管理员：`/api/admin/usage?days=7`（最近 7 天，全用户）
- 普通用户不能读写系统设置 `/api/settings`（403 是预期）
- 普通用户可设置自己的游戏工具 Key：`/api/game/settings`（按用户隔离）
- 游戏工具 Key 优先级：用户 `game_*` > 系统 key > 缺 key 提示

### 3) 云端同步（真实上传 + 自动备份可观测）

- 生成媒体文件（图片/视频/音频/上传文件）保存后会触发同步队列。
- 数据库按间隔推送到云端，并在本机做周期性备份。
- 同步状态 UI 展示：上传文件数、等待队列、数据库推送次数、最近成功/失败信息等。

### 4) UI/UX 修复与优化

- 修复 React 条件渲染导致页面出现“0”的问题。
- 云同步面板按截图重做样式与文案，明确“系统级配置”。
- 视频反推按钮/生成视频按钮：禁用态不再发白，文字可读；生成视频按钮样式与主题按钮统一（更明显）。

---

## 打包产物（本地）

已生成全量代码包（不包含 node_modules / __pycache__ 等）：

- `D:\fwq\game-video-tool-full-20260420-2056.tar.gz`

说明：
- 包内包含 `react-ui/dist`（已构建的前端产物）。
- 包内包含后端源码与脚本。

---

## 部署方式（B + C）

目标：以后换电脑/换人/换 AI 都能稳定部署，不依赖复杂命令行引号。

### B：本地打包（Windows）

1) 构建前端（如本次改动涉及前端）

```powershell
cd D:\Codex-Kit\game-video-tool\react-ui
npm run build
```

2) 在本地打 tar.gz（推荐排除缓存目录）

```powershell
$ts = Get-Date -Format "yyyyMMdd-HHmm"
$out = "D:\fwq\game-video-tool-$ts.tar.gz"
cd D:\Codex-Kit
tar -czf $out `
  --exclude="game-video-tool/.tmp-data" `
  --exclude="game-video-tool/react-ui/node_modules" `
  --exclude="game-video-tool/**/__pycache__" `
  game-video-tool
```

> 建议：每次发包都保留一个带时间戳的文件名，便于回滚。

### C：服务器一键发布（上传 → 解压覆盖 → 重启 → 验收）

本地已有辅助脚本（避免 PowerShell 引号灾难）：

- `D:\fwq\run_scp_deploy.cmd`：上传文件到服务器
- `D:\fwq\run_ssh_deploy.cmd`：执行服务器命令
- `/home/deploy/remote_restart_game_video_tool.sh`：重启服务（注意：此脚本可能包含临时密码/交互方案，交接时需替换为更安全方式）

1) 上传 tar.gz 到服务器

```cmd
D:\fwq\run_scp_deploy.cmd D:\fwq\game-video-tool-YYYYMMDD-HHMM.tar.gz /home/deploy/game-video-tool-YYYYMMDD-HHMM.tar.gz
```

2) 服务器解压覆盖 + 重启（推荐在 `/home/deploy` 下操作）

```cmd
D:\fwq\run_ssh_deploy.cmd "cd /home/deploy; tar -xzf game-video-tool-YYYYMMDD-HHMM.tar.gz; bash /home/deploy/remote_restart_game_video_tool.sh"
```

3) 验收（本地跑 curl）

```powershell
curl.exe -sS -o NUL -w "code:%{http_code} ttfb:%{time_starttransfer} total:%{time_total}`n" http://106.53.49.23/health
curl.exe -sS http://106.53.49.23/ | findstr /i "assets/index-"
```

---

## 回滚策略（推荐）

原则：**回滚只回滚代码，不动数据**（`/home/deploy/game-video-data`）。

1) 选择一个历史 tar.gz（你本地 `D:\fwq` 已保留多个）
2) 重复 C 流程：上传该 tar.gz → 解压覆盖 → 重启
3) 按验收检查确认恢复

---

## 后续建议（如果要继续提升“多人并发稳定性”）

- **请求级隔离**：当前后端会根据 token 切换 db 路径/文件目录，但仍有全局状态风险；高并发时需改为更严格的请求级隔离。
- **worker 数量**：如有长任务/高并发，可考虑 uvicorn 多 worker（配合 Nginx）。
- **清理机制**：删除历史/项目时，如果需要真正释放磁盘，需补充“删除文件”链路。

