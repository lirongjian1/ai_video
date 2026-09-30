# AI Video Workflow

本地运行的 AI 视频生成工作流平台。当前版本提供登录、用户、项目、文件、AI 提示词、AI 图片、六段分镜、视频生成任务、模型配置、图片/视频资产库和本地视频合成。

## 环境基线

- 后端：Conda `base_test`，Python 3.10.x
- 前端：本机现有 Node.js 20+ 与 npm
- 数据库：MySQL 8.x
- 视频处理：FFmpeg

禁止在项目内创建虚拟环境或新增 Conda / Node 版本。

## 启动后端

1. 按需修改根目录 `.env`，特别是 MySQL 用户名和密码。
2. 新数据库可直接导入 `database/init_mysql.sql`，它会创建数据库、全部工作流表和默认管理员。
3. 激活环境并进入后端目录：

```powershell
conda activate base_test
cd backend
```

4. 如果没有导入初始化 SQL，执行迁移：

```powershell
python -m alembic upgrade head
```

5. 启动后端：

```powershell
python -m uvicorn app.main:app --reload --port 8010
```

SQL 导入与 Alembic 迁移是两种初始化方式，首次部署选择一种即可。已有数据库升级统一执行 `python -m alembic upgrade head`。项目默认关闭运行时自动建表，数据库结构以迁移版本为准。

接口文档地址：`http://127.0.0.1:8010/docs`

## 启动前端

进入 `frontend` 目录后执行 `npm install` 和 `npm run dev`，访问 `http://127.0.0.1:5173`。

默认账号：`admin` / `admin123`。首次启动后端时会自动创建该账号，密码以 BCrypt 哈希保存。

## 第二阶段功能

- 模型管理：分别配置文本、图片、视频模型的接口地址、模型名和 Key，并可直接测试连接。Key 使用项目 `SECRET_KEY` 加密后存入 MySQL，接口只返回掩码。
- 提示词：既可手动维护，也可输入关键内容，由文本模型生成主体定妆三视图或场景概念图提示词。
- 图片：既可导入本地文件，也可选择提示词和图片模型创建生成任务，成功结果自动进入图片管理。
- 剧本与分镜：输入故事描述后由文本模型生成总时长 60 秒、固定 6 段、每段 10 秒的视频分镜提示词；也支持手动编辑镜头、角色、场景、机位与台词。
- 视频任务：单个分镜或全部分镜可选择视频模型加入任务队列，统一查看状态、进度和错误，可取消或清理任务记录。
- 视频合成：选择并排序至少两个视频后由 FFmpeg 拼接，成功产物自动进入视频管理。

视频合成前请确认 `ffmpeg -version` 可正常执行。若页面提示未检测到 FFmpeg，将 FFmpeg 加入系统 `PATH` 并重启后端。

## 模型接口协议

文本和图片模型默认使用 OpenAI 兼容协议：

- 文本：`POST {base_url}/chat/completions`
- 图片：`POST {base_url}/images/generations`
- 连接测试：`GET {base_url}/models`

AutoDL ComfyUI 视频工作流使用异步任务协议。模型管理中选择“AutoDL ComfyUI
工作流”，并按下面方式配置：

- 厂商：`AutoDL ComfyUI`
- 工作流 ID：例如 `minimax_h3_lightx2v_no_pic`
- 任务提交地址：`https://autodl.art/api/v1/comfyui/comfyui_workflow`
- Key：在 AutoDL 令牌管理中创建的 `ComfyUI` 分组 Token

扩展参数示例：

```json
{
  "protocol": "COMFYUI",
  "poll_interval": 3,
  "timeout": 900,
  "video_options": {
    "resolution": "768p竖"
  }
}
```

系统提交任务后会保存平台返回的 `task_id`，然后通过
`/result/{task_id}` 异步查询状态。任务页会显示平台任务 ID 和平台状态；成功后
自动下载成片并加入视频管理。连接测试仅提交空提示词进行参数校验，不会创建付费
视频任务。

其他视频厂商可在模型的“扩展参数”中配置提交和轮询路径：

```json
{
  "video_submit_path": "/videos/generations",
  "video_status_path": "/videos/generations/{task_id}",
  "poll_interval": 5,
  "video_options": {}
}
```

MiniMax 海螺视频接口已内置适配。接口地址可以直接填写完整提交地址，例如
`https://www.autodl.art/api/v1/minimax/v1/video_generation`。连接测试会发送缺少
`prompt` 的参数校验请求，不会创建视频任务；生成时会自动使用
`/query/video_generation` 查询状态，并通过 `/files/retrieve` 获取成片。10 秒的
`MiniMax-Hailuo-02` 任务默认使用 `768P`。

文本、图片路径也可分别用 `text_path`、`image_path` 覆盖；测试路径可用 `test_path` 覆盖。额外请求参数分别放在 `text_options`、`image_options`、`video_options`。保存模型 Key 后不要随意修改根目录 `.env` 中的 `SECRET_KEY`，否则已有 Key 无法解密。

## 使用流程

1. 在模型管理中至少配置一个文本模型、图片模型和视频模型，并测试连接。
2. 在提示词管理输入关键内容，生成主体三视图或场景提示词。
3. 在图片管理选择提示词生成参考图片；在剧本管理生成六段分镜。
4. 打开剧本分镜，将单段或全部分镜加入视频任务；成功后到视频管理排序并合成为完整视频。

