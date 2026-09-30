from __future__ import annotations

import base64
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.file import AiFile
from app.models.workflow import AiModelConfig, AiPrompt, AiStoryboard, AiTask
from app.services.ai_gateway import generate_image, generate_text, generate_video
from app.services.file_storage import resolve_storage_file


MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}

_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")


def _translation_model(db, image_config: AiModelConfig) -> AiModelConfig:
    configured_id = image_config.extra_config.get("translation_model_config_id")
    if configured_id:
        config = db.get(AiModelConfig, int(configured_id))
        if config and config.model_type == "TEXT" and config.status == "ENABLED":
            return config
        raise RuntimeError("图片模型配置的翻译模型不可用")
    config = db.scalar(
        select(AiModelConfig)
        .where(AiModelConfig.model_type == "TEXT", AiModelConfig.status == "ENABLED")
        .order_by(AiModelConfig.is_default.desc(), AiModelConfig.updated_at.desc())
    )
    if config is None:
        raise RuntimeError("检测到中文提示词，但没有可用文本模型执行英文转换")
    return config


async def _prepare_image_prompt(
    db, image_config: AiModelConfig, content: str
) -> tuple[str, bool]:
    if not _CJK_PATTERN.search(content):
        return content, False
    translated = await generate_text(
        _translation_model(db, image_config),
        (
            "Translate the user's visual design description into one concise English image "
            "generation prompt. Preserve subject, appearance, clothing, composition, camera, "
            "lighting, materials, colors, and style. Treat every human subject as an adult "
            "aged 21 or older and keep all clothing details intact. Use positive, neutral, "
            "family-friendly wording. Do not include explanations, safety terminology, or "
            "negative concepts. Output only the English image prompt."
        ),
        content,
        temperature=0.2,
    )
    return translated.strip(), True


def _save_media(data: bytes, mime_type: str, media_type: str, name: str) -> tuple[str, Path]:
    extension = MIME_EXTENSIONS.get(mime_type, ".png" if media_type == "image" else ".mp4")
    safe_name = Path(name).stem.strip() or media_type
    relative = (
        Path("generated")
        / media_type
        / datetime.now().strftime("%Y%m%d")
        / f"{safe_name}-{uuid4().hex[:10]}{extension}"
    )
    output_path = settings.storage_path / relative
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    return relative.as_posix(), output_path


def _finish_failed(task_id: int, message: str) -> None:
    with SessionLocal() as db:
        task = db.get(AiTask, task_id)
        if task is None or task.status == "CANCELLED":
            return
        task.status = "FAILED"
        task.progress = 100
        task.error_message = message
        task.finished_at = datetime.now()
        db.commit()


async def run_image_generation(task_id: int) -> None:
    try:
        with SessionLocal() as db:
            task = db.get(AiTask, task_id)
            if task is None or task.status == "CANCELLED":
                return
            prompt = db.get(AiPrompt, task.request_payload.get("prompt_id"))
            config = db.get(AiModelConfig, task.model_config_id)
            if prompt is None or config is None:
                raise RuntimeError("提示词或图片模型配置不存在")
            task.status = "RUNNING"
            task.progress = 10
            task.started_at = datetime.now()
            db.commit()

            content = prompt.content
            if prompt.negative_prompt:
                content = f"{content}\nNegative prompt: {prompt.negative_prompt}"
            content, translated = await _prepare_image_prompt(db, config, content)
            task.progress = 25
            task.result_payload = {
                **(task.result_payload or {}),
                "provider_prompt": content,
                "prompt_translated": translated,
            }
            db.commit()
            data, mime_type = await generate_image(
                config, content, size=str(task.request_payload.get("size", "1024x1024"))
            )
            db.refresh(task)
            if task.status == "CANCELLED":
                return
            relative_path, output_path = _save_media(
                data, mime_type, "image", str(task.request_payload.get("name", task.name))
            )
            file_record = AiFile(
                project_id=task.project_id,
                file_name=output_path.name,
                original_name=output_path.name,
                file_type="IMAGE",
                mime_type=mime_type,
                file_size=len(data),
                storage_type="LOCAL",
                storage_path=relative_path,
                url=f"/storage/{relative_path}",
                source_type="AI_IMAGE",
                source_id=task.id,
                created_by=task.created_by,
            )
            db.add(file_record)
            db.flush()
            task.status = "SUCCESS"
            task.progress = 100
            task.result_payload = {
                **(task.result_payload or {}),
                "file_id": file_record.id,
                "url": file_record.url,
            }
            task.finished_at = datetime.now()
            db.commit()
    except Exception as exc:
        _finish_failed(task_id, str(exc))


