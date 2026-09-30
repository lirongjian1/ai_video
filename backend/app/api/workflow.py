import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import func, or_, select, update

from app.api.dependencies import CurrentUser, DbSession
from app.models.file import AiFile
from app.models.project import AiProject
from app.models.workflow import (
    AiCharacter,
    AiModelConfig,
    AiPrompt,
    AiScene,
    AiScript,
    AiStoryboard,
    AiTask,
)
from app.schemas.common import MessageResponse, Page
from app.schemas.workflow import (
    CharacterCreate,
    CharacterRead,
    CharacterUpdate,
    ImageGenerateRequest,
    ModelConnectionResult,
    ModelConfigCreate,
    ModelConfigRead,
    ModelConfigUpdate,
    PromptCreate,
    PromptGenerateRequest,
    PromptRead,
    PromptUpdate,
    SceneCreate,
    SceneRead,
    SceneUpdate,
    ScriptCreate,
    ScriptGenerateRequest,
    ScriptRead,
    ScriptUpdate,
    StoryboardCreate,
    StoryboardRead,
    StoryboardUpdate,
    TaskCapabilities,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    VideoMergeCreate,
    VideoGenerateRequest,
)
from app.services.ai_gateway import generate_text, test_model_connection
from app.services.generation import run_image_generation, run_video_generation
from app.services.secret_store import encrypt_secret
from app.services.video_merge import ffmpeg_available, run_video_merge


router = APIRouter(tags=["工作流"])


def _require(db: DbSession, model: type, record_id: int | None, label: str):
    if record_id is None:
        return None
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{label}不存在")
    return record


def _apply_values(record, values: dict) -> None:
    for field, value in values.items():
        column = record.__table__.columns.get(field)
        if value is None and column is not None and not column.nullable:
            raise HTTPException(status_code=422, detail=f"{field} 不能为空")
        setattr(record, field, value)


def _apply(record, payload) -> None:
    _apply_values(record, payload.model_dump(exclude_unset=True))


def _require_model_config(
    db: DbSession, config_id: int, model_type: str
) -> AiModelConfig:
    config = _require(db, AiModelConfig, config_id, "模型配置")
    if config.status != "ENABLED":
        raise HTTPException(status_code=409, detail="所选模型配置已停用")
    if config.model_type != model_type:
        labels = {"TEXT": "文本", "IMAGE": "图片", "VIDEO": "视频"}
        raise HTTPException(status_code=400, detail=f"请选择{labels[model_type]}模型")
    return config


