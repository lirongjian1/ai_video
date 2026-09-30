from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin

import httpx

from app.models.workflow import AiModelConfig
from app.services.secret_store import model_api_key


class ModelCallError(RuntimeError):
    pass


_KNOWN_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/images/generations",
    "/videos/generations",
    "/video_generation",
    "/contents/generations/tasks",
)


def _endpoint_root(config: AiModelConfig) -> str:
    base_url = (config.base_url or "").strip().rstrip("/")
    for endpoint_suffix in _KNOWN_ENDPOINT_SUFFIXES:
        if base_url.lower().endswith(endpoint_suffix):
            return base_url[: -len(endpoint_suffix)]
    return base_url


def _url(config: AiModelConfig, key: str, default_path: str) -> str:
    base_url = (config.base_url or "").strip()
    if not base_url:
        raise ModelCallError("模型配置缺少接口地址")
    explicit_path = config.extra_config.get(key)
    path = str(explicit_path or default_path).strip()
    if path.startswith(("http://", "https://")):
        return path
    normalized_base = base_url.rstrip("/")
    if explicit_path is None and normalized_base.lower().endswith(
        default_path.rstrip("/").lower()
    ):
        return normalized_base
    return urljoin(f"{_endpoint_root(config).rstrip('/')}/", path.lstrip("/"))


def _is_minimax_video(config: AiModelConfig) -> bool:
    if config.model_type != "VIDEO":
        return False
    protocol = str(config.extra_config.get("protocol", "")).upper()
    if protocol:
        return protocol == "MINIMAX"
    base_url = (config.base_url or "").lower()
    model_name = config.model_name.lower()
    return (
        "/minimax/" in base_url
        or base_url.rstrip("/").endswith("/video_generation")
        or model_name.startswith(("minimax-hailuo", "t2v-", "i2v-"))
    )


def _is_ark_video(config: AiModelConfig) -> bool:
    if config.model_type != "VIDEO":
        return False
    protocol = str(config.extra_config.get("protocol", "")).upper()
    if protocol:
        return protocol == "ARK"
    base_url = (config.base_url or "").lower()
    return (
        "/contents/generations/tasks" in base_url
        or config.model_name.lower().startswith("doubao-seedance")
    )


def _is_comfyui_video(config: AiModelConfig) -> bool:
    if config.model_type != "VIDEO":
        return False
    protocol = str(config.extra_config.get("protocol", "")).upper()
    base_url = (config.base_url or "").lower()
    return protocol == "COMFYUI" or "/comfyui/comfyui_workflow" in base_url


def _comfyui_url(config: AiModelConfig, path: str) -> str:
    base_url = (config.base_url or "").strip().rstrip("/")
    if not base_url:
        raise ModelCallError("模型配置缺少接口地址")
    marker = "/comfyui/comfyui_workflow"
    marker_index = base_url.lower().find(marker)
    if marker_index >= 0:
        root = base_url[: marker_index + len(marker)]
    elif base_url.lower().endswith("/api/v1"):
        root = f"{base_url}{marker}"
    else:
        root = f"{base_url}/api/v1{marker}"
    return f"{root}/{path.lstrip('/')}"


def _video_url(
    config: AiModelConfig,
    key: str,
    generic_path: str,
    minimax_path: str,
    ark_path: str,
    comfyui_path: str,
) -> str:
    if _is_comfyui_video(config) and not config.extra_config.get(key):
        workflow_id = str(
            config.extra_config.get("workflow_id") or config.model_name
        ).strip()
        return _comfyui_url(
            config,
            comfyui_path.replace("{workflow_id}", workflow_id),
        )
    if _is_ark_video(config):
        default_path = ark_path
    elif _is_minimax_video(config):
        default_path = minimax_path
    else:
        default_path = generic_path
    return _url(config, key, default_path)


