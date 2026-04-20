#!/usr/bin/env python3
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_model_aliases() -> dict:
    raw = os.getenv("MODEL_ALIASES", "").strip()
    if not raw:
        return {}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid MODEL_ALIASES JSON: {e}") from e

    if not isinstance(data, dict):
        raise RuntimeError("MODEL_ALIASES must be a JSON object")

    normalized = {}
    for alias_name, cfg in data.items():
        if not isinstance(alias_name, str) or not alias_name.strip():
            raise RuntimeError("MODEL_ALIASES keys must be non-empty strings")

        if not isinstance(cfg, dict):
            raise RuntimeError(f"MODEL_ALIASES['{alias_name}'] must be an object")

        upstream_model = cfg.get("upstream_model")
        if not isinstance(upstream_model, str) or not upstream_model.strip():
            raise RuntimeError(
                f"MODEL_ALIASES['{alias_name}'].upstream_model must be a non-empty string"
            )

        item = {
            "upstream_model": upstream_model.strip(),
        }

        reasoning_effort = cfg.get("reasoning_effort")
        if reasoning_effort is not None:
            if not isinstance(reasoning_effort, str) or not reasoning_effort.strip():
                raise RuntimeError(
                    f"MODEL_ALIASES['{alias_name}'].reasoning_effort must be a non-empty string when provided"
                )
            item["reasoning_effort"] = reasoning_effort.strip()

        normalized[alias_name.strip()] = item

    return normalized


UPSTREAM_BASE = os.getenv("UPSTREAM_BASE", "https://api.openai.com/v1").rstrip("/")
UPSTREAM_API_KEY = os.getenv("UPSTREAM_API_KEY", "").strip()
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "600"))

PROXY_API_TOKEN = os.getenv("PROXY_API_TOKEN", "").strip()
REQUIRE_PROXY_AUTH = env_bool("REQUIRE_PROXY_AUTH", True)

MODELS_CACHE_TTL = int(os.getenv("MODELS_CACHE_TTL", "30"))
MODEL_ALIASES = load_model_aliases()

app_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    timeout = httpx.Timeout(REQUEST_TIMEOUT)
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
    client = httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        limits=limits,
        http2=True,
    )
    app_state["client"] = client
    app_state["models_cache"] = {
        "expires_at": 0.0,
        "payload": None,
    }
    yield
    await client.aclose()


app = FastAPI(
    title="OpenAI-Compatible Alias Proxy",
    version="1.6.0",
    lifespan=lifespan,
)


def get_client() -> httpx.AsyncClient:
    return app_state["client"]


def get_models_cache() -> dict:
    return app_state["models_cache"]


def is_json_request(content_type: str) -> bool:
    return "application/json" in (content_type or "").lower()


def authorize_proxy(request: Request) -> None:
    if not REQUIRE_PROXY_AUTH:
        return

    if not PROXY_API_TOKEN:
        raise HTTPException(status_code=500, detail="Server proxy token is not configured")

    auth = request.headers.get("authorization", "")
    prefix = "Bearer "
    if not auth.startswith(prefix):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    provided = auth[len(prefix):].strip()
    if not secrets.compare_digest(provided, PROXY_API_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid bearer token")


def apply_model_policy(payload: dict) -> dict:
    model_name = payload.get("model")
    if not isinstance(model_name, str):
        return payload

    alias_cfg = MODEL_ALIASES.get(model_name)
    if not alias_cfg:
        return payload

    payload = dict(payload)
    payload["model"] = alias_cfg["upstream_model"]

    if payload.get("reasoning_effort") is not None:
        return payload

    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict) and reasoning.get("effort") is not None:
        return payload

    alias_effort = alias_cfg.get("reasoning_effort")
    if alias_effort is None:
        return payload

    payload["reasoning_effort"] = alias_effort

    if not isinstance(reasoning, dict):
        payload["reasoning"] = {"effort": alias_effort}
    else:
        reasoning = dict(reasoning)
        if reasoning.get("effort") is None:
            reasoning["effort"] = alias_effort
        payload["reasoning"] = reasoning

    return payload


def patch_payload(payload: dict) -> dict:
    return apply_model_policy(payload)


def filter_hop_by_hop_headers(headers: httpx.Headers) -> dict:
    excluded = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
    }
    return {k: v for k, v in headers.items() if k.lower() not in excluded}


def build_upstream_headers(request: Request, body: bytes | None = None) -> dict:
    headers = dict(request.headers)

    headers.pop("host", None)
    headers.pop("content-length", None)

    if body is not None:
        headers["content-length"] = str(len(body))

    if UPSTREAM_API_KEY:
        headers["authorization"] = f"Bearer {UPSTREAM_API_KEY}"
    else:
        headers.pop("authorization", None)

    return headers


