# game-video-tool 当前状态、已完成工作与下一步交接说明

更新时间：2026-05-04

本文档用于下一次新对话或新维护者快速接手当前 `game-video-tool` 项目。重点不是追述全部历史，而是明确：

1. 当前线上基线是什么；
2. 最近已经做完并已上线的内容；
3. 现在仍然存在的真实问题；
4. 接下来最值得做的事；
5. 后续排障、开发、发布必须遵守哪些硬边界。

本项目已经上线且多人使用，后续所有动作必须以稳定、可追踪、可回滚、可维护为优先，不能为了赶功能继续堆屎山代码。

## 0. 2026-05-04 稳定治理基线

当前稳定治理基线：

- 稳定 worktree：`/private/tmp/game-video-tool-bootstrap-hook`
- 当前线上稳定提交：`830b73c Extract workbench tab persistence hook`
- 主目录 `/Users/jinyu/Documents/game-video-tool` 仍有未跟踪实验文件，不能作为发布基线。
- 线上按 52 个活跃账号容量继续验收。

最近一轮稳定治理已经完成：

- 前端工作台多个受控面板拆分：生成、替换、图片、反推、设置、生成记录。
- 前端关键 hook 拆分：任务轮询、自动保存、项目加载、项目动作、bootstrap、tabState、tab 持久化、媒体资源、文字插入。
- 后端稳定治理：模型 registry、视频参数校验、任务状态查询限流/去重、provider queue、健康报告、任务审计、磁盘生命周期治理。
- 最新线上包 `830b73c` 已通过 15 分钟观察：`/health 200`、stale processing 为 0、provider/status queue 无堆积、日志 429/503/504/Failed to fetch/traceback 计数为 0。

当前架构判断：

- `GameVideoPage.jsx` 仍是 orchestrator，负责组合状态、业务动作和副作用。
- `components/` 只做展示和事件转发，禁止直接调用 API、缓存、轮询、保存。
- `use*.js` hook 必须有明确职责，不能机械搬代码造成新的散乱。
- `GameVideoPage.jsx` 仍约 1620 行，`server/routers/game_routes.py` 仍约 1788 行，不能贸然大拆。
- 详细边界见 `docs/WORKBENCH_ARCHITECTURE_GOVERNANCE.md`。

下一步优先级：

1. 先固化架构文档和默认流程，统一 R0/R1/R2/R3 备份口径。
2. 再选择一个低风险前端小包继续边界收敛。
3. 后端 router/service 拆分只进入计划，不与前端拆分混在一个上线包里。

---

## 1. 项目概况

`game-video-tool` 是一个游戏视频素材工具，技术栈为：

- 前端：React / Vite
- 后端：FastAPI
- 数据：SQLite + 文件目录

当前主要能力包括：

- 游戏素材项目管理
- 图片生成
- 视频生成
- 视频替换 / 动作模仿
- 视频反推提示词
- 素材上传与引用
- 生成历史管理
- 多人账号登录
- 管理员 / 普通用户权限区分
- 普通用户个人 Key 配置
- 云端同步与数据备份

该项目已经部署上线并有多人使用，不能再以“先能跑再说”的方式继续改。

---

## 2. 当前线上基线

当前生产环境信息：

- 线上地址：`http://106.53.49.23`
- 服务器代码目录：`/home/deploy/game-video-tool`
- 服务器数据目录：`/home/deploy/game-video-data`
- 后端监听：`127.0.0.1:57991`
- 实际服务重启方式：当前通过 kill 监听进程并依赖 `Restart=always` 自动拉起

硬边界：

- 只能覆盖服务器代码目录。
- 绝不能覆盖、删除或手改 `/home/deploy/game-video-data`。
- 发布和回滚都只动代码，不直接动生产数据目录。
- 代码上线必须先本地验证，再按 R0/R1/R2/R3 定级备份，再部署，再验收。
- R0 文档包不部署生产，不需要生产 DB 备份。

当前最新线上前端资源 hash：

- `/assets/index-Dit-b_nI.js`

最近稳定包回滚点：

- 代码备份：`/home/deploy/game-video-backups/game-video-tool-code-before-830b73c-20260504-0303.tar.gz`
- DB 定向备份：`/home/deploy/game-video-backups/game-video-dbs-20260504-0303.tar.gz`
- 前端 dist 备份：`/home/deploy/game-video-backups/830b73c-tab-persistence-hook-20260504-0301`

说明：

- 线上曾出现旧页面缓存问题，用户截图里看到过旧 bundle 界面。
- 当前新界面已生效，`生成视频` 页面应显示：
  - `标准生成`
  - `参考视频生成`
  - `高级视频编辑`

---

## 3. 最近已经完成并已上线的工作

以下内容都已经完成，并且已经部署到线上。

### 3.1 前端稳定性与维护性改进

已完成：

1. 抽离 `GameVideoPage` 任务轮询逻辑

- 文件：`react-ui/src/pages/game/useGameTaskPolling.js`
- 目的：把页面内的任务轮询 `Map/ref/timer` 管理从巨型组件中拆出去

2. 抽离 `GameVideoPage` helper

- 文件：`react-ui/src/pages/game/gameVideoPageHelpers.js`
- 已抽离内容包括：
  - 媒体 URL 处理
  - 媒体标准化
  - 场景默认值
  - 场景标准化
  - tab state 解析
  - scene 序列化
  - 错误消息安全格式化

3. 自动保存失败可见化

- 页面现在会明确显示：
  - 自动保存中
  - 已保存
  - 自动保存失败

4. 上传失败不再静默吞掉

- 场景图上传
- 角色图上传
- 替换参考视频上传
- 参考图上传

这些入口失败时现在会有明确提示，不再出现“以为成功其实没传上去”。

5. 修复自动保存竞态

- 旧逻辑使用单个 `savePendingRef`，会在弱网或频繁编辑下丢掉较新的修改
- 现已改为 token 化的保存状态控制，旧请求回包不会覆盖新一轮保存

6. 修复切项目时的跨项目误保存

- 切换项目时会短暂进入 hydrating 保护期
- 旧项目未完成的保存不会误写到新项目

7. 修复批量生成绕过“参考视频模式模型约束”

- 单场景和批量生成现在共用一套校验
- `reference_video` 模式下，如果模型不支持，就会直接阻止提交

---

### 3.2 “生成视频”第一阶段：参考视频生成模式

需求背景：

- 不一定总是要用参考图生成
- 需要能上传一个参考视频
- 再配合提示词，在保留原动作 / 镜头的基础上改写内容

当前已经落地的方式：

- 没有新加 tab
- 放在 `生成视频` 里，通过显式模式切换实现：
  - `标准生成`
  - `参考视频生成`

当前第一阶段边界：

- 只支持单参考视频
- 只支持单提示词
- 当前仅支持即梦：
  - `Seedance 2.0`
  - `Seedance 2.0 Fast`

当前实现要点：

- 前端场景对象新增 `videoMode`
- 后端 `GenerateVideoRequest` 新增 `reference_video_url`
- `reference_video` 模式仍走 `/api/game/generate_video`
- 即梦生成链路已支持把参考视频作为 `reference_video`

这样做的原因：

- 不污染旧的“视频替换”页
- 不再沿用之前那个含糊的“待替换视频（可选）”逻辑
- 生成页现在是显式模式，不再靠字段隐式判断

---

### 3.3 `generate_video` 任务落库与任务可追踪性补齐

此前真实问题：

- `replace_video` 会落库到 `game_tasks`
- `generate_video` 不会

已完成并上线的修补：

- `generate_video` 现在会像 `replace_video` 一样落库到 `game_tasks`
- 生成任务和替换任务在记录层保持一致
- 后续任务历史、任务轮询、状态回写更完整

同时补了一个关键边界：

- 如果上游 provider 任务已经创建成功，但本地首次写 `game_tasks` 失败
- 现在不会再把整次请求直接报成“整体失败”
- 接口仍会返回 `task_id`
- 同时带上 `task_record_warning`
- 后续轮询时会自动尝试补写任务记录

这套补写逻辑已经同时覆盖：

- `generate_video`
- `replace_video`

额外修复：

- 修正 `vidu` provider 默认模型误吃 `seedance-2.0` 的问题
- 现在 provider / model 不再错配

---

### 3.4 模型错误提示与上游波动可见化

最近线上真实出现过：

- Gemini 图片生成 `504 DEADLINE_EXCEEDED`
- 模型繁忙类错误

已完成并上线的处理：

- 后端 `server/ai_service.py` 增加更明确的人类可读错误
- 前端图片生成和提示词刷新，对 `504 DEADLINE_EXCEEDED` 加了短重试

当前目标不是“假装不失败”，而是：

- 遇到上游 503 / 504 时
- 用户能看到明确原因
- 不再只是含糊的“失败”

---

### 3.5 视频时长限制相关热修

最近线上真实出现并确认的问题：

- 用户在“视频替换”或“参考视频生成”中使用参考视频
- 上游 Seedance 返回：
  - `video duration must be <= 15.2`

已确认的关键事实：

- “能上传”不等于“能通过模型校验”
- 上传接口目前不会按 Seedance 的 15.2 秒限制做强约束
- 模型按文件真实元数据时长校验，不一定等于播放器里肉眼看到的时长

本轮已完成并上线的修补：

1. 后端在替换视频前增加本地参考视频时长预检

- 超过 15.2 秒时，直接返回明确中文错误
- 不再完全依赖上游返回英文参数错误

2. 修复本地文件查找漏洞

此前问题：

- 时长预检只查了公共 `files` 目录
- 漏掉了很多实际上传所在的用户目录：
  - `/home/deploy/game-video-data/users/<uid>/files/...`

影响：

- 某些视频虽然已经上传，但本地预检找不到文件
- 请求仍会被送到上游，再被上游用英文报错打回

现状：

- 本地文件查找已覆盖用户目录
- 用户上传视频的时长预检现在更可靠

3. Seedance 时长超限错误翻译为明确中文

当前如果上游再返回这一类错误，用户看到的会是：

- `参考视频时长过长。Seedance 当前仅支持 15.2 秒以内的参考视频，请先裁剪后重试。`

说明：

- 即便用户“看起来是 11 秒”，如果文件真实元数据超限，模型仍会拒绝
- 这不是单纯前端显示问题，而是播放器显示时长和容器真实时长可能不一致

---

### 3.6 备份脚本修复

已完成：

- 修复 `deploy/backup-game-video-data.sh`
- 备份时排除 SQLite 临时文件：
  - `*.db-wal`
  - `*.db-shm`
  - `*.db-journal`

原因：

- 旧脚本在在线 SQLite 环境下容易因为这些临时文件导致备份失败

注意：

- 服务器上该脚本执行位仍可能不稳定
- 当前更稳的做法是：
  - 用 `bash /home/deploy/game-video-tool/deploy/backup-game-video-data.sh`
  - 或在必要时手工用 `tar` 备份

---

## 4. 当前确认存在的真实问题

这里只列真实问题，不列为了重构而重构的“伪问题”。

### 4.1 上游模型服务仍然存在 503 / 504 / 超时波动

这不是我们本地服务挂掉，而是外部模型服务不稳定。

当前已做：

- 明确提示
- 少量重试

但尚未彻底做完的方向包括：

- 后端对可重试错误做更系统的限次重试
- 更明确的失败分桶与日志统计
- 在任务记录里保存更清晰的失败原因

---

### 4.2 视频上传阶段与模型约束仍然不是完全同一套规则

当前事实：

- 视频可以上传成功
- 但提交给 Seedance 时仍可能因真实时长、格式、容器元数据等原因被拒绝

当前已做：

- 上传后返回真实视频时长
- 旧项目视频可通过 `/api/game/media_info` 补查真实时长
- 参考视频生成、视频替换、视频反推入口会展示真实时长
- Seedance 参考视频超过 15.2 秒时会前置阻止提交

后续仍建议补：

- 展示更明确的“建议裁剪 / 重新编码”提示
- 对 provider 返回的格式类错误继续做中文翻译

---

### 4.3 巨型组件问题还没有根治

当前仍需关注：

- `react-ui/src/pages/game/GameVideoPage.jsx` 仍然很大
- `react-ui/src/pages/SettingsPage.jsx` 仍然很大

当前原则：