def _headers(config: AiModelConfig) -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    api_key = model_api_key(config)
    if api_key:
        header_name = str(config.extra_config.get("auth_header", "Authorization"))
        default_scheme = "" if _is_comfyui_video(config) else "Bearer"
        scheme = str(config.extra_config.get("auth_scheme", default_scheme)).strip()
        headers[header_name] = f"{scheme} {api_key}".strip()
    extra_headers = config.extra_config.get("headers", {})
    if isinstance(extra_headers, dict):
        headers.update({str(key): str(value) for key, value in extra_headers.items()})
    return headers


def _timeout(config: AiModelConfig, default: float = 120) -> float:
    try:
        return float(config.extra_config.get("timeout", default))
    except (TypeError, ValueError):
        return default


def _options(config: AiModelConfig, key: str) -> dict[str, Any]:
    value = config.extra_config.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


def _nested(payload: Any, *paths: tuple[Any, ...]) -> Any:
    for path in paths:
        value = payload
        try:
            for part in path:
                value = value[part] if isinstance(part, int) else value.get(part)
                if value is None:
                    break
        except (AttributeError, IndexError, KeyError, TypeError):
            value = None
        if value is not None:
            return value
    return None


def _available_model_ids(payload: dict[str, Any]) -> set[str]:
    items = _nested(payload, ("data",), ("models",), ("result", "data"))
    if not isinstance(items, list):
        return set()
    model_ids: set[str] = set()
    for item in items:
        if isinstance(item, str):
            model_ids.add(item.strip())
        elif isinstance(item, dict):
            value = item.get("id") or item.get("model") or item.get("name")
            if value:
                model_ids.add(str(value).strip())
    return {item for item in model_ids if item}


