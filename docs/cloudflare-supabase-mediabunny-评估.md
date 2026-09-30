# AI Video Workflow — 功能清单与「Cloudflare + Supabase + MediaBunny」改造可行性评估

> 评估日期：2026-09-30
> 结论摘要：**可行，但不是「加配置就上线」，而是「架构重写」。**
> MediaBunny 替代 FFmpeg —— 可行且推荐；Cloudflare 跑当前 Python 后端 —— 不可行，需整体退役；Supabase 能否替代 —— 取决于一个关键能力：Edge Function 调用视频模型。

---

## 一、项目现有功能清单

技术栈：FastAPI + SQLAlchemy 2.0 + Alembic + MySQL 8 ｜ Vue3 + Element Plus + Vite ｜ FFmpeg 子进程 ｜ 本地磁盘存储

### 1. 账号与权限
- JWT 登录（access token），BCrypt 密码哈希
- 用户管理（列表 / 增删改），默认管理员 `admin` / `admin123`
- 接口级鉴权依赖注入（`CurrentUser`）

### 2. 项目（Project）
- 项目 CRUD、分页、关键字段；所有资产（提示词/图片/分镜/任务）归属项目

### 3. 文件与资产库
- 本地上传（图片 / 视频，默认上限 500MB），落盘 `storage/`
- 文件列表、筛选（IMAGE / VIDEO）、删除
- 图片库、视频库（AI 生成产物 + 手动上传 + 合成产物统一管理）
- 静态资源通过 `/storage/{path}` 对外提供

### 4. 模型配置（核心抽象层）
- 分别配置 **文本 / 图片 / 视频** 三类模型：base_url、model_name、api_key、扩展参数 JSON
- API Key 用 `SECRET_KEY` 做对称加密入库，接口只回掩码
- 连接测试（文本/图片走 OpenAI 兼容 `/models`；视频走厂商校验协议）
- 默认模型标记（同类唯一）
- 协议适配：
  - OpenAI 兼容（文本 `chat/completions`、图片 `images/generations`）
  - **AutoDL ComfyUI 异步工作流**（提交 + `/result/{task_id}` 轮询）
  - **MiniMax 海螺**（视频生成 + `/query/video_generation` + `/files/retrieve`）
  - 通用自定义 submit/status path

### 5. 提示词（Prompt）
- 手动维护 + AI 生成
- 两种生成器：**角色三视图**（定妆模型表）、**场景概念图**
- 内置完整 system prompt（含主体一致性、年龄约束、正向友善措辞等护栏）

### 6. 创意实体
- **角色（Character）** CRUD：关联参考图、提示词、项目
- **场景（Scene）** CRUD：同上
- 两者供分镜引用，保证跨镜头主体一致

### 7. 剧本与分镜
- **剧本（Script）** CRUD；AI 生成总时长 60s、**固定 6 段 × 10s** 的分镜
- 强制 JSON 结构校验（`shots` 必须正好 6 项）
- **分镜（Storyboard）**：序号、标题、画面描述、机位运镜、台词、video_prompt、角色关联、参考图关联
- 分镜手动增删改

### 8. 生成任务流水线
- **图片生成任务**：提示词 →（中文自动翻译成英文）→ 图片模型 → 产物入图片库
- **视频生成任务**：分镜 →（中文整理/参考图指令注入）→ 视频模型异步轮询（进度回写）→ 产物入视频库
- 任务队列：状态（PENDING/RUNNING/SUCCESS/FAILED/CANCELLED）、进度、错误信息、取消、清理
- 参考图最多 9 张、格式校验、ComfyUI no_pic 工作流冲突检测
- 中文提示词自动翻译（依赖一个可用的文本模型）

### 9. 视频合成
- 选 ≥2 个视频，手工排序 → **FFmpeg concat demuxer `-c copy`** 无损拼接 → 产物入视频库
- FFmpeg 可用性检测（`/tasks/capabilities`）

### 10. 前端
- 11 个视图：登录、工作台、项目、用户、模型配置、提示词、创意实体、剧本、任务、文件、资产库、视频合成
- Pinia 状态（auth / tabs / tasks）、Tabs 布局、进度轮询

---

## 二、三个改造目标的可行性判定