def should_stream(request: Request, patched_body: bytes) -> bool:
    accept = request.headers.get("accept", "").lower()
    if "text/event-stream" in accept:
        return True

    if not patched_body:
        return False

    try:
        data = json.loads(patched_body.decode("utf-8"))
        return isinstance(data, dict) and data.get("stream") is True
    except Exception:
        return False


async def stream_bytes(resp: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in resp.aiter_bytes():
            yield chunk
    finally:
        await resp.aclose()


def alias_to_model_object(alias_name: str, cfg: dict) -> dict:
    return {
        "id": alias_name,
        "object": "model",
        "owned_by": "alias-proxy",
        "metadata": {
            "alias": True,
            "upstream_model": cfg.get("upstream_model"),
            "reasoning_effort": cfg.get("reasoning_effort"),
        },
    }


def merge_models_payload(upstream_payload: dict) -> dict:
    if not isinstance(upstream_payload, dict):
        upstream_payload = {"object": "list", "data": []}

    data = upstream_payload.get("data")
    if not isinstance(data, list):
        data = []

    merged = list(data)
    existing_ids = {
        item.get("id")
        for item in merged
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    for alias_name, cfg in MODEL_ALIASES.items():
        if alias_name not in existing_ids:
            merged.append(alias_to_model_object(alias_name, cfg))

    upstream_payload["object"] = upstream_payload.get("object", "list")
    upstream_payload["data"] = merged
    return upstream_payload


async def fetch_upstream_models(request: Request) -> dict:
    client = get_client()

    upstream_url = f"{UPSTREAM_BASE}/models"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    upstream_request = client.build_request(
        method="GET",
        url=upstream_url,
        headers=build_upstream_headers(request),
    )

    upstream_response = await client.send(upstream_request, stream=False)
    try:
        body = await upstream_response.aread()
        if upstream_response.status_code >= 400:
            raise HTTPException(
                status_code=upstream_response.status_code,
                detail=body.decode("utf-8", errors="replace"),
            )

        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            payload = {"object": "list", "data": []}

        return merge_models_payload(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Invalid JSON from upstream /models")
    finally:
        await upstream_response.aclose()


async def get_cached_models(request: Request) -> dict:
    cache = get_models_cache()
    now = time.time()

    if cache["payload"] is not None and now < cache["expires_at"]:
        return cache["payload"]

    payload = await fetch_upstream_models(request)
    cache["payload"] = payload
    cache["expires_at"] = now + MODELS_CACHE_TTL
    return payload


@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "Welcome to the OpenAI API! Documentation is available at https://platform.openai.com/docs/api-reference"
    }


@app.get("/healthz", tags=["meta"])
async def healthz():
    cache = get_models_cache()
    ttl_left = max(0, int(cache["expires_at"] - time.time())) if cache["payload"] is not None else 0

    return {
        "ok": True,
        "upstream_base": UPSTREAM_BASE,
        "proxy_auth_required": REQUIRE_PROXY_AUTH,
        "upstream_api_key_configured": bool(UPSTREAM_API_KEY),
        "models_cache_ttl": MODELS_CACHE_TTL,
        "models_cache_remaining": ttl_left,
        "aliases_count": len(MODEL_ALIASES),
        "aliases": MODEL_ALIASES,
    }


@app.get("/v1/models", tags=["v1"])
async def list_models(request: Request):
    authorize_proxy(request)
    payload = await get_cached_models(request)
    return JSONResponse(content=payload)


@app.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy_v1(path: str, request: Request):
    authorize_proxy(request)

    if path == "models" and request.method.upper() == "GET":
        return await list_models(request)

    client = get_client()
    raw_body = await request.body()
    content_type = request.headers.get("content-type", "")
    outbound_body = raw_body

    if raw_body and is_json_request(content_type):
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            if isinstance(parsed, dict):
                patched = patch_payload(parsed)
                outbound_body = json.dumps(patched, ensure_ascii=False).encode("utf-8")
        except Exception:
            outbound_body = raw_body

    upstream_url = f"{UPSTREAM_BASE}/{path}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    upstream_request = client.build_request(
        method=request.method,
        url=upstream_url,
        headers=build_upstream_headers(request, outbound_body),
        content=outbound_body,
    )

    upstream_response = await client.send(upstream_request, stream=True)
    response_headers = filter_hop_by_hop_headers(upstream_response.headers)
    media_type = upstream_response.headers.get("content-type")

    if should_stream(request, outbound_body):
        return StreamingResponse(
            stream_bytes(upstream_response),
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=media_type,
        )

    try:
        body = await upstream_response.aread()
        return Response(
            content=body,
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=media_type,
        )
    finally:
        await upstream_response.aclose()


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def reject_non_v1(path: str):
    return JSONResponse(
        status_code=404,
        content={"error": "Not found"},
    )
