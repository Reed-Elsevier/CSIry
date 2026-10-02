import io
import json

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


@pytest.fixture
def bedrock(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    calls: dict[str, object] = {}

    class FakeBedrockClient:
        def invoke_model(self, **kwargs: object) -> dict[str, io.BytesIO]:
            calls["request"] = kwargs
            if "error" in calls:
                raise calls["error"]
            body = io.BytesIO(json.dumps({"content": [{"text": "Test reply"}]}).encode())
            return {"body": body}

    class FakeSession:
        def __init__(self, **kwargs: object) -> None:
            calls["session_kwargs"] = kwargs

        def client(self, service_name: str, **kwargs: object) -> FakeBedrockClient:
            calls["service_name"] = service_name
            return FakeBedrockClient()

    monkeypatch.setattr(main.boto3, "Session", FakeSession)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "test-token")
    monkeypatch.setenv("AWS_BEDROCK_MODEL_ID", "test-model")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return calls


@pytest.fixture
def fake_kb(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    questions: list[str] = []

    class FakeKB:
        def ask(self, question: str) -> dict[str, object]:
            questions.append(question)
            return {
                "answer": "Grounding context",
                "sources": ["KB000001"],
                "conflicts": [],
                "invalid_citations": [],
            }

    monkeypatch.setattr(main, "KB", FakeKB)
    return questions


def test_chat_single_message_returns_only_reply(
    client: TestClient, bedrock: dict[str, object], fake_kb: list[str]
) -> None:
    response = client.post("/chat", json={"message": "How do I request access?"})

    assert response.status_code == 200
    assert response.json() == {"reply": "Test reply"}
    assert fake_kb == ["How do I request access?"]
    request = bedrock["request"]
    assert isinstance(request, dict)
    assert request["modelId"] == "test-model"
    assert bedrock["service_name"] == "bedrock-runtime"


def test_chat_history_uses_latest_question_and_keeps_rag_context(
    client: TestClient, bedrock: dict[str, object], fake_kb: list[str]
) -> None:
    response = client.post(
        "/chat",
        json={
            "messages": [
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
                {"role": "user", "content": "Follow-up question"},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"reply": "Test reply"}
    assert fake_kb == ["Follow-up question"]

    request = bedrock["request"]
    assert isinstance(request, dict)
    body = json.loads(request["body"])
    assert body["system"].endswith("Context:\nGrounding context")
    assert body["messages"] == [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
        {"role": "user", "content": "Follow-up question"},
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"messages": [{"role": "assistant", "content": "No user message"}]},
        {"message": "", "messages": []},
    ],
)
def test_chat_rejects_requests_without_a_user_message(
    client: TestClient, payload: dict[str, object]
) -> None:
    response = client.post("/chat", json=payload)

    assert response.status_code == 400


def test_chat_requires_model_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 500
    assert "No LLM credentials configured" in response.json()["detail"]


def test_chat_reports_bedrock_invocation_failure(
    client: TestClient, bedrock: dict[str, object], fake_kb: list[str]
) -> None:
    bedrock["error"] = RuntimeError("Bedrock unavailable")

    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 500
    assert "Bedrock unavailable" in response.json()["detail"]