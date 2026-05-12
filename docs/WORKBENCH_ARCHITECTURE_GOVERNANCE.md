# 视频工作台架构治理说明

更新时间：2026-05-04

本文档用于固化 `game-video-tool` 视频工作台当前架构边界。后续 Codex、DeepSeek、Claude 或其他 agent 接手时，先按本文档判断能不能改、怎么拆、怎么验收。

当前稳定治理基线：

- 稳定 worktree：`/private/tmp/game-video-tool-bootstrap-hook`
- 当前线上稳定提交：`830b73c Extract workbench tab persistence hook`
- 主目录 `/Users/jinyu/Documents/game-video-tool` 仍可能存在未跟踪实验文件，不作为发布基线。

## 1. 当前结构定位

`react-ui/src/pages/game/GameVideoPage.jsx` 仍是视频工作台 orchestrator。

它现在的职责是：

- 组合项目、场景、tab、模型、设置等顶层状态。
- 连接业务动作、API 调用、上传、生成、轮询和自动保存。
- 把受控状态和 handler 传给子面板。

它不应该继续承接新的大功能。新增能力必须先判断是否能落到已有组件、hook、helper 或 provider/service 边界中。

当前仍需承认的风险：

- `GameVideoPage.jsx` 仍约 1620 行，仍有较多顶层状态和业务动作。
- `server/routers/game_routes.py` 仍约 1788 行，仍承载多条生产关键链路。
- 继续拆分必须小包推进，不能把前端大拆分和后端大拆分混在一个包里。

## 2. 前端边界规则

`components/` 只做展示和事件转发。

组件允许：

- 渲染 UI。
- 展示状态、列表、按钮、提示、历史记录。
- 调用从父组件传入的回调。

组件禁止：

- 直接调用 `api`。
- 读写 `localStorage` / `sessionStorage` / `writeWorkbenchCache`。
- 启动轮询或定时保存。
- 直接修改项目、场景、任务状态。
- 直接处理费用、provider 调用或数据库语义。

`use*.js` hook 用来承接明确副作用或状态闭环。

当前已拆出的 hook 边界：

- `useGameTaskPolling`：任务状态批量轮询。
- `useSceneAutosave`：场景和 tabState 串行保存、保存状态。
- `useProjectLoader`：打开项目、hydrate、恢复场景和轮询。
- `useProjectActions`：项目列表、新建、删除、重命名。
- `useWorkbenchBootstrap`：模型、图片模型、设置初始化和保存。
- `useWorkbenchTabState`：tabState 组装、解析、恢复。
- `useWorkbenchTabPersistence`：独立图片和视频替换 tabState 的立即保存。
- `useMediaResourceActions`：媒体时长查询、服务端文件删除。
- `useTextInsertionActions`：文本插入和光标恢复。

`gameVideoModelUtils.js`、`gameVideoPageHelpers.js`、`gameVideoConstants.js` 应保持纯规则、纯 helper 或常量，不引入 API 副作用。

## 3. 后续拆分路线

下一阶段优先做前端边界收敛，而不是马上拆后端 router。

推荐顺序：

1. 审查并收敛 `GameVideoPage.jsx` 中仍散落的上传动作。
2. 审查并收敛图片生成、视频生成、视频替换、视频反推动作，但每包只处理一个主题。
3. 将场景操作逐步收敛为更明确的 action 层，避免 `genScenes` / `replScenes` 镜像更新散落。
4. 稳定后再规划后端 router/service 拆分。

后端拆分只进入后续计划，不在当前文档包实施。候选边界：

- projects/settings
- files/media assets
- image generation
- prompt/reverse analysis
- video generation
- replace video
- task status
- model registry/validation

## 4. Agent 使用规则

默认可以使用多个 agent 提高审查质量，但必须分工明确。

推荐模式：

- 架构审查 agent：只读审查边界和长期维护风险。
- 测试审查 agent：只读审查测试矩阵、上线门禁和回滚点。
- 风险排查 agent：只读扫描脏工作区、未跟踪文件、敏感文件和明显冲突。
- 主线程：整合结论、执行最终改动、提交、打包和上线。

硬规则：

- 默认 agent 只读，不修改文件。
- 多个 agent 不得同时修改同一文件。
- worker agent 只有在用户明确要求实施代码时才允许改文件。
- 主线程必须复核 agent 结论，不能把 agent 输出直接当上线结论。

## 5. 发布与备份规则

所有改动先定级，再决定备份和上线。

- R0：文档、提示词、交接材料、纯说明；只需本地提交，不部署生产，不做生产 DB 备份。
- R1：纯前端、样式、只读接口、无数据写入；需要代码备份和回滚点，不做全量数据备份。
- R2：单功能写入、文件输出、费用记录、任务状态；做代码备份和相关 DB/目录范围备份。
- R3：认证、权限、账号、schema、迁移、同步、备份/部署脚本、数据路径、大版本；先检查磁盘，再做生产数据全量备份。

任何级别都必须确认发布包不会覆盖 `/home/deploy/game-video-data`。

代码包上线仍必须保留：

- 测试通过记录。
- 独立提交点。
- 干净发布包。
- 回滚路径。
- 上线后 `/health`、首页、静态资源、日志、provider queue、task audit 检查。
- 15 分钟观察。

R0 文档包不需要生产部署，不需要重启服务，不需要生产 DB 备份。
