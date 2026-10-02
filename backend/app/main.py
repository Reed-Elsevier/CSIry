import json
import os

import boto3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.rag import KB

app = FastAPI(
    title="CSIry API",
    version="0.1.0",
    description="A starter FastAPI backend for CSIry.",
)


class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str | None = None
    messages: list[ChatMessage] | None = None
    model: str | None = None


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Welcome to CSIry API"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items/{item_id}")
def read_item(item_id: int) -> dict[str, int | str]:
    return {"item_id": item_id, "name": "Example item"}


@app.post("/items")
def create_item(item: Item) -> dict[str, object]:
    total = item.price + (item.tax or 0)
    return {
        "message": "Item created",
        "item": item,
        "total": total,
    }


@app.post("/chat")
def chat_with_rag(payload: ChatRequest) -> dict[str, object]:
    if payload.messages:
        chat_messages = [{"role": msg.role, "content": msg.content} for msg in payload.messages]
    elif payload.message:
        chat_messages = [{"role": "user", "content": payload.message}]
    else:
        raise HTTPException(status_code=400, detail="Either 'message' or 'messages' must be provided.")

    last_user_message = next(
        (msg["content"] for msg in reversed(chat_messages) if msg["role"] == "user"),
        "",
    )
    if not last_user_message:
        raise HTTPException(status_code=400, detail="A user message is required for the chat request.")

    model = payload.model or os.getenv("AWS_BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
    bedrock_auth = bool(os.getenv("AWS_BEARER_TOKEN_BEDROCK")) or (
        bool(os.getenv("AWS_ACCESS_KEY_ID")) and bool(os.getenv("AWS_SECRET_ACCESS_KEY"))
    )
    if not bedrock_auth and not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="No LLM credentials configured. Set AWS_BEARER_TOKEN_BEDROCK, AWS credentials/profile, or OPENAI_API_KEY.",
        )

    rag_context = None
    rag_result = None
    try:
        kb = KB()
        rag_result = kb.ask(last_user_message)
        rag_context = rag_result.get("answer")
    except Exception:
        rag_context = None

    llm_messages: list[dict[str, str]] = []
    if rag_context:
        llm_messages.append(
            {
                "role": "system",
                "content": (
                    "Use the following internal knowledge context for the latest question. "
                    "Keep answers grounded in this context when it is relevant.\n\n"
                    f"Context:\n{rag_context}"
                ),
            }
        )
    llm_messages.extend(chat_messages)

    try:
        if os.getenv("AWS_BEARER_TOKEN_BEDROCK") or (
            os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")
        ):
            session_kwargs = {}
            if os.getenv("AWS_PROFILE"):
                session_kwargs["profile_name"] = os.getenv("AWS_PROFILE")
            session = boto3.Session(**session_kwargs)
            client_kwargs = {"region_name": os.getenv("AWS_REGION", "us-east-1")}
            if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
                client_kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID")
                client_kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY")
                if os.getenv("AWS_SESSION_TOKEN"):
                    client_kwargs["aws_session_token"] = os.getenv("AWS_SESSION_TOKEN")

            client = session.client("bedrock-runtime", **client_kwargs)
            system_prompts = [msg["content"] for msg in llm_messages if msg["role"] == "system"]
            bedrock_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1200,
                "messages": [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in llm_messages
                    if msg["role"] != "system"
                ],
                "temperature": 0.2,
            }
            if system_prompts:
                bedrock_body["system"] = "\n".join(system_prompts)
            response = client.invoke_model(
                modelId=model,
                body=json.dumps(bedrock_body),
                contentType="application/json",
                accept="application/json",
            )
            response_payload = json.loads(response["body"].read())
            reply = response_payload["content"][0]["text"] if response_payload.get("content") else "No response returned."
        else:
            from openai import OpenAI

            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=model,
                messages=llm_messages,
                temperature=0.2,
            )
            reply = response.choices[0].message.content or "No response returned."

        return {"reply": reply}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM chat request failed: {str(exc)}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