@router.get("/model-configs", response_model=Page[ModelConfigRead])
def list_model_configs(
    _: CurrentUser,
    db: DbSession,
    keyword: str | None = Query(default=None, max_length=150),
    model_type: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[ModelConfigRead]:
    filters = []
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(or_(AiModelConfig.name.like(pattern), AiModelConfig.model_name.like(pattern)))
    if model_type:
        filters.append(AiModelConfig.model_type == model_type)
    if status_filter:
        filters.append(AiModelConfig.status == status_filter)
    total = db.scalar(select(func.count(AiModelConfig.id)).where(*filters)) or 0
    items = db.scalars(
        select(AiModelConfig)
        .where(*filters)
        .order_by(AiModelConfig.is_default.desc(), AiModelConfig.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=list(items), total=total, page=page, page_size=page_size)


def _clear_default(db: DbSession, model_type: str, except_id: int | None = None) -> None:
    statement = update(AiModelConfig).where(AiModelConfig.model_type == model_type)
    if except_id is not None:
        statement = statement.where(AiModelConfig.id != except_id)
    db.execute(statement.values(is_default=False))


@router.post("/model-configs", response_model=ModelConfigRead, status_code=status.HTTP_201_CREATED)
def create_model_config(
    payload: ModelConfigCreate, current_user: CurrentUser, db: DbSession
) -> AiModelConfig:
    if payload.is_default:
        _clear_default(db, payload.model_type)
    values = payload.model_dump(exclude={"api_key"})
    record = AiModelConfig(
        **values,
        api_key_encrypted=encrypt_secret(payload.api_key.strip()) if payload.api_key else None,
        created_by=current_user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/model-configs/{record_id}", response_model=ModelConfigRead)
def update_model_config(
    record_id: int, payload: ModelConfigUpdate, _: CurrentUser, db: DbSession
) -> AiModelConfig:
    record = _require(db, AiModelConfig, record_id, "模型配置")
    values = payload.model_dump(exclude_unset=True)
    api_key = values.pop("api_key", None)
    new_type = values.get("model_type", record.model_type)
    if values.get("is_default"):
        _clear_default(db, new_type, record.id)
    _apply_values(record, values)
    if api_key:
        record.api_key_encrypted = encrypt_secret(api_key.strip())
    db.commit()
    db.refresh(record)
    return record


@router.delete("/model-configs/{record_id}", response_model=MessageResponse)
def delete_model_config(record_id: int, _: CurrentUser, db: DbSession) -> MessageResponse:
    record = _require(db, AiModelConfig, record_id, "模型配置")
    db.delete(record)
    db.commit()
    return MessageResponse(message="模型配置已删除")


@router.post("/model-configs/{record_id}/test", response_model=ModelConnectionResult)
async def test_model_config(
    record_id: int, _: CurrentUser, db: DbSession
) -> ModelConnectionResult:
    record = _require(db, AiModelConfig, record_id, "模型配置")
    try:
        message = await test_model_connection(record)
        return ModelConnectionResult(ok=True, message=message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/prompts", response_model=Page[PromptRead])
def list_prompts(
    _: CurrentUser,
    db: DbSession,
    keyword: str | None = Query(default=None, max_length=150),
    project_id: int | None = None,
    prompt_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[PromptRead]:
    filters = []
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(or_(AiPrompt.name.like(pattern), AiPrompt.content.like(pattern)))
    if project_id is not None:
        filters.append(AiPrompt.project_id == project_id)
    if prompt_type:
        filters.append(AiPrompt.prompt_type == prompt_type)
    total = db.scalar(select(func.count(AiPrompt.id)).where(*filters)) or 0
    items = db.scalars(
        select(AiPrompt)
        .where(*filters)
        .order_by(AiPrompt.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=list(items), total=total, page=page, page_size=page_size)


@router.post("/prompts", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
def create_prompt(payload: PromptCreate, current_user: CurrentUser, db: DbSession) -> AiPrompt:
    _require(db, AiProject, payload.project_id, "项目")
    record = AiPrompt(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post("/prompts/generate", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
async def generate_prompt(
    payload: PromptGenerateRequest, current_user: CurrentUser, db: DbSession
) -> AiPrompt:
    _require(db, AiProject, payload.project_id, "项目")
    config = _require_model_config(db, payload.model_config_id, "TEXT")
    task = AiTask(
        project_id=payload.project_id,
        name=f"生成提示词：{payload.name}",
        task_type="TEXT",
        model_config_id=config.id,
        status="RUNNING",
        progress=20,
        request_payload={
            "generation_type": payload.generation_type,
            "keywords": payload.keywords,
        },
        started_at=datetime.now(),
        created_by=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    if payload.generation_type == "CHARACTER_THREE_VIEW":
        system_prompt = (
            "You are a professional visual development artist. First identify whether the "
            "user's subject is a human, a real animal, a fantasy creature, or an object, then "
            "create one concise production-ready three-view model-sheet prompt. Always show "
            "the same subject in consistent front, side, and rear orthographic views, with a "
            "neutral pose, consistent proportions, a clean background, no text, and no "
            "watermark. For a human or humanoid subject, make the character clearly adult "
            "aged 21 or older and preserve only clothing and accessories requested by the "
            "user. For a real animal, preserve natural anatomy, posture, fur, scales, feathers, "
            "markings, and species traits; do not add clothing, accessories, human anatomy, "
            "or anthropomorphic behavior unless the user explicitly requests them. For a "
            "fantasy creature or object, preserve its native structure and do not invent human "
            "traits. Never introduce major elements that were not requested. Add appropriate "
            "materials, colors, lighting, and image-quality details. Use positive, "
            "family-friendly wording. Write the final prompt in Simplified Chinese and output "
            "only that prompt."
        )
        prompt_type = "CHARACTER"
    else:
        system_prompt = (
            "You are a professional film environment concept designer. Create one concise, "
            "production-ready image prompt from the user's description. Include spatial "
            "layout, time of day, weather, lighting, color palette, camera angle, environment "
            "details, atmosphere, and image quality. Do not include people, text, or "
            "watermarks. Write the final prompt in Simplified Chinese and output only that "
            "prompt."
        )
        prompt_type = "SCENE"
    try:
        content = await generate_text(config, system_prompt, payload.keywords)
        record = AiPrompt(
            project_id=payload.project_id,
            name=payload.name,
            prompt_type=prompt_type,
            content=content,
            variables={
                "keywords": payload.keywords,
                "generation_type": payload.generation_type,
                "model_config_id": config.id,
            },
            status="ENABLED",
            created_by=current_user.id,
        )
        db.add(record)
        db.flush()
        task.status = "SUCCESS"
        task.progress = 100
        task.target_type = "PROMPT"
        task.target_id = record.id
        task.result_payload = {"prompt_id": record.id}
        task.finished_at = datetime.now()
        db.commit()
        db.refresh(record)
        return record
    except Exception as exc:
        db.rollback()
        failed_task = db.get(AiTask, task.id)
        if failed_task:
            failed_task.status = "FAILED"
            failed_task.progress = 100
            failed_task.error_message = str(exc)
            failed_task.finished_at = datetime.now()
            db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.put("/prompts/{record_id}", response_model=PromptRead)
def update_prompt(record_id: int, payload: PromptUpdate, _: CurrentUser, db: DbSession) -> AiPrompt:
    record = _require(db, AiPrompt, record_id, "提示词")
    if "project_id" in payload.model_fields_set:
        _require(db, AiProject, payload.project_id, "项目")
    _apply(record, payload)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/prompts/{record_id}", response_model=MessageResponse)
def delete_prompt(record_id: int, _: CurrentUser, db: DbSession) -> MessageResponse:
    record = _require(db, AiPrompt, record_id, "提示词")
    db.delete(record)
    db.commit()
    return MessageResponse(message="提示词已删除")


def _validate_creative_links(
    db: DbSession, project_id: int | None, reference_file_id: int | None, prompt_id: int | None
) -> None:
    _require(db, AiProject, project_id, "项目")
    _require(db, AiFile, reference_file_id, "参考文件")
    _require(db, AiPrompt, prompt_id, "提示词")


def _list_creative(
    db: DbSession, model, keyword: str | None, project_id: int | None, page: int, page_size: int
):
    filters = []
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(or_(model.name.like(pattern), model.description.like(pattern)))
    if project_id is not None:
        filters.append(model.project_id == project_id)
    total = db.scalar(select(func.count(model.id)).where(*filters)) or 0
    items = db.scalars(
        select(model)
        .where(*filters)
        .order_by(model.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=list(items), total=total, page=page, page_size=page_size)


@router.get("/characters", response_model=Page[CharacterRead])
def list_characters(
    _: CurrentUser,
    db: DbSession,
    keyword: str | None = Query(default=None, max_length=150),
    project_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return _list_creative(db, AiCharacter, keyword, project_id, page, page_size)


@router.post("/characters", response_model=CharacterRead, status_code=status.HTTP_201_CREATED)
def create_character(
    payload: CharacterCreate, current_user: CurrentUser, db: DbSession
) -> AiCharacter:
    _validate_creative_links(db, payload.project_id, payload.reference_file_id, payload.prompt_id)
    record = AiCharacter(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/characters/{record_id}", response_model=CharacterRead)
def update_character(
    record_id: int, payload: CharacterUpdate, _: CurrentUser, db: DbSession
) -> AiCharacter:
    record = _require(db, AiCharacter, record_id, "角色")
    values = payload.model_dump(exclude_unset=True)
    _validate_creative_links(
        db,
        values.get("project_id", record.project_id),
        values.get("reference_file_id", record.reference_file_id),
        values.get("prompt_id", record.prompt_id),
    )
    _apply(record, payload)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/characters/{record_id}", response_model=MessageResponse)
def delete_character(record_id: int, _: CurrentUser, db: DbSession) -> MessageResponse:
    record = _require(db, AiCharacter, record_id, "角色")
    db.delete(record)
    db.commit()
    return MessageResponse(message="角色已删除")


@router.get("/scenes", response_model=Page[SceneRead])
def list_scenes(
    _: CurrentUser,
    db: DbSession,
    keyword: str | None = Query(default=None, max_length=150),
    project_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return _list_creative(db, AiScene, keyword, project_id, page, page_size)


@router.post("/scenes", response_model=SceneRead, status_code=status.HTTP_201_CREATED)
def create_scene(payload: SceneCreate, current_user: CurrentUser, db: DbSession) -> AiScene:
    _validate_creative_links(db, payload.project_id, payload.reference_file_id, payload.prompt_id)
    record = AiScene(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/scenes/{record_id}", response_model=SceneRead)
def update_scene(record_id: int, payload: SceneUpdate, _: CurrentUser, db: DbSession) -> AiScene:
    record = _require(db, AiScene, record_id, "场景")
    values = payload.model_dump(exclude_unset=True)
    _validate_creative_links(
        db,
        values.get("project_id", record.project_id),
        values.get("reference_file_id", record.reference_file_id),
        values.get("prompt_id", record.prompt_id),
    )
    _apply(record, payload)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/scenes/{record_id}", response_model=MessageResponse)
def delete_scene(record_id: int, _: CurrentUser, db: DbSession) -> MessageResponse:
    record = _require(db, AiScene, record_id, "场景")
    db.delete(record)
    db.commit()
    return MessageResponse(message="场景已删除")


@router.get("/scripts", response_model=Page[ScriptRead])
def list_scripts(
    _: CurrentUser,
    db: DbSession,
    keyword: str | None = Query(default=None, max_length=200),
    project_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[ScriptRead]:
    filters = []
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(or_(AiScript.title.like(pattern), AiScript.summary.like(pattern)))
    if project_id is not None:
        filters.append(AiScript.project_id == project_id)
    total = db.scalar(select(func.count(AiScript.id)).where(*filters)) or 0
    rows = db.execute(
        select(AiScript, func.count(AiStoryboard.id))
        .outerjoin(AiStoryboard, AiStoryboard.script_id == AiScript.id)
        .where(*filters)
        .group_by(AiScript.id)
        .order_by(AiScript.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        ScriptRead.model_validate(script).model_copy(update={"storyboard_count": count})
        for script, count in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/scripts", response_model=ScriptRead, status_code=status.HTTP_201_CREATED)
def create_script(payload: ScriptCreate, current_user: CurrentUser, db: DbSession) -> ScriptRead:
    _require(db, AiProject, payload.project_id, "项目")
    record = AiScript(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return ScriptRead.model_validate(record)


def _parse_storyboard_json(content: str) -> dict:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("文本模型未返回有效的分镜 JSON")
    value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("分镜结果必须是 JSON 对象")
    shots = value.get("shots")
    if not isinstance(shots, list) or len(shots) != 6:
        raise ValueError("文本模型必须返回正好 6 个分镜")
    return value


@router.post("/scripts/generate", response_model=ScriptRead, status_code=status.HTTP_201_CREATED)
async def generate_script(
    payload: ScriptGenerateRequest, current_user: CurrentUser, db: DbSession
) -> ScriptRead:
    _require(db, AiProject, payload.project_id, "项目")
    config = _require_model_config(db, payload.model_config_id, "TEXT")
    task = AiTask(
        project_id=payload.project_id,
        name=f"生成六段分镜：{payload.title}",
        task_type="TEXT",
        model_config_id=config.id,
        status="RUNNING",
        progress=15,
        request_payload={"keywords": payload.keywords, "style": payload.style},
        started_at=datetime.now(),
        created_by=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    system_prompt = (
        "你是一名短视频导演和分镜师。请把用户描述改编为连续的 60 秒故事，严格拆分为 "
        "6 个分镜，每个分镜 10 秒。所有自然语言字段必须使用简体中文，不得输出英文提示词。"
        "仅输出严格 JSON，不要使用 Markdown。JSON 结构必须为："
        '{"summary":"故事摘要","content":"完整故事梗概","shots":['
        '{"sequence":1,"title":"镜头标题","description":"画面描述","camera":"景别和运镜",'
        '"dialogue":"台词或旁白","video_prompt":"可直接交给视频模型的完整提示词"}]}. '
        "shots 数组必须正好包含 6 项，sequence 从 1 到 6。人物或动物主体的外貌、体型、"
        "毛色、发型、服装、配饰以及场景布局必须在全部分镜中保持一致。每个 video_prompt "
        "必须是完整中文句子，并以‘严格参考所提供的人物、动物主体和场景参考图，保持主体"
        "身份、外貌、造型与场景一致’开头，再描述主体动作、环境、景别、运镜、光线和视觉"
        "风格；不要写 8K、超高清等与工作流分辨率参数冲突的词。"
    )
    user_prompt = payload.keywords
    if payload.style:
        user_prompt += f"\n视觉风格：{payload.style}"
    try:
        generated = _parse_storyboard_json(
            await generate_text(config, system_prompt, user_prompt, temperature=0.6)
        )
        script = AiScript(
            project_id=payload.project_id,
            title=payload.title,
            summary=str(generated.get("summary") or payload.keywords)[:5000],
            content=str(generated.get("content") or payload.keywords),
            duration=60,
            status="READY",
            created_by=current_user.id,
        )
        db.add(script)
        db.flush()
        board_ids = []
        for index, shot in enumerate(generated["shots"], start=1):
            if not isinstance(shot, dict):
                raise ValueError(f"第 {index} 个分镜格式不正确")
            board = AiStoryboard(
                script_id=script.id,
                project_id=payload.project_id,
                sequence=index,
                title=str(shot.get("title") or f"分镜 {index}")[:200],
                description=str(shot.get("description") or ""),
                duration=10,
                camera=str(shot.get("camera") or "")[:200] or None,
                dialogue=str(shot.get("dialogue") or "") or None,
                video_prompt=str(shot.get("video_prompt") or shot.get("description") or ""),
                character_ids=[],
                reference_file_ids=[],
                status="READY",
                created_by=current_user.id,
            )
            db.add(board)
            db.flush()
            board_ids.append(board.id)
        task.status = "SUCCESS"
        task.progress = 100
        task.target_type = "SCRIPT"
        task.target_id = script.id
        task.result_payload = {"script_id": script.id, "storyboard_ids": board_ids}
        task.finished_at = datetime.now()
        db.commit()
        db.refresh(script)
        return ScriptRead.model_validate(script).model_copy(update={"storyboard_count": 6})
    except Exception as exc:
        db.rollback()
        failed_task = db.get(AiTask, task.id)
        if failed_task:
            failed_task.status = "FAILED"
            failed_task.progress = 100
            failed_task.error_message = str(exc)
            failed_task.finished_at = datetime.now()
            db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.put("/scripts/{record_id}", response_model=ScriptRead)
def update_script(record_id: int, payload: ScriptUpdate, _: CurrentUser, db: DbSession) -> ScriptRead:
    record = _require(db, AiScript, record_id, "剧本")
    if "project_id" in payload.model_fields_set:
        if payload.project_id is None:
            raise HTTPException(status_code=422, detail="剧本必须归属项目")
        _require(db, AiProject, payload.project_id, "项目")
        if payload.project_id != record.project_id:
            db.execute(
                update(AiStoryboard)
                .where(AiStoryboard.script_id == record.id)
                .values(project_id=payload.project_id)
            )
    _apply(record, payload)
    db.commit()
    db.refresh(record)
    count = db.scalar(select(func.count(AiStoryboard.id)).where(AiStoryboard.script_id == record.id)) or 0
    return ScriptRead.model_validate(record).model_copy(update={"storyboard_count": count})


@router.delete("/scripts/{record_id}", response_model=MessageResponse)
def delete_script(record_id: int, _: CurrentUser, db: DbSession) -> MessageResponse:
    record = _require(db, AiScript, record_id, "剧本")
    db.delete(record)
    db.commit()
    return MessageResponse(message="剧本已删除")


@router.get("/storyboards", response_model=Page[StoryboardRead])
def list_storyboards(
    _: CurrentUser,
    db: DbSession,
    script_id: int | None = None,
    project_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
) -> Page[StoryboardRead]:
    filters = []
    if script_id is not None:
        filters.append(AiStoryboard.script_id == script_id)
    if project_id is not None:
        filters.append(AiStoryboard.project_id == project_id)
    total = db.scalar(select(func.count(AiStoryboard.id)).where(*filters)) or 0
    items = db.scalars(
        select(AiStoryboard)
        .where(*filters)
        .order_by(AiStoryboard.sequence.asc(), AiStoryboard.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=list(items), total=total, page=page, page_size=page_size)


@router.post("/storyboards", response_model=StoryboardRead, status_code=status.HTTP_201_CREATED)
def create_storyboard(
    payload: StoryboardCreate, current_user: CurrentUser, db: DbSession
) -> AiStoryboard:
    script = _require(db, AiScript, payload.script_id, "剧本")
    _require(db, AiScene, payload.scene_id, "场景")
    for character_id in payload.character_ids:
        _require(db, AiCharacter, character_id, "角色")
    for file_id in payload.reference_file_ids:
        _require(db, AiFile, file_id, "参考文件")
    record = AiStoryboard(
        **payload.model_dump(), project_id=script.project_id, created_by=current_user.id
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/storyboards/{record_id}", response_model=StoryboardRead)
def update_storyboard(
    record_id: int, payload: StoryboardUpdate, _: CurrentUser, db: DbSession
) -> AiStoryboard:
    record = _require(db, AiStoryboard, record_id, "分镜")
    values = payload.model_dump(exclude_unset=True)
    if "scene_id" in values:
        _require(db, AiScene, values["scene_id"], "场景")
    for character_id in values.get("character_ids", []):
        _require(db, AiCharacter, character_id, "角色")
    for file_id in values.get("reference_file_ids", []):
        _require(db, AiFile, file_id, "参考文件")
    _apply(record, payload)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/storyboards/{record_id}", response_model=MessageResponse)
def delete_storyboard(record_id: int, _: CurrentUser, db: DbSession) -> MessageResponse:
    record = _require(db, AiStoryboard, record_id, "分镜")
    db.delete(record)
    db.commit()
    return MessageResponse(message="分镜已删除")


@router.post("/images/generate", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_image_generation(
    payload: ImageGenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
) -> AiTask:
    prompt = _require(db, AiPrompt, payload.prompt_id, "提示词")
    _require_model_config(db, payload.model_config_id, "IMAGE")
    project_id = payload.project_id if payload.project_id is not None else prompt.project_id
    _require(db, AiProject, project_id, "项目")
    task = AiTask(
        project_id=project_id,
        name=f"生成图片：{payload.name}",
        task_type="IMAGE",
        target_type="PROMPT",
        target_id=prompt.id,
        model_config_id=payload.model_config_id,
        status="PENDING",
        request_payload={"prompt_id": prompt.id, "name": payload.name, "size": payload.size},
        created_by=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    background_tasks.add_task(run_image_generation, task.id)
    return task


@router.post(
    "/storyboards/{record_id}/generate-video",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_video_generation(
    record_id: int,
    payload: VideoGenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
) -> AiTask:
    storyboard = _require(db, AiStoryboard, record_id, "分镜")
    config = _require_model_config(db, payload.model_config_id, "VIDEO")
    if not (storyboard.video_prompt or storyboard.description):
        raise HTTPException(status_code=400, detail="请先填写分镜的视频提示词或画面描述")
    reference_file_ids = list(dict.fromkeys(payload.reference_file_ids))
    if payload.reference_file_id is not None and payload.reference_file_id not in reference_file_ids:
        reference_file_ids.insert(0, payload.reference_file_id)
    if len(reference_file_ids) > 9:
        raise HTTPException(status_code=400, detail="参考图片最多选择 9 张")
    is_comfyui = (
        str(config.extra_config.get("protocol", "")).upper() == "COMFYUI"
        or "/comfyui/comfyui_workflow" in (config.base_url or "").lower()
    )
    if reference_file_ids and is_comfyui and "no_pic" in config.model_name.lower():
        raise HTTPException(
            status_code=400,
            detail=(
                "当前工作流不支持参考图片，请在模型管理中将工作流 ID 改为 "
                "minimax_h3_image_audio_to_video_v2_15s"
            ),
        )
    for reference_file_id in reference_file_ids:
        reference = _require(db, AiFile, reference_file_id, "参考图片")
        if reference.file_type != "IMAGE":
            raise HTTPException(status_code=400, detail="参考文件必须是图片")
        if reference.mime_type.lower() not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(status_code=400, detail="参考图片仅支持 JPG、PNG 或 WebP 格式")
    storyboard.reference_file_ids = reference_file_ids
    task = AiTask(
        project_id=storyboard.project_id,
        name=f"生成视频：{storyboard.title}",
        task_type="VIDEO",
        target_type="STORYBOARD",
        target_id=storyboard.id,
        model_config_id=payload.model_config_id,
        status="PENDING",
        request_payload={
            "reference_file_ids": reference_file_ids,
            "duration": payload.duration,
            "resolution": payload.resolution,
            "seed": payload.seed,
        },
        created_by=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    background_tasks.add_task(run_video_generation, task.id)
    return task


@router.get("/tasks/capabilities", response_model=TaskCapabilities)
def task_capabilities(_: CurrentUser) -> TaskCapabilities:
    return TaskCapabilities(ffmpeg_available=ffmpeg_available())


@router.get("/tasks", response_model=Page[TaskRead])
def list_tasks(
    _: CurrentUser,
    db: DbSession,
    keyword: str | None = Query(default=None, max_length=200),
    project_id: int | None = None,
    task_type: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[TaskRead]:
    filters = []
    if keyword:
        filters.append(AiTask.name.like(f"%{keyword.strip()}%"))
    if project_id is not None:
        filters.append(AiTask.project_id == project_id)
    if task_type:
        filters.append(AiTask.task_type == task_type)
    if status_filter:
        filters.append(AiTask.status == status_filter)
    total = db.scalar(select(func.count(AiTask.id)).where(*filters)) or 0
    items = db.scalars(
        select(AiTask)
        .where(*filters)
        .order_by(AiTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=list(items), total=total, page=page, page_size=page_size)


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, current_user: CurrentUser, db: DbSession) -> AiTask:
    _require(db, AiProject, payload.project_id, "项目")
    _require(db, AiModelConfig, payload.model_config_id, "模型配置")
    record = AiTask(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/tasks/{record_id}", response_model=TaskRead)
def update_task(record_id: int, payload: TaskUpdate, _: CurrentUser, db: DbSession) -> AiTask:
    record = _require(db, AiTask, record_id, "任务")
    values = payload.model_dump(exclude_unset=True)
    if values.get("status") == "RUNNING" and record.started_at is None:
        record.started_at = datetime.now()
    if values.get("status") in {"SUCCESS", "FAILED", "CANCELLED"}:
        record.finished_at = datetime.now()
    _apply(record, payload)
    db.commit()
    db.refresh(record)
    return record


@router.post("/tasks/{record_id}/cancel", response_model=TaskRead)
def cancel_task(record_id: int, _: CurrentUser, db: DbSession) -> AiTask:
    record = _require(db, AiTask, record_id, "任务")
    if record.status in {"SUCCESS", "FAILED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="该任务已结束，不能取消")
    record.status = "CANCELLED"
    record.finished_at = datetime.now()
    db.commit()
    db.refresh(record)
    return record


@router.delete("/tasks/{record_id}", response_model=MessageResponse)
def delete_task(record_id: int, _: CurrentUser, db: DbSession) -> MessageResponse:
    record = _require(db, AiTask, record_id, "任务")
    if record.status == "RUNNING":
        raise HTTPException(status_code=409, detail="运行中的任务不能删除")
    db.delete(record)
    db.commit()
    return MessageResponse(message="任务已删除")


@router.post("/video-merges", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_video_merge(
    payload: VideoMergeCreate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
) -> AiTask:
    _require(db, AiProject, payload.project_id, "项目")
    videos = []
    for file_id in payload.file_ids:
        record = _require(db, AiFile, file_id, "视频文件")
        if record.file_type != "VIDEO":
            raise HTTPException(status_code=400, detail=f"文件 {record.file_name} 不是视频")
        videos.append(record)
    task = AiTask(
        project_id=payload.project_id,
        name=payload.name,
        task_type="MERGE",
        target_type="FILE",
        status="PENDING",
        request_payload={"file_ids": payload.file_ids, "output_name": payload.output_name},
        created_by=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    if ffmpeg_available():
        background_tasks.add_task(run_video_merge, task.id)
    else:
        task.status = "FAILED"
        task.progress = 100
        task.error_message = "未检测到 FFmpeg，请安装并加入系统 PATH 后重试"
        task.finished_at = datetime.now()
        db.commit()
        db.refresh(task)
    return task
