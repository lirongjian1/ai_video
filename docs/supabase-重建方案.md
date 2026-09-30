# Supabase + MediaBunny 重建方案（V2）

> 目标：退役 Python/FastAPI 后端，用 Supabase(Postgres + Storage + Auth + Edge Functions) + 前端 MediaBunny 重建一版**功能大致一致**的版本。
> 部署形态：前端静态站（可上 Cloudflare Pages）+ Supabase 全托管后端。

---

## 一、技术选型落定

| 原方案 | 新方案 | 说明 |
|---|---|---|
| MySQL 8 | **Supabase Postgres** | 表结构重写；`JSON`/`LONGTEXT` → `jsonb`/`text` |
| SQLAlchemy ORM + Alembic | **SQL Migration**（Supabase CLI） | 迁移文件落 `supabase/migrations/` |
| 自研 JWT + BCrypt | **Supabase Auth** | 删掉 bcrypt / PyJWT 依赖与登录接口 |
| 本地 `storage/` 磁盘 | **Supabase Storage**（bucket: `media`） | 前端直传直读，RLS 控制写权限 |
| FastAPI 路由 | **supabase-js 直连** + **Edge Function** | CRUD 直连；AI 调用走 Function |
| BackgroundTasks | **Edge Function 异步 + 轮询表** | 任务状态落 Postgres，前端轮询 |
| **FFmpeg 子进程** | **MediaBunny（浏览器端）** | 拼接逻辑整体搬到前端 |
| Key 对称加密入库 | **Edge Function Secrets** | 更安全，不再入库 |

---

## 二、数据模型（Postgres）

沿用原有实体，字段名保持 snake_case 以降低前端改动。

```
profiles          用户档案（关联 auth.users，存 username/role/status）
projects          项目
files             文件/资产（storage_path 改为存储桶相对路径）
prompts           提示词
characters        角色
scenes            场景
scripts           剧本
storyboards       分镜
model_configs     模型配置（api_key 不再入库，仅存引用名）
tasks             任务（含 result_payload / request_payload jsonb）
```

**关键改动**
- `files.url` → 由前端用 `storage.from('media').getPublicUrl()` 现算，不入库
- `model_configs.api_key_encrypted` → 删除，改为 `secret_ref`（指向 Edge Function Secret 名）
- `tasks` 增加 `provider_task_id` / `provider_status` 独立列（原塞在 jsonb 里，便于轮询查询）
- 所有表启用 **RLS**：默认「登录用户可读写自己 project 下的数据」；`profiles.role='admin'` 放开管理权限

---

## 三、功能映射表

| 原功能 | 新实现 | 位置 |
|---|---|---|
| 登录/登出 | `supabase.auth.signInWithPassword` | 前端 |
| 用户管理（增删改查） | Auth Admin API + `profiles` 表 | Edge Function `admin-users` |
| 项目 CRUD | supabase-js `.from('projects')` | 前端直连 |
| 文件上传 | `.storage.from('media').upload()` | 前端直传 |
| 文件/资产列表 | `.from('files').select()` | 前端直连 |
| 模型配置 CRUD | `.from('model_configs')` | 前端直连 |
| 模型连接测试 | Edge Function `model-test` | Function |
| 提示词 CRUD | 前端直连 | 前端 |
| 提示词 AI 生成（三视图/场景） | Edge Function `ai-text`（内置 system prompt） | Function |
| 角色/场景 CRUD | 前端直连 | 前端 |
| 剧本 AI 生成（6 段分镜） | Edge Function `ai-script`（含 JSON 校验 + 批量写 storyboards） | Function |
| 图片生成 | Edge Function `ai-image`（官方同构的中文→英文翻译逻辑） | Function |
| 视频生成 | Edge Function `ai-video-submit` + `ai-video-poll`（拆分解决时限） | Function ×2 |
| 任务列表/取消/删除 | 前端直连 `tasks` 表 | 前端 |
| **视频合成** | **MediaBunny 前端拼接，直接产出 Blob 并上传 Storage** | 前端 |
| FFmpeg 能力检测 | **删除**（不再需要） | — |

---

## 四、Edge Function 清单

| Function | 职责 | 触发 |
|---|---|---|
| `ai-text` | 提示词生成、中文→英文翻译、视频提示词整理 | 前端调用 |
| `ai-script` | 生成 6 段分镜 JSON，校验后写库 | 前端调用 |
| `ai-image` | 调图片模型，产物写 Storage + `files` 表 | 前端调用 |
| `ai-video-submit` | 提交视频任务，存 provider_task_id，立即返回 | 前端调用 |
| `ai-video-poll` | 轮询厂商状态，成功则下载落 Storage、更新任务 | 定时/Cron |
| `admin-users` | 用户增删改（需 service_role） | 前端调用 |
| `model-test` | 代理连接测试，避免把 Key 暴露给前端 | 前端调用 |

> 所有涉及外部厂商 Key 的调用一律在 Function 内完成，密钥放 **Secrets**，前端永不可见。

---

## 五、目录结构（新增部分）

```
ai_video/
├─ supabase/
│  ├─ migrations/        表结构 + RLS 策略
│  ├─ functions/
│  │  ├─ ai-text/
│  │  ├─ ai-script/
│  │  ├─ ai-image/
│  │  ├─ ai-video-submit/
│  │  ├─ ai-video-poll/
│  │  ├─ admin-users/
│  │  └─ model-test/
│  └─ config.toml
├─ frontend/
│  ├─ src/lib/supabase.ts        新增：客户端
│  ├─ src/lib/mediabunny.ts      新增：视频拼接
│  ├─ src/api/*.ts               重写：改为 supabase-js
│  └─ src/views/VideoMergeView.vue  重写：走 MediaBunny
└─ (backend/ 保留不动，退役参考；不删)
```

---

## 六、实施顺序

1. **建 Supabase 骨架**：migrations（表 + RLS）+ config
2. **前端接入层**：`lib/supabase.ts` + 重写 `api/http.ts` 为业务 API 模块
3. **CRUD 模块切换**：项目 / 文件 / 资产库 / 提示词 / 角色 / 场景 / 模型配置 / 任务
4. **Edge Functions**：ai-text → ai-script → ai-image → model-test → ai-video
5. **MediaBunny 视频合成**：替换 `VideoMergeView`
6. **鉴权切换**：Supabase Auth 替换自研登录
7. **清理**：移除 FFmpeg 能力检测、bcrypt 相关前端逻辑

---

## 七、需要你确认的点

1. **后端是否保留**：建议 `backend/` 原地保留作为逻辑参考，不删（不影响部署）。
2. **是否已有 Supabase 项目**：需要 `SUPABASE_URL` / `anon key` / `service_role key` 才能实际联调；没有的话我先把代码与 migration 写完，你建好项目后填 `frontend/src/lib/config.ts` 即可。
3. **视频生成厂商**：是否仍以 AutoDL ComfyUI / MiniMax 为主？Edge Function 里我按这两个协议实现，其他厂商留通用配置位。
4. **角色权限**：是否保留「管理员 / 普通用户」二级权限模型？
