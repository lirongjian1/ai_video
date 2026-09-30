from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_rejects_wrong_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_project_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "雪夜寻师妹", "description": "古风短片", "status": "ACTIVE"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    listing = client.get("/api/v1/projects", headers=auth_headers)
    assert listing.status_code == 200
    assert any(item["id"] == project_id for item in listing.json()["items"])

    updated = client.put(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
        json={"name": "雪夜古寺"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "雪夜古寺"


def test_user_and_file_flow(client: TestClient, auth_headers: dict[str, str]) -> None:
    user = client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "username": "editor",
            "nickname": "剪辑师",
            "password": "editor123",
            "status": "ENABLED",
        },
    )
    assert user.status_code in {201, 409}

    uploaded = client.post(
        "/api/v1/files/upload",
        headers=auth_headers,
        files={"upload": ("reference.png", b"fake-png", "image/png")},
    )
    assert uploaded.status_code == 201
    file_id = uploaded.json()["id"]

    renamed = client.put(
        f"/api/v1/files/{file_id}",
        headers=auth_headers,
        json={"file_name": "角色参考图.png"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["file_name"] == "角色参考图.png"

    deleted = client.delete(f"/api/v1/files/{file_id}", headers=auth_headers)
    assert deleted.status_code == 200


def test_workflow_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    project = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "工作流测试", "status": "ACTIVE"},
    ).json()

    model = client.post(
        "/api/v1/model-configs",
        headers=auth_headers,
        json={
            "name": "本地文本模型",
            "model_type": "TEXT",
            "provider": "OpenAI Compatible",
            "model_name": "demo-model",
            "is_default": True,
        },
    )
    assert model.status_code == 201
    assert model.json()["is_default"] is True

    prompt = client.post(
        "/api/v1/prompts",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "name": "角色提示词",
            "prompt_type": "CHARACTER",
            "content": "一个沉稳的剑客",
        },
    )
    assert prompt.status_code == 201

    character = client.post(
        "/api/v1/characters",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "name": "沈砚",
            "appearance": "黑衣长剑",
            "prompt_id": prompt.json()["id"],
        },
    )
    assert character.status_code == 201

    scene = client.post(
        "/api/v1/scenes",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "name": "雪夜古寺",
            "environment": "深夜大雪",
        },
    )
    assert scene.status_code == 201

    script = client.post(
        "/api/v1/scripts",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "title": "雪夜寻人",
            "content": "剑客来到古寺。",
            "duration": 30,
        },
    )
    assert script.status_code == 201

    storyboard = client.post(
        "/api/v1/storyboards",
        headers=auth_headers,
        json={
            "script_id": script.json()["id"],
            "sequence": 1,
            "title": "抵达古寺",
            "duration": 5,
            "scene_id": scene.json()["id"],
            "character_ids": [character.json()["id"]],
        },
    )
    assert storyboard.status_code == 201

    scripts = client.get("/api/v1/scripts", headers=auth_headers)
    assert scripts.status_code == 200
    created_script = next(item for item in scripts.json()["items"] if item["id"] == script.json()["id"])
    assert created_script["storyboard_count"] == 1

    task = client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "name": "分镜文案生成",
            "task_type": "TEXT",
            "model_config_id": model.json()["id"],
            "target_type": "STORYBOARD",
            "target_id": storyboard.json()["id"],
        },
    )
    assert task.status_code == 201
    cancelled = client.post(
        f"/api/v1/tasks/{task.json()['id']}/cancel", headers=auth_headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"


def test_ai_generation_workflow(
    client: TestClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    async def fake_text(_, system_prompt: str, __: str, **___) -> str:
        if "6 个分镜" in system_prompt:
            return """{
              "summary": "一次雪夜寻人",
              "content": "剑客进入古寺并找到线索。",
              "shots": [
                {"title":"抵达","description":"剑客抵达古寺","camera":"远景推进","dialogue":"","video_prompt":"雪夜古寺，剑客走近，远景推进"},
                {"title":"入寺","description":"推门进入","camera":"中景跟拍","dialogue":"有人吗","video_prompt":"剑客推开寺门，中景跟拍"},
                {"title":"发现","description":"发现脚印","camera":"俯拍特写","dialogue":"","video_prompt":"雪地脚印，俯拍特写"},
                {"title":"追踪","description":"沿脚印前进","camera":"侧面移动","dialogue":"","video_prompt":"剑客沿脚印奔跑，侧面移动"},
                {"title":"对峙","description":"院中对峙","camera":"环绕中景","dialogue":"放开她","video_prompt":"古寺院中对峙，环绕中景"},
                {"title":"结尾","description":"晨光照入","camera":"全景拉远","dialogue":"","video_prompt":"晨光中的古寺，全景拉远"}
              ]
            }"""
        return "同一角色定妆三视图，正面、侧面、背面，全身，统一服装，纯净背景"

    async def fake_image(*_, **__) -> tuple[bytes, str]:
        return b"generated-image", "image/png"

    async def fake_translation(*_, **__) -> str:
        return "adult swordsman character sheet, front side and rear views"

    video_calls: list[dict] = []

    async def fake_video(_, prompt: str, **kwargs) -> tuple[bytes, str]:
        video_calls.append({"prompt": prompt, **kwargs})
        return b"generated-video", "video/mp4"

    monkeypatch.setattr("app.api.workflow.generate_text", fake_text)
    monkeypatch.setattr("app.services.generation.generate_text", fake_translation)
    monkeypatch.setattr("app.services.generation.generate_image", fake_image)
    monkeypatch.setattr("app.services.generation.generate_video", fake_video)

    project = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "AI 生成链路", "status": "ACTIVE"},
    ).json()

    def create_model(name: str, model_type: str) -> dict:
        response = client.post(
            "/api/v1/model-configs",
            headers=auth_headers,
            json={
                "name": name,
                "model_type": model_type,
                "provider": "Test",
                "base_url": "https://example.invalid/v1",
                "model_name": f"test-{model_type.lower()}",
                "api_key": "secret-test-key",
            },
        )
        assert response.status_code == 201
        assert response.json()["has_api_key"] is True
        assert "secret-test-key" not in response.text
        assert "api_key_env" not in response.json()
        assert "api_key_encrypted" not in response.json()
        return response.json()

    text_model = create_model("测试文本模型", "TEXT")
    image_model = create_model("测试图片模型", "IMAGE")
    video_model = create_model("测试视频模型", "VIDEO")

    prompt = client.post(
        "/api/v1/prompts/generate",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "name": "剑客三视图",
            "generation_type": "CHARACTER_THREE_VIEW",
            "keywords": "青年剑客，黑衣，银色发冠",
            "model_config_id": text_model["id"],
        },
    )
    assert prompt.status_code == 201
    assert "三视图" in prompt.json()["content"]

    script = client.post(
        "/api/v1/scripts/generate",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "title": "雪夜古寺",
            "keywords": "剑客在雪夜古寺寻找失踪同伴",
            "model_config_id": text_model["id"],
        },
    )
    assert script.status_code == 201
    assert script.json()["storyboard_count"] == 6

    image_task = client.post(
        "/api/v1/images/generate",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "prompt_id": prompt.json()["id"],
            "name": "剑客定妆",
            "model_config_id": image_model["id"],
        },
    )
    assert image_task.status_code == 201
    reference_image = client.get(
        "/api/v1/files",
        headers=auth_headers,
        params={"project_id": project["id"], "file_type": "IMAGE", "page_size": 100},
    ).json()["items"][0]

    boards = client.get(
        "/api/v1/storyboards",
        headers=auth_headers,
        params={"script_id": script.json()["id"]},
    ).json()["items"]
    assert len(boards) == 6
    video_task = client.post(
        f"/api/v1/storyboards/{boards[0]['id']}/generate-video",
        headers=auth_headers,
        json={
            "model_config_id": video_model["id"],
            "reference_file_ids": [reference_image["id"]],
            "duration": 15,
            "resolution": "480p横",
            "seed": 12345,
        },
    )
    assert video_task.status_code == 201
    assert video_task.json()["request_payload"] == {
        "reference_file_ids": [reference_image["id"]],
        "duration": 15,
        "resolution": "480p横",
        "seed": 12345,
    }
    updated_board = client.get(
        "/api/v1/storyboards",
        headers=auth_headers,
        params={"script_id": script.json()["id"]},
    ).json()["items"][0]
    assert updated_board["reference_file_ids"] == [reference_image["id"]]
    assert "严格参考所提供的人物、动物主体和场景参考图" in video_calls[0]["prompt"]
    assert "雪夜古寺" in video_calls[0]["prompt"]
    assert video_calls[0]["image_data_urls"]

    generated_files = client.get(
        "/api/v1/files",
        headers=auth_headers,
        params={"project_id": project["id"], "page_size": 100},
    ).json()["items"]
    assert {item["source_type"] for item in generated_files} >= {"AI_IMAGE", "AI_VIDEO"}