- 不为了拆而拆
- 但后续任何新功能都不能继续堆进巨型组件里
- 如果做新的视频编辑模式，必须单独拆模块，不得继续硬塞

---

## 5. 当前已上线、但仍需验收的新功能

### 5.1 第二阶段：高级视频编辑

这是需求里已经提过、并已完成第一版上线的功能：

- 上传 1-3 个视频
- 在提示词里通过 `视频1`、`视频2`、`视频3` 引用
- 做多参考视频编辑 / 移植 / 替换

当前进展：

- 已在本地实现第一版，并已部署到生产
- 放在 `生成视频` 中，作为第三个显式模式：
  - `高级视频编辑`
- 前端最多允许上传 3 个高级参考视频
- 提示词中可以通过 `视频1` / `视频2` 引用
- 高级视频编辑可叠加上方角色参考图 / 场景参考图，并随同视频一起传给 Seedance
- 仍然只支持即梦 `Seedance 2.0 / 2.0 Fast`
- 超过 15.2 秒的视频会在前端和后端双侧拦截

后端实现方向：

- `GenerateVideoRequest` 增加 `advanced_reference_videos`
- 高级视频编辑不走普通 `reference_video` 分支
- 后端会把本地上传视频读取出来，通过火山 Files API 上传为 `file_id`
- 再调用 `server/game_video_service.py` 中的 `edit_video(...)`
- 任务仍落库到 `game_tasks`

后端事实：

- `server/game_video_service.py` 已有 `edit_video(...)` 雏形
- 它依赖 provider 文件 `file_id`
- 本轮本地实现已经补上本地视频 URL 到 provider `file_id` 的桥接
- 本地 smoke test 已验证高级模式走 `upload_bytes -> edit_video`，不会误走普通 `generate_video`

当前仍需完成：

- 线上真实用 1-3 个短视频验收高级编辑效果
- 若真实 provider 返回新参数错误，继续补明确中文提示，不允许静默失败

历史上线验收记录：

- 本地 `compileall server` 通过
- 本地 `eslint GameVideoPage.jsx gameVideoPageHelpers.js` 通过
- 前端 `npm run build` 通过
- 当时生产备份已完成
- 生产服务已重启
- 线上 `/health` 返回 `{"status":"ok"}`
- 线上 `/api/auth/status` 返回 `{"auth_enabled":true}`
- 线上代码和前端 bundle 均确认包含 `advanced_reference_videos` / `高级视频编辑` / `edit_video`

说明：这段是 2026-04 历史验收记录，不代表当前线上基线。当前基线以本文开头的 `830b73c` 稳定治理记录为准。

---

## 6. 当前最值得做的下一步

如果要继续推进，推荐按下面顺序做。

### 第一优先级

继续做线上稳定性收口，而不是加新功能：

- 对最近失败任务按接口类型分桶
- 区分：
  - `generate_image`
  - `generate_video`
  - `replace_video`
- 搞清楚究竟是哪条链路失败最多

目标：

- 不再靠用户零散反馈猜问题
- 而是形成真实的失败画像

---

### 第二优先级

对高级视频编辑做真实业务验收：

- 用 1 个 15.2 秒以内短视频生成
- 用 2 个 15.2 秒以内短视频生成
- 故意上传超限视频，确认前端和后端都能明确阻止
- 如果 provider 返回新错误，补中文可见提示

---

### 第三优先级

补更稳的上游繁忙保护：

- 对 Gemini / 即梦的可重试错误做后端限次重试
- 失败原因统一落到任务记录或可见状态里
- 对用户展示更明确的建议：
  - 稍后重试
  - 切模型
  - 裁剪素材

---

## 7. 当前开发与代码质量原则

后续开发必须遵守：

- 不允许为了赶功能继续堆屎山代码
- 不允许把新能力继续塞进单个超大文件
- 不允许在 async 路由里直接做重型同步 IO、SQLite 扫描、大文件读写等阻塞操作
- 不允许静默吞异常
- 不允许让用户“以为成功其实失败”
- 不允许部署时覆盖 `/home/deploy/game-video-data`
- 所有上线必须先本地验证、再备份、再部署、再验收
- 每次上线必须能说明改了什么、为什么改、怎么回滚

