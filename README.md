# 游戏视频素材工具

AI 驱动的游戏视频素材生成工具，支持视频生成、视频换人、AI 提示词分析等功能。

## 功能

- **视频生成** — Seedance 2.0 / VIDU 文生视频、图生视频
- **视频换人** — Seedance 动作模仿 / 万相 Animate-Mix 角色替换
- **AI 提示词** — Gemini / GPT 自动生成和优化视频提示词
- **视频反推** — 从参考视频反向工程生成提示词
- **图像生成** — 角色/场景参考图生成（即梦 Seedream / Gemini）
- **项目管理** — 项目、资产、场景、任务历史

## 技术栈

- **前端**: React 19 + Vite 8 + React Router 7
- **后端**: FastAPI + SQLite
- **桌面端**: Tauri v2（可选）
- **部署**: Docker

## 快速开始

```bash
# 1. 安装后端依赖
cd server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. 安装前端依赖
cd ../react-ui
npm install

# 3. 启动开发服务器
npm run dev          # 前端 http://localhost:5173
cd ../server && python main.py  # 后端 http://localhost:57991
```

## Docker 部署

```bash
cp .env.example .env
# 编辑 .env，设置 JWT_SECRET
docker compose up -d
```

## API Key 配置

在 Web 界面「设置」页面配置以下 API Key：

| 服务 | 用途 | 获取地址 |
|------|------|---------|
| 火山引擎 Ark API Key | Seedance 视频生成 + 即梦图像生成 | ark.cn-beijing.volces.com |
| VIDU API Key | VIDU 视频生成 | api.vidu.com |
| DashScope API Key | 万相视频换人 | dashscope.aliyuncs.com |
| Gemini API Key | AI 提示词 + 图像生成 | aistudio.google.com |
| OpenAI API Key | GPT 视觉分析（可选） | platform.openai.com |

## 协作与发布规范

- [Claude / AI 维护总规则](/Users/jinyu/Documents/game-video-tool/CLAUDE.md)
- [默认执行摘要](/Users/jinyu/Documents/game-video-tool/docs/DEFAULT_EXECUTION_SUMMARY.md)
- [协作流程约定](/Users/jinyu/Documents/game-video-tool/docs/COLLABORATION_WORKFLOW.md)
- [测试、上线与备份策略](/Users/jinyu/Documents/game-video-tool/docs/TESTING_RELEASE_AND_BACKUP_POLICY.md)
- [变更检查清单](/Users/jinyu/Documents/game-video-tool/docs/CHANGE_CHECKLIST.md)
- [发布、回滚与备份 SOP](/Users/jinyu/Documents/game-video-tool/docs/RELEASE_ROLLBACK_AND_BACKUP_SOP.md)
- [发布记录模板 / 上线打钩表](/Users/jinyu/Documents/game-video-tool/docs/RELEASE_RECORD_TEMPLATE.md)
