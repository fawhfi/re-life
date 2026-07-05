"""Debug a custom Re-Life AI endpoint without going through the web UI."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


DEFAULT_PROMPT = (
    "Identify this item for a recycling app. Respond with ONLY one JSON object "
    "with fields: name, category, description, ecoRate, recycleRate, material, "
    "disposalGuide, precaution, weightedScores."
)

ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def openai_chat_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def anthropic_messages_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/messages"):
        return base
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/v1/messages"


def preview(value: str, limit: int = 1200) -> str:
    text = (value or "").replace("\r", "\\r").replace("\n", "\\n")
    if len(text) > limit:
        return text[:limit] + "...<truncated>"
    return text


def print_debug(**fields) -> None:
    parts = []
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={preview(str(value), 500)}")
    print("[Custom Endpoint Debug] " + " ".join(parts))


def load_image(path: str | None) -> tuple[bytes, str]:
    if not path:
        return ONE_PIXEL_PNG, "image/png"

    image_path = Path(path)
    data = image_path.read_bytes()
    suffix = image_path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    return data, mime


def build_openai_payload(model: str, prompt: str, image_b64: str, mime: str) -> dict:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are an environmental packaging evaluator. Respond with ONLY a single JSON object.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ],
            },
        ],
        "max_tokens": 8192,
        "temperature": 0.6,
        "stream": False,
    }


def build_anthropic_payload(model: str, prompt: str, image_b64: str, mime: str) -> dict:
    return {
        "model": model,
        "max_tokens": 8192,
        "system": "You are an environmental packaging evaluator. Respond with ONLY a single JSON object.",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": image_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    }


def inspect_openai_response(data: object) -> int:
    if not isinstance(data, dict):
        print_debug(error="top-level JSON is not an object", json_type=type(data).__name__)
        return 2
    choices = data.get("choices")
    print_debug(json_keys=",".join(data.keys()), choices_len=len(choices) if isinstance(choices, list) else "missing")
    try:
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        print_debug(error="missing choices[0].message.content", error_type=exc.__class__.__name__)
        return 2
    print_debug(model_content_preview=content)
    try:
        parsed_content = json.loads(content)
        print_debug(model_content_json_keys=",".join(parsed_content.keys()) if isinstance(parsed_content, dict) else type(parsed_content).__name__)
    except ValueError as exc:
        print_debug(model_content_json_error=str(exc))
    return 0


def inspect_anthropic_response(data: object) -> int:
    if not isinstance(data, dict):
        print_debug(error="top-level JSON is not an object", json_type=type(data).__name__)
        return 2
    blocks = data.get("content")
    print_debug(json_keys=",".join(data.keys()), content_blocks=len(blocks) if isinstance(blocks, list) else "missing")
    text = "".join(
        block.get("text", "")
        for block in blocks or []
        if isinstance(block, dict)
    )
    if not text:
        print_debug(error="missing Anthropic content text")
        return 2
    print_debug(model_content_preview=text)
    try:
        parsed_content = json.loads(text)
        print_debug(model_content_json_keys=",".join(parsed_content.keys()) if isinstance(parsed_content, dict) else type(parsed_content).__name__)
    except ValueError as exc:
        print_debug(model_content_json_error=str(exc))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug Re-Life custom AI endpoint config and response shape.")
    parser.add_argument("--env-file", default=".env", help="Path to env file. Defaults to .env")
    parser.add_argument("--image", help="Optional image path. Defaults to a 1x1 PNG test image.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--method", choices=["openai", "anthropic"], default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    load_dotenv(args.env_file)

    base_url = args.base_url or os.getenv("CUSTOM_BASE_URL", "")
    api_key = args.api_key or os.getenv("CUSTOM_API", "")
    method = (args.method or os.getenv("CUSTOM_ENDPOINT_METHOD", "openai")).strip().lower()
    model = args.model or os.getenv("CUSTOM_ENDPOINT_MODEL", "")

    if not base_url or not api_key or not model:
        print_debug(
            error="missing config",
            base_url="SET" if base_url else "UNSET",
            api_key="SET" if api_key else "UNSET",
            model="SET" if model else "UNSET",
        )
        return 2

    image_bytes, mime = load_image(args.image)
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    if method == "openai":
        url = openai_chat_url(base_url)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = build_openai_payload(model, args.prompt, image_b64, mime)
    else:
        url = anthropic_messages_url(base_url)
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        payload = build_anthropic_payload(model, args.prompt, image_b64, mime)

    print_debug(
        method=method,
        url=url,
        model=model,
        api_key="SET",
        image_mime=mime,
        image_bytes=len(image_bytes),
        image_b64_len=len(image_b64),
        prompt_len=len(args.prompt),
    )

    try:
        with httpx.Client(timeout=args.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
    except Exception as exc:
        print_debug(error="request failed", error_type=exc.__class__.__name__, message=str(exc))
        return 1

    body = response.text or ""
    body_preview = preview(body)
    print_debug(
        status_code=response.status_code,
        content_type=response.headers.get("content-type", ""),
        body_len=len(body),
        body_preview=body_preview,
    )

    if response.status_code >= 400:
        return 1

    try:
        data = response.json()
    except ValueError as exc:
        print_debug(error="response is not JSON", error_type=exc.__class__.__name__, message=str(exc))
        return 2

    if method == "openai":
        return inspect_openai_response(data)
    return inspect_anthropic_response(data)


if __name__ == "__main__":
    raise SystemExit(main())
