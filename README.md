# AI Video Workflow

AI 视频生成工作流平台。基于 **Supabase（Postgres + Storage + Auth + Edge Functions）** 与 **Vue 3**，
视频拼接由浏览器端 **MediaBunny** 完成，**无需 Python 后端，也无需 FFmpeg**。

> 完整部署步骤见 [docs/部署与使用指南.md](docs/部署与使用指南.md)
> 架构改造评估见 [docs/cloudflare-supabase-mediabunny-评估.md](docs/cloudflare-supabase-mediabunny-评估.md)

## 架构

```
Vue 3 前端（可托管 Cloudflare Pages）
  ├─ Supabase Auth         登录 / 用户
  ├─ Supabase Postgres     项目、剧本、分镜、任务、模型配置
  ├─ Supabase Storage      图片 / 视频资产（media 桶）
  └─ MediaBunny            浏览器端视频拼接（替代 FFmpeg）
        ↓ AI 调用走 Edge Function
  ai-text / ai-script / ai-image / ai-video-submit / ai-video-poll
  model-test / admin-users
```

## 目录结构

```
ai_video/
├─ frontend/          Vue 3 前端（唯一运行时）
│  └─ src/lib/
│     ├─ supabase.ts  Supabase 客户端与 Edge Function 调用封装
│     └─ mediabunny.ts 视频拼接（直通封装）
├─ supabase/
│  ├─ migrations/     数据库表结构 + RLS + 定时轮询
│  ├─ functions/      Edge Functions（含 _shared 公共网关逻辑）
│  └─ config.toml
├─ backend/           旧 Python 后端（已废弃，仅作逻辑参考，可删）
└─ docs/              部署指南与改造评估
```

## 功能

- 登录鉴权（Supabase Auth，邮箱 + 密码，管理员 / 普通用户两级）
- **权限模型**：所有资源（项目 / 文件 / 提示词 / 模型 / 密钥 / 剧本 / 任务…）一律按用户隔离，
  不共享；管理员仅额外拥有「用户管理」权限
- 项目管理、文件与资产库（图片 / 视频上传、预览、重命名、删除）
- 密钥管理：模型 API Key 加密存于数据库、按用户隔离，页面只显示掩码，明文不回传前端
- 模型配置：文本 / 图片 / 视频三类，支持 OpenAI 兼容、AutoDL ComfyUI、MiniMax、火山 Ark，
  密钥下拉选择，可在页面测试连接（**按用户隔离**，看不到别人的模型）
- 提示词管理 + AI 生成（角色三视图 / 场景概念图）
- 角色 / 场景管理（跨镜头主体一致性）
- 剧本 + 六段分镜（固定 60 秒 × 6 段，AI 生成或手动编辑）
- 图片生成、视频生成（异步任务 + 定时轮询推进）
- 视频合成：浏览器端拼接，支持排序，产物自动入库

## 快速开始

```bash
# 1. 初始化 Supabase（按 001 → 003 → 004 → 005 → 002 顺序执行 migrations 下 5 个 SQL）
# 2. 部署 Edge Functions
cd D:/ai_video
supabase link --project-ref <your-ref>
supabase functions deploy ai-text   # ...其余见部署指南
supabase secrets set CRON_SECRET=<random-string>

# 3. 启动前端
cd frontend
# 编辑 src/lib/config.ts，填入 Supabase URL 与 anon key（不用环境变量）
npm install
npm run dev             # http://127.0.0.1:5173
```

> 模型 API Key 无需写进环境变量，登录后在系统「密钥管理」页面添加即可。
> 项目地址与轮询密钥存在数据库 `app_config` 表中，不要使用
> `alter database set app.settings.*`（托管平台会拒绝）。

详细步骤（含创建管理员、配置定时轮询、部署 Cloudflare Pages）请见
[docs/部署与使用指南.md](docs/部署与使用指南.md)。

## 环境基线

- 前端：Node.js 20+ / npm
- 后端：Supabase 托管（无需本地运行时）
- 视频处理：浏览器端 MediaBunny（需支持 WebCodecs 的现代浏览器）