| 目标 | 判定 | 说明 |
|---|---|---|
| **MediaBunny 替代 FFmpeg** | ✅ 可行，推荐 | 纯浏览器端 TS 库，无需服务端二进制，天然适配 Serverless |
| **Supabase 替代 MySQL + 本地存储** | ⚠️ 基本可行，有 1 个卡点 | 数据/存储/鉴权都能替；**但后台调用视频模型需要 Edge Function（Deno）** |
| **Cloudflare 部署** | ❌ 跑不了当前后端 | Workers 无法运行本项目的 Python 依赖与本地磁盘逻辑；正确形态是**承载前端静态站** |

### 关键结论 1：Cloudflare Workers 跑不了这个 Python 后端
经查证，Cloudflare Python Workers 已于 2026-09 GA，**确实能跑 FastAPI**——但运行在 Pyodide（WASM）里，**只支持纯 Python 或已编译成 WASM 的包**。本项目依赖中招的：

- `PyMySQL` — pure Python 尚可，但 MySQL 是长连接，Hyperdrive 只面向 TCP 驱动，且 Worker 有 CPU/时长限制
- `bcrypt` — C 扩展，无 PyEmscripten wheel → **直接不可用**
- `cryptography` — Rust 扩展 → 看是否有 WASM wheel
- 本地磁盘 `storage/` + `subprocess(ffmpeg)` → Workers 无文件系统、无子进程
- **后台长轮询视频任务**（900s 超时）→ 远超 Worker 执行时限

**所以：不是「迁移」，而是「把 Business Logic 挪到 Supabase」然后让 Python 后端退役。**

### 关键结论 2：MediaBunny 是这次改造里最顺的一环
- 纯 TS、零依赖、浏览器原生，`npm install mediabunny` 即用
- 能**读** MP4/WebM/MOV/MKV/HLS 等，能**写** MP4/WebM 等
- 支持 `UrlSource`（远程 HTTP，走 Range 请求 + 智能预取）与 `BlobSource`
- 提供 `Conversion` API，可做 transmux / transcode / trim / resize
- 拼接的实现方式：用 `Input` 逐个读源文件 → 用 `Output` + `Mp4OutputFormat` + `BufferTarget` 写出 → 手动按顺序追加各源的 packets/tracks
  （注意：MediaBunny **没有现成的「concat」一行式 API**，需要自行按 track 顺序写入，但这是官方支持的常规用法，社区有示例）

**代价**：拼接从「后端无损 `-c copy`」变成「浏览器端重新封装/必要时重编码」。
- 若源编码一致 → 走 transmux，几乎无损、快
- 若编码不一致 → 需 decode+encode，耗时且吃 CPU（WebCodecs 硬件加速能缓解）
- 需要浏览器支持 WebCodecs（现代 Chrome/Edge 均可；Safari 支持较晚，需实测）

### 关键结论 3：Supabase 的卡点
- **数据库**：Postgres，替代 MySQL 无痛；`init_mysql.sql` / Alembic 迁移要重写为 Postgres DDL / SQL migration
- **存储**：Storage Buckets 替代 `storage/` 磁盘；公开读 + RLS 写策略；文件 URL 换成 Storage 公网 URL（MediaBunny 的 `UrlSource` 正好适用）
- **鉴权**：Supabase Auth 替代自研 JWT + BCrypt，**可以彻底删掉 bcrypt / PyJWT 依赖**
- **⚠️ 卡点**：图片/视频生成这类「后台异步任务」（含厂商轮询 900s）需要 **Supabase Edge Function（Deno Runtime）**。Deno 下 `fetch` 可用、纯 TS 可写，但：
  - Edge Function 也有执行时限，长轮询要拆成「提交 + 定时轮询（pg_cron / 定时触发）」两段
  - 视频下载落 Storage 需要在 Function 里做流式转发
  - 密钥（各厂商 API Key）从「数据库加密存储」改为 **Edge Function Secrets**

---

## 三、目标架构（改造后）