async def _json(response: httpx.Response) -> dict[str, Any]:
    if response.is_error:
        detail = response.text.strip()[-1500:]
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = None
        if isinstance(error_payload, dict):
            error_message = str(
                _nested(
                    error_payload,
                    ("error", "message"),
                    ("message",),
                    ("msg",),
                )
                or ""
            )
            error_code = str(
                _nested(error_payload, ("error", "code"), ("code",)) or ""
            )
            normalized_error = f"{error_code} {error_message}".lower()
            if error_code == "401008" or (
                "quota" in normalized_error and "postpaid" in normalized_error
            ):
                detail = (
                    "模型服务额度已用尽且未开启后付费，请在模型厂商控制台开通计费，"
                    "或更换有可用额度的 API Key"
                )
            elif "sensitive_words_detected" in normalized_error:
                detail = "模型服务拒绝了当前输入：内容审核未通过，请调整关键词后重试"
            elif "模型未部署或不支持该接口" in error_message:
                detail = "当前模型未部署或不支持该接口，请检查模型名称和接口地址"
        raise ModelCallError(f"模型接口返回 {response.status_code}: {detail or response.reason_phrase}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ModelCallError("模型接口没有返回有效 JSON") from exc
    if not isinstance(payload, dict):
        raise ModelCallError("模型接口返回格式不受支持")
    return payload


async def test_model_connection(config: AiModelConfig) -> str:
    verify = bool(config.extra_config.get("verify_ssl", True))
    async with httpx.AsyncClient(timeout=_timeout(config, 30), verify=verify) as client:
        if _is_comfyui_video(config) and not config.extra_config.get("test_path"):
            url = _video_url(
                config,
                "video_submit_path",
                "/videos/generations",
                "/video_generation",
                "/contents/generations/tasks",
                "{workflow_id}",
            )
            options = _options(config, "video_options")
            response = await client.post(
                url,
                headers=_headers(config),
                json={
                    "prompt": "",
                    "duration": 1,
                    "resolution": options.get("resolution", "480p竖"),
                },
            )
            data = await _json(response)
            code = str(data.get("code", ""))
            message = str(data.get("msg", ""))
            if code == "RequestParameterIsWrong" and "prompt" in message.lower():
                return "连接成功，ComfyUI Token 和工作流 ID 有效"
            if code and code.lower() != "success":
                raise ModelCallError(f"视频工作流返回 {code}: {message or '未知错误'}")
            raise ModelCallError("视频工作流未返回预期的参数校验结果")

        if (
            _is_minimax_video(config) or _is_ark_video(config)
        ) and not config.extra_config.get("test_path"):
            url = _video_url(
                config,
                "video_submit_path",
                "/videos/generations",
                "/video_generation",
                "/contents/generations/tasks",
                "{workflow_id}",
            )
            payload: dict[str, Any] = {"model": config.model_name}
            if _is_ark_video(config):
                payload["content"] = [{"type": "text", "text": ""}]
            response = await client.post(
                url,
                headers=_headers(config),
                json=payload,
            )
            detail = response.text.lower()
            input_error = any(field in detail for field in ("prompt", "content", "text")) and any(
                marker in detail
                for marker in ("empty", "required", "missing", "invalid", "不能为空", "必填")
            )
            if response.status_code in {400, 406, 422} and input_error:
                return "连接成功，视频接口、认证和模型名称有效"
            await _json(response)
            raise ModelCallError("视频接口未返回预期的参数校验结果")

        url = _url(config, "test_path", "/models")
        response = await client.get(url, headers=_headers(config))
        data = await _json(response)
        available_models = _available_model_ids(data)
        configured_model = config.model_name.strip()
        if available_models and configured_model.casefold() not in {
            item.casefold() for item in available_models
        }:
            raise ModelCallError(
                f"认证成功，但模型名称“{configured_model}”不在服务商的可用模型列表中"
            )
    return "连接成功，认证信息和模型名称有效"


async def generate_text(
    config: AiModelConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.7,
) -> str:
    if config.model_type != "TEXT":
        raise ModelCallError("所选配置不是文本模型")
    payload: dict[str, Any] = {
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    payload.update(_options(config, "text_options"))
    verify = bool(config.extra_config.get("verify_ssl", True))
    async with httpx.AsyncClient(timeout=_timeout(config), verify=verify) as client:
        response = await client.post(
            _url(config, "text_path", "/chat/completions"),
            headers=_headers(config),
            json=payload,
        )
        data = await _json(response)
    content = _nested(
        data,
        ("choices", 0, "message", "content"),
        ("choices", 0, "text"),
        ("output_text",),
        ("data", "output_text"),
    )
    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content
        )
    if not isinstance(content, str) or not content.strip():
        raise ModelCallError("文本模型返回内容为空或格式不受支持")
    return content.strip()


async def _download_media(
    client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None
) -> tuple[bytes, str]:
    response = await client.get(url, headers=headers or {})
    if response.is_error:
        raise ModelCallError(f"生成结果下载失败：HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    return response.content, content_type


def _decode_base64(value: str, default_mime: str) -> tuple[bytes, str]:
    mime_type = default_mime
    encoded = value
    if value.startswith("data:") and ";base64," in value:
        prefix, encoded = value.split(",", 1)
        mime_type = prefix[5:].split(";", 1)[0]
    try:
        return base64.b64decode(encoded), mime_type
    except ValueError as exc:
        raise ModelCallError("模型返回的 Base64 数据无效") from exc


async def generate_image(
    config: AiModelConfig, prompt: str, *, size: str = "1024x1024"
) -> tuple[bytes, str]:
    if config.model_type != "IMAGE":
        raise ModelCallError("所选配置不是图片模型")
    payload: dict[str, Any] = {
        "model": config.model_name,
        "prompt": prompt,
        "size": size,
        "n": 1,
        "response_format": "b64_json",
    }
    payload.update(_options(config, "image_options"))
    verify = bool(config.extra_config.get("verify_ssl", True))
    async with httpx.AsyncClient(timeout=_timeout(config, 300), verify=verify) as client:
        response = await client.post(
            _url(config, "image_path", "/images/generations"),
            headers=_headers(config),
            json=payload,
        )
        data = await _json(response)
        encoded = _nested(data, ("data", 0, "b64_json"), ("b64_json",), ("image_base64",))
        if isinstance(encoded, str) and encoded:
            return _decode_base64(encoded, "image/png")
        result_url = _nested(
            data,
            ("data", 0, "url"),
            ("url",),
            ("output", 0, "url"),
            ("data", "url"),
        )
        if isinstance(result_url, str) and result_url:
            return await _download_media(client, result_url)
    raise ModelCallError("图片模型返回格式不受支持，未找到图片数据或下载地址")


async def generate_video(
    config: AiModelConfig,
    prompt: str,
    *,
    duration: float = 10,
    image_data_url: str | None = None,
    image_data_urls: list[str] | None = None,
    request_options: dict[str, Any] | None = None,
    cancelled: Callable[[], bool] | None = None,
    on_submitted: Callable[[str], None] | None = None,
    on_poll: Callable[[str, int], None] | None = None,
) -> tuple[bytes, str]:
    if config.model_type != "VIDEO":
        raise ModelCallError("所选配置不是视频模型")
    is_minimax = _is_minimax_video(config)
    is_ark = _is_ark_video(config)
    is_comfyui = _is_comfyui_video(config)
    normalized_duration: int | float = (
        int(duration) if float(duration).is_integer() else duration
    )
    video_options = _options(config, "video_options")
    video_options.update(request_options or {})
    reference_images = [item for item in (image_data_urls or []) if item]
    if image_data_url and image_data_url not in reference_images:
        reference_images.insert(0, image_data_url)
    if is_comfyui:
        payload: dict[str, Any] = {
            "prompt": prompt,
            "duration": normalized_duration,
        }
        payload.update(video_options)
        configured_fields = config.extra_config.get("reference_fields")
        reference_field = config.extra_config.get("reference_field")
        field_template = str(
            config.extra_config.get("reference_field_template", "ref_image_{index}")
        )
        for index, reference_image in enumerate(reference_images):
            if isinstance(configured_fields, list) and index < len(configured_fields):
                field_name = str(configured_fields[index])
            elif index == 0 and reference_field:
                field_name = str(reference_field)
            else:
                field_name = field_template.format(index=index)
            payload[field_name] = reference_image
    elif is_ark:
        flag_names = {
            "resolution": "rs",
            "ratio": "rt",
            "fps": "fps",
            "seed": "seed",
            "camera_fixed": "cf",
            "watermark": "wm",
        }
        flags = [f"--dur {normalized_duration}"]
        for option, flag in flag_names.items():
            if option in video_options:
                value = video_options.pop(option)
                if isinstance(value, bool):
                    value = str(value).lower()
                flags.append(f"--{flag} {value}")
        content: list[dict[str, Any]] = [
            {"type": "text", "text": f"{prompt} {' '.join(flags)}"}
        ]
        if reference_images:
            content.append(
                {"type": "image_url", "image_url": {"url": reference_images[0]}}
            )
        payload = {
            "model": config.model_name,
            "content": content,
        }
    else:
        payload = {
            "model": config.model_name,
            "prompt": prompt,
            "duration": normalized_duration,
        }
    if reference_images and not is_ark and not is_comfyui:
        default_reference_field = "first_frame_image" if is_minimax else "image"
        payload[
            str(config.extra_config.get("reference_field", default_reference_field))
        ] = reference_images[0]
    if is_minimax and normalized_duration == 10:
        payload["resolution"] = "768P"
    if not is_comfyui:
        payload.update(video_options)
    verify = bool(config.extra_config.get("verify_ssl", True))
    timeout = _timeout(config, 600)
    async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
        response = await client.post(
            _video_url(
                config,
                "video_submit_path",
                "/videos/generations",
                "/video_generation",
                "/contents/generations/tasks",
                "{workflow_id}",
            ),
            headers=_headers(config),
            json=payload,
        )
        if response.headers.get("content-type", "").startswith("video/"):
            return response.content, response.headers["content-type"].split(";", 1)[0]
        data = await _json(response)
        if is_comfyui and str(data.get("code", "")).lower() != "success":
            raise ModelCallError(
                f"视频工作流提交失败：{data.get('msg') or data.get('code') or '未知错误'}"
            )
        direct_b64 = _nested(data, ("b64_json",), ("data", "b64_json"))
        if isinstance(direct_b64, str) and direct_b64:
            return _decode_base64(direct_b64, "video/mp4")
        direct_url = _nested(
            data,
            ("url",),
            ("video_url",),
            ("data", "url"),
            ("data", "video_url"),
            ("output", "url"),
        )
        if isinstance(direct_url, str) and direct_url:
            return await _download_media(client, direct_url)

        provider_task_id = _nested(data, ("id",), ("task_id",), ("data", "id"), ("data", "task_id"))
        if provider_task_id is None:
            message = _nested(
                data,
                ("error", "message"),
                ("base_resp", "status_msg"),
                ("message",),
            )
            if message:
                raise ModelCallError(f"视频生成请求失败：{message}")
            raise ModelCallError("视频模型返回格式不受支持，未找到任务 ID 或视频地址")
        if on_submitted:
            on_submitted(str(provider_task_id))

        status_url = _video_url(
            config,
            "video_status_path",
            "/videos/generations/{task_id}",
            "/query/video_generation?task_id={task_id}",
            "/contents/generations/tasks/{task_id}",
            "result/{task_id}",
        ).replace("{task_id}", str(provider_task_id))
        interval = float(config.extra_config.get("poll_interval", 5))
        max_polls = max(1, int(timeout / max(interval, 0.5)))
        success_statuses = {str(item).lower() for item in config.extra_config.get("success_statuses", ["succeeded", "success", "completed", "done"])}
        failure_statuses = {str(item).lower() for item in config.extra_config.get("failure_statuses", ["fail", "failed", "error", "expired", "cancelled", "canceled"])}

        for poll_index in range(1, max_polls + 1):
            if cancelled and cancelled():
                raise ModelCallError("任务已取消")
            await asyncio.sleep(max(interval, 0.5))
            poll_response = await client.get(status_url, headers=_headers(config))
            poll_data = await _json(poll_response)
            if is_comfyui and str(poll_data.get("code", "")).lower() != "success":
                raise ModelCallError(
                    f"视频工作流查询失败：{poll_data.get('msg') or poll_data.get('code') or '未知错误'}"
                )
            state = str(_nested(poll_data, ("status",), ("data", "status")) or "").lower()
            if on_poll:
                on_poll(state, poll_index)
            result_url = _nested(
                poll_data,
                ("url",),
                ("video_url",),
                ("data", "url"),
                ("data", "video_url"),
                ("output", "url"),
                ("data", "output", "url"),
                ("content", "video_url"),
                ("data", "content", "video_url"),
                ("results", 0, "url"),
                ("data", "results", 0, "url"),
                ("results", 0),
                ("data", "results", 0),
            )
            if isinstance(result_url, str) and result_url and (not state or state in success_statuses):
                return await _download_media(client, result_url)
            file_id = _nested(
                poll_data,
                ("file_id",),
                ("data", "file_id"),
                ("file", "id"),
            )
            if state in success_statuses and file_id is not None:
                file_url = _video_url(
                    config,
                    "video_file_path",
                    "/files/{file_id}",
                    "/files/retrieve?file_id={file_id}",
                    "/files/{file_id}",
                    "files/{file_id}",
                ).replace("{file_id}", str(file_id))
                file_response = await client.get(file_url, headers=_headers(config))
                file_data = await _json(file_response)
                download_url = _nested(
                    file_data,
                    ("file", "download_url"),
                    ("download_url",),
                    ("data", "download_url"),
                    ("data", "file", "download_url"),
                )
                if isinstance(download_url, str) and download_url:
                    return await _download_media(client, download_url)
                raise ModelCallError("视频任务已完成，但未找到成片下载地址")
            if state in failure_statuses:
                message = _nested(
                    poll_data,
                    ("error", "message"),
                    ("error",),
                    ("message",),
                    ("data", "error"),
                    ("base_resp", "status_msg"),
                )
                raise ModelCallError(f"视频生成失败：{message or state}")
        raise ModelCallError("视频生成等待超时")
