from __future__ import annotations

import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.file import AiFile
from app.models.workflow import AiTask
from app.services.file_storage import resolve_storage_file


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def run_video_merge(task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(AiTask, task_id)
        if task is None or task.status == "CANCELLED":
            return
        task.status = "RUNNING"
        task.progress = 10
        task.started_at = datetime.now()
        db.commit()

        output_path: Path | None = None
        try:
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg is None:
                raise RuntimeError("未检测到 FFmpeg，请安装并加入系统 PATH 后重试")

            file_ids = task.request_payload.get("file_ids", [])
            files = [db.get(AiFile, file_id) for file_id in file_ids]
            if any(record is None for record in files):
                raise RuntimeError("合成源视频已被删除")
            source_paths = [resolve_storage_file(record.storage_path) for record in files if record]
            if any(not path.is_file() for path in source_paths):
                raise RuntimeError("合成源视频的磁盘文件不存在")

            output_dir = settings.storage_path / "generated" / "video" / datetime.now().strftime("%Y%m%d")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_name = Path(str(task.request_payload.get("output_name", "merged.mp4"))).stem
            output_path = output_dir / f"{output_name}-{uuid4().hex[:10]}.mp4"

            with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as manifest:
                manifest_path = Path(manifest.name)
                for source_path in source_paths:
                    escaped = source_path.resolve().as_posix().replace("'", "'\\''")
                    manifest.write(f"file '{escaped}'\n")

            try:
                result = subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(manifest_path),
                        "-c",
                        "copy",
                        str(output_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60 * 60,
                    check=False,
                )
            finally:
                manifest_path.unlink(missing_ok=True)

            if result.returncode != 0 or not output_path.is_file():
                detail = result.stderr.strip()[-2000:] or "FFmpeg 合成失败"
                raise RuntimeError(detail)

            db.refresh(task)
            if task.status == "CANCELLED":
                output_path.unlink(missing_ok=True)
                return

            relative_path = output_path.relative_to(settings.storage_path).as_posix()
            file_record = AiFile(
                project_id=task.project_id,
                file_name=f"{output_name}.mp4",
                original_name=f"{output_name}.mp4",
                file_type="VIDEO",
                mime_type="video/mp4",
                file_size=output_path.stat().st_size,
                storage_type="LOCAL",
                storage_path=relative_path,
                url=f"/storage/{relative_path}",
                source_type="VIDEO_MERGE",
                source_id=task.id,
                created_by=task.created_by,
            )
            db.add(file_record)
            db.flush()
            task.status = "SUCCESS"
            task.progress = 100
            task.result_payload = {"file_id": file_record.id, "url": file_record.url}
            task.finished_at = datetime.now()
            db.commit()
        except Exception as exc:
            if output_path is not None:
                output_path.unlink(missing_ok=True)
            db.rollback()
            task = db.get(AiTask, task_id)
            if task is not None and task.status != "CANCELLED":
                task.status = "FAILED"
                task.progress = 100
                task.error_message = str(exc)
                task.finished_at = datetime.now()
                db.commit()