代码要求：

- 模块边界清晰
- 函数职责单一
- 命名直接可读
- 减少重复逻辑
- 对多人并发安全
- 对错误有明确处理
- 对任务和外部模型调用有清晰边界

---

## 8. 当前标准发布流程

每次上线都建议按以下流程走：

1. 检查本地状态

```bash
git status --short
```

2. 修改代码

3. 后端编译检查

```bash
PYTHONPYCACHEPREFIX=/Users/jinyu/Documents/game-video-tool/.pycache .venv/bin/python -m compileall server
```

4. 前端检查

```bash
cd /Users/jinyu/Documents/game-video-tool/react-ui
npm run lint
npm run build
```

5. 如需整包发布，生成发布包

```bash
cd /Users/jinyu/Documents/game-video-tool
./deploy/create-release-package.sh /tmp
```

6. 备份风险分级

上线前先判断本次改动属于 R0/R1/R2/R3，不再默认每次都做生产数据全量备份。

- R0：文档、提示词、交接材料、注释说明；不做生产数据备份。
- R1：纯前端、样式、只读接口、无数据写入；只需要代码提交、发布包和回滚点。
- R2：单功能写入、文件输出、费用记录、任务状态、模型结果缓存；优先备份相关数据库或相关目录。
- R3：认证、权限、账号、数据库结构、数据迁移、同步、备份/部署脚本、数据目录路径、大版本上线；必须做生产数据全量备份。

R3 全量备份优先：

```bash
ssh -o BatchMode=yes deploy@106.53.49.23 'bash /home/deploy/game-video-tool/deploy/backup-game-video-data.sh'
```

若脚本不可执行或异常，且确认必须执行 R3 全量备份，可用手工备份：

```bash
ssh -o BatchMode=yes deploy@106.53.49.23 'ts=$(date +%Y%m%d-%H%M%S); out=/home/deploy/game-video-backups/game-video-data-$ts.tar.gz; tar -C /home/deploy/game-video-data --exclude="*.db-wal" --exclude="*.db-shm" --exclude="*.db-journal" -czf "$out" . && echo "$out"'
```

7. 只覆盖代码目录

- 绝不碰 `/home/deploy/game-video-data`

8. 重启后端

当前实际可用方式：

```bash
ssh -o BatchMode=yes deploy@106.53.49.23 'pid=$(lsof -ti :57991 | head -n 1); if [ -n "$pid" ]; then kill "$pid"; fi'
```

说明：

- 当前环境下是通过 kill 监听进程后自动拉起
- 后续若权限模型变化，需要重新确认正式重启方式

9. 线上验收

至少包括：

- `GET /health`
- `GET /api/auth/status`
- 首页是否加载最新静态资源 hash
- 关键业务接口是否符合预期
- 关键错误提示是否清晰

---

## 9. 回滚原则

- 回滚只回滚代码，不动数据目录
- 回滚前如有必要先再次备份数据
- 优先使用最近一次稳定发布包或最近稳定代码版本
- 回滚后必须重新验收：
  - `/health`
  - `/api/auth/status`
  - 首页资源
  - 关键业务接口
- 不要删除 `/home/deploy/game-video-data`

---

## 10. 给下一位维护者的提醒

当前项目接手时，必须先认清以下事实：

1. 这是已经上线、多人使用的项目，稳定优先。
2. 本轮已经完成：
   - `GameVideoPage` 轮询与 helper 抽离
   - 自动保存失败可见化
   - 上传失败可见化
   - `generate_video` 落库到 `game_tasks`
   - 参考视频生成第一阶段
   - 上游模型 503 / 504 相关错误可见化
   - 视频时长限制相关热修
   - 高级视频编辑第一版上线
3. 当前最值得做的不是继续扩功能，而是继续收口线上真实失败问题。
4. “高级视频编辑”第一版已经上线，但仍需要真实短视频业务验收和错误提示收口。
5. 任何部署都不能碰 `/home/deploy/game-video-data`。
6. 任何功能迭代都不能继续堆进巨型组件，必须保持模块边界清晰。

正确方向不是“继续越堆越多”，而是每次改动都让系统更稳一点、更清晰一点、更容易让下一个人接手。
