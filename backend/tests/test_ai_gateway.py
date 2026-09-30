import asyncio

import httpx

from app.models.workflow import AiModelConfig
from app.services import ai_gateway


def _video_config() -> AiModelConfig:
    return AiModelConfig(
        name="MiniMax 视频",
        model_type="VIDEO",
        provider="MiniMax",
        base_url="https://example.test/api/v1/minimax/v1/video_generation",
        model_name="MiniMax-Hailuo-02",
        extra_config={},
        status="ENABLED",
        is_default=False,
        created_by=1,
    )


def _comfyui_config() -> AiModelConfig:
    return AiModelConfig(
        name="AutoDL ComfyUI 视频",
        model_type="VIDEO",
        provider="AutoDL ComfyUI",
        base_url="https://autodl.art/api/v1/comfyui/comfyui_workflow",
        model_name="minimax_h3_lightx2v_no_pic",
        api_key_env="COMFYUI_TEST_TOKEN",
        extra_config={
            "protocol": "COMFYUI",
            "poll_interval": 1,
            "video_options": {"resolution": "768p竖"},
        },
        status="ENABLED",
        is_default=False,
        created_by=1,
    )


def _response(status_code: int, url: str, **kwargs) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("GET", url),
        **kwargs,
    )


def _text_config(model_name: str = "DeepSeek-V4.1-Flash") -> AiModelConfig:
    return AiModelConfig(
        name="文本模型",
        model_type="TEXT",
        provider="AutoDL",
        base_url="https://example.test/api/v1",
        model_name=model_name,
        extra_config={},
        status="ENABLED",
        is_default=True,
        created_by=1,
    )


def test_connection_verifies_configured_model_name(monkeypatch) -> None:
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, *, headers):
            return _response(
                200,
                url,
                json={"data": [{"id": "DeepSeek-V4.1-Flash"}]},
            )

    monkeypatch.setattr(ai_gateway.httpx, "AsyncClient", lambda **_: FakeClient())

    message = asyncio.run(ai_gateway.test_model_connection(_text_config()))
    assert message == "连接成功，认证信息和模型名称有效"

    try:
        asyncio.run(ai_gateway.test_model_connection(_text_config("missing-model")))
    except ai_gateway.ModelCallError as exc:
        assert "不在服务商的可用模型列表中" in str(exc)
    else:
        raise AssertionError("不存在的模型名称应导致连接测试失败")


def test_minimax_connection_uses_non_billable_validation(monkeypatch) -> None:
    captured: dict = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, *, headers, json):
            captured.update(url=url, payload=json)
            return _response(
                406,
                url,
                json={"error": {"message": "prompt can't be empty"}},
            )

    monkeypatch.setattr(ai_gateway.httpx, "AsyncClient", lambda **_: FakeClient())

    message = asyncio.run(ai_gateway.test_model_connection(_video_config()))

    assert message == "连接成功，视频接口、认证和模型名称有效"
    assert captured == {
        "url": "https://example.test/api/v1/minimax/v1/video_generation",
        "payload": {"model": "MiniMax-Hailuo-02"},
    }


def test_minimax_video_generation_poll_and_download(monkeypatch) -> None:
    captured: dict = {"get_urls": []}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, *, headers, json):
            captured.update(post_url=url, payload=json)
            return _response(200, url, json={"task_id": "task-1"})

        async def get(self, url, *, headers):
            captured["get_urls"].append(url)
            if "/query/video_generation" in url:
                return _response(
                    200,
                    url,
                    json={"status": "Success", "file_id": "file-1"},
                )
            if "/files/retrieve" in url:
                return _response(
                    200,
                    url,
                    json={"file": {"download_url": "https://cdn.test/video.mp4"}},
                )
            return _response(
                200,
                url,
                content=b"video-bytes",
                headers={"content-type": "video/mp4"},
            )

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(ai_gateway.httpx, "AsyncClient", lambda **_: FakeClient())
    monkeypatch.setattr(ai_gateway.asyncio, "sleep", no_sleep)

    content, mime_type = asyncio.run(
        ai_gateway.generate_video(
            _video_config(),
            "雨夜城市中的追逐镜头",
            duration=10,
            image_data_url="data:image/png;base64,AAAA",
        )
    )

    assert content == b"video-bytes"
    assert mime_type == "video/mp4"
    assert captured["post_url"].endswith("/minimax/v1/video_generation")
    assert captured["payload"] == {
        "model": "MiniMax-Hailuo-02",
        "prompt": "雨夜城市中的追逐镜头",
        "duration": 10,
        "first_frame_image": "data:image/png;base64,AAAA",
        "resolution": "768P",
    }
    assert captured["get_urls"] == [
        "https://example.test/api/v1/minimax/v1/query/video_generation?task_id=task-1",
        "https://example.test/api/v1/minimax/v1/files/retrieve?file_id=file-1",
        "https://cdn.test/video.mp4",
    ]