def _reference_data_url(file_record: AiFile | None) -> str | None:
    if file_record is None:
        return None
    path = resolve_storage_file(file_record.storage_path)
    if not path.is_file():
        raise RuntimeError("参考图片的磁盘文件不存在")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{file_record.mime_type};base64,{encoded}"


async def run_video_generation(task_id: int) -> None:
    try:
        with SessionLocal() as db:
            task = db.get(AiTask, task_id)
            if task is None or task.status == "CANCELLED":
                return
            storyboard = db.get(AiStoryboard, task.target_id)
            config = db.get(AiModelConfig, task.model_config_id)
            if storyboard is None or config is None:
                raise RuntimeError("分镜或视频模型配置不存在")
            prompt = storyboard.video_prompt or storyboard.description
            if not prompt:
                raise RuntimeError("该分镜没有视频提示词或画面描述")
            reference_file_ids = task.request_payload.get("reference_file_ids") or []
            if not reference_file_ids and task.request_payload.get("reference_file_id"):
                reference_file_ids = [task.request_payload["reference_file_id"]]
            reference_files: list[AiFile] = []
            for reference_file_id in reference_file_ids:
                reference_file = db.get(AiFile, reference_file_id)
                if reference_file is None or reference_file.file_type != "IMAGE":
                    raise RuntimeError("参考文件不是有效图片")
                reference_files.append(reference_file)
            image_data_urls = [
                data_url
                for reference_file in reference_files
                if (data_url := _reference_data_url(reference_file)) is not None
            ]
            request_options = {
                key: task.request_payload[key]
                for key in ("resolution", "seed")
                if task.request_payload.get(key) is not None
            }
            task.status = "RUNNING"
            task.progress = 10
            task.started_at = datetime.now()
            db.commit()

            def cancelled() -> bool:
                db.expire(task)
                db.refresh(task)
                return task.status == "CANCELLED"

            def submitted(provider_task_id: str) -> None:
                db.refresh(task)
                if task.status == "CANCELLED":
                    return
                task.progress = 20
                task.result_payload = {
                    **(task.result_payload or {}),
                    "provider_task_id": provider_task_id,
                    "provider_status": "SUBMITTED",
                }
                db.commit()

            def polled(provider_status: str, poll_index: int) -> None:
                db.refresh(task)
                if task.status == "CANCELLED":
                    return
                task.progress = min(90, max(task.progress, 20 + poll_index * 2))
                task.result_payload = {
                    **(task.result_payload or {}),
                    "provider_status": provider_status.upper() or "PROCESSING",
                }
                db.commit()

            data, mime_type = await generate_video(
                config,
                prompt,
                duration=task.request_payload.get("duration") or storyboard.duration or 10,
                image_data_urls=image_data_urls,
                request_options=request_options,
                cancelled=cancelled,
                on_submitted=submitted,
                on_poll=polled,
            )
            db.refresh(task)
            if task.status == "CANCELLED":
                return
            relative_path, output_path = _save_media(data, mime_type, "video", storyboard.title)
            file_record = AiFile(
                project_id=task.project_id,
                file_name=output_path.name,
                original_name=output_path.name,
                file_type="VIDEO",
                mime_type=mime_type,
                file_size=len(data),
                storage_type="LOCAL",
                storage_path=relative_path,
                url=f"/storage/{relative_path}",
                duration=storyboard.duration or 10,
                source_type="AI_VIDEO",
                source_id=task.id,
                created_by=task.created_by,
            )
            db.add(file_record)
            db.flush()
            storyboard.status = "GENERATED"
            task.status = "SUCCESS"
            task.progress = 100
            task.result_payload = {
                **(task.result_payload or {}),
                "provider_status": "SUCCESS",
                "file_id": file_record.id,
                "url": file_record.url,
            }
            task.finished_at = datetime.now()
            db.commit()
    except Exception as exc:
        _finish_failed(task_id, str(exc))