```
┌─────────────────────────────────────────────┐
│  Cloudflare Pages（前端静态站）              │
│  Vue3 + Vite + MediaBunny                    │
│  ↓ 直接读写                                    │
│  ├─ Supabase Auth     （登录/用户）           │
│  ├─ Supabase Postgres （项目/剧本/分镜/任务）  │
│  ├─ Supabase Storage  （图片/视频资产）        │
│  └─ MediaBunny        （视频拼接，浏览器内）   │
└─────────────────────────────────────────────┘
                 ↓ 仅「调用外部 AI 模型」时
┌─────────────────────────────────────────────┐
│  Supabase Edge Function（Deno）              │
│  - 文本/图片/视频模型调用                     │
│  - 厂商异步任务提交 + 轮询状态机               │
│  - Secrets 管理各厂商 Key                     │
└─────────────────────────────────────────────┘
```

**Python 后端（FastAPI/Alembic/uvicorn）整体退役。**

---

## 四、改造工作量分级

| 模块 | 改造动作 | 工作量 |
|---|---|---|
| 视频合成 | 删后端 `video_merge.py`；前端引入 MediaBunny 实现拼接；去掉 FFmpeg 能力检测 | **小** |
| 鉴权 | 换 Supabase Auth；删 JWT/BCrypt/登录接口 | 中 |
| 数据层 | 所有 API 调用改为 `supabase-js`；表结构迁 Postgres | **大** |
| 文件存储 | 上传/下载改 Storage SDK；URL 换 Storage 公网地址 | 中 |
| AI 模型网关 | 全部逻辑（含中文翻译、参考图注入、ComfyUI/MiniMax 适配）迁到 Edge Function | **大** |
| 异步任务 | BackgroundTasks → Edge Function + 定时轮询；任务状态表改 Postgres 并发写 | **大** |
| 前端 | `http.ts` 全量重写为 supabase client；11 个视图的接口调用改写 | **大** |

---

## 五、风险与建议

### 风险
1. **视频拼接体验变化**：浏览器端拼接吃客户端 CPU，源编码不一致时慢；移动端浏览器风险更高
2. **Edge Function 时限**：视频生成轮询最长 900s，必须拆解为「提交 + 定时轮询」
3. **成本结构变化**：Supabase 免费额度（DB 500MB / Storage 1GB / Edge Function 调用数）对视频项目偏紧，视频文件很快超限
4. **安全模型重构**：从「后端统一鉴权」变成「RLS 行级安全 + 前端直连」，策略写错会越权
5. **一次性重写风险**：这不是渐进式重构，是近乎重写，回归测试成本高

### 建议路线（若要推进）
1. **先做孤立的「MediaBunny 拼接」原型**：不动架构，单独验证浏览器端能否可靠拼接你的真实视频样本（重点是编码一致性）。这一步能最快证伪/证实核心假设
2. **再搭 Supabase 骨架**：Auth + Postgres 表 + Storage，把「项目/文件/资产库」这三个 CRUD 模块先切过去（不涉及 AI 调用，风险最低）
3. **然后迁 AI 网关**：把 `ai_gateway.py` 翻译成 Edge Function，先只做「同步的文本/图片生成」，视频异步任务最后做
4. **最后退役 Python 后端**

### 有更省力的替代方案吗？
有，值得一并权衡：
- **只换前半段**：前端上 Cloudflare Pages + Supabase（数据/存储/鉴权），但 AI 调用仍保留一个**轻量 Python/Node 服务**（可部署在同配置的容器平台）。这样 MediaBunny 省掉 FFmpeg，但不必把整个 FastAPI 塞进 Edge Function 的时限里
- **只换 FFmpeg**：如果目标仅是「去掉本地 FFmpeg 依赖」，其实**不必动 Cloudflare/Supabase**——直接在前端加 MediaBunny 替换 `VideoMergeView` 的合成逻辑即可，改动量最小

---

## 六、一句话总结

- **MediaBunny 替代 FFmpeg**：可行，推荐，改动小，但拼接从「无损 copy」变「浏览器端重封装」。
- **Cloudflare 部署**：跑不了现有 Python 后端；只能承载前端静态站。
- **Supabase**：能替代数据库/存储/鉴权，但 AI 异步任务必须靠 Edge Function + 定时轮询重写。
- **整体**：这是一次**架构重写（Serverless 化）**，不是配置改造。建议先做 MediaBunny 单点原型验证，再决定是否全量推进。