def test_comfyui_connection_uses_workflow_validation(monkeypatch) -> None:
    captured: dict = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, payload=json)
            return _response(
                200,
                url,
                json={
                    "code": "RequestParameterIsWrong",
                    "data": None,
                    "msg": "缺少必填参数：prompt",
                },
            )

    monkeypatch.setenv("COMFYUI_TEST_TOKEN", "test-token")
    monkeypatch.setattr(ai_gateway.httpx, "AsyncClient", lambda **_: FakeClient())

    message = asyncio.run(ai_gateway.test_model_connection(_comfyui_config()))

    assert message == "连接成功，ComfyUI Token 和工作流 ID 有效"
    assert captured["url"] == (
        "https://autodl.art/api/v1/comfyui/comfyui_workflow/"
        "minimax_h3_lightx2v_no_pic"
    )
    assert captured["headers"]["Authorization"] == "test-token"
    assert captured["payload"] == {
        "prompt": "",
        "duration": 1,
        "resolution": "768p竖",
    }


def test_comfyui_video_submit_poll_and_download(monkeypatch) -> None:
    captured: dict = {"get_urls": [], "statuses": []}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, *, headers, json):
            captured.update(post_url=url, headers=headers, payload=json)
            return _response(
                200,
                url,
                json={"code": "Success", "data": {"task_id": "task-1"}},
            )

        async def get(self, url, *, headers):
            captured["get_urls"].append(url)
            if "/result/" in url:
                return _response(
                    200,
                    url,
                    json={
                        "code": "Success",
                        "data": {
                            "status": "SUCCESS",
                            "results": ["https://cdn.test/video.mp4"],
                        },
                    },
                )
            return _response(
                200,
                url,
                content=b"comfyui-video",
                headers={"content-type": "video/mp4"},
            )

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setenv("COMFYUI_TEST_TOKEN", "test-token")
    monkeypatch.setattr(ai_gateway.httpx, "AsyncClient", lambda **_: FakeClient())
    monkeypatch.setattr(ai_gateway.asyncio, "sleep", no_sleep)

    config = _comfyui_config()
    config.model_name = "minimax_h3_image_audio_to_video_v2_15s"
    content, mime_type = asyncio.run(
        ai_gateway.generate_video(
            config,
            "云端漫步的小猫",
            duration=15,
            image_data_urls=[
                "data:image/png;base64,AAAA",
                "data:image/webp;base64,BBBB",
            ],
            request_options={"resolution": "480p横", "seed": 12345},
            on_submitted=lambda task_id: captured.update(task_id=task_id),
            on_poll=lambda status, index: captured["statuses"].append((status, index)),
        )
    )

    assert content == b"comfyui-video"
    assert mime_type == "video/mp4"
    assert captured["post_url"].endswith(
        "/comfyui/comfyui_workflow/minimax_h3_image_audio_to_video_v2_15s"
    )
    assert captured["headers"]["Authorization"] == "test-token"
    assert captured["payload"] == {
        "prompt": "云端漫步的小猫",
        "duration": 15,
        "resolution": "480p横",
        "seed": 12345,
        "ref_image_0": "data:image/png;base64,AAAA",
        "ref_image_1": "data:image/webp;base64,BBBB",
    }
    assert captured["task_id"] == "task-1"
    assert captured["statuses"] == [("success", 1)]
    assert captured["get_urls"] == [
        "https://autodl.art/api/v1/comfyui/comfyui_workflow/result/task-1",
        "https://cdn.test/video.mp4",
    ]


def test_provider_quota_error_is_translated() -> None:
    response = _response(
        402,
        "https://example.test/chat/completions",
        json={
            "error": {
                "message": (
                    "The free trial quota for the service has been exhausted and "
                    "postpaid billing is not enabled"
                ),
                "code": "401008",
            }
        },
    )

    try:
        asyncio.run(ai_gateway._json(response))
    except ai_gateway.ModelCallError as exc:
        message = str(exc)
    else:
        raise AssertionError("额度错误应抛出 ModelCallError")

    assert "模型服务额度已用尽且未开启后付费" in message
