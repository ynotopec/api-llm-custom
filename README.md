# OpenAI-Compatible Alias Proxy

FastAPI proxy for OpenAI-compatible `/v1/*` endpoints.

It lets you expose friendly aliases such as:

- `ai-chat`
- `ai-tools`
- `ai-vision`
- `ai-summary`
- `ai-rag`
- `ai-translate`

Each alias is mapped from `.env` to:

- a real upstream model
- an optional default `reasoning_effort`

The proxy:

- replaces the alias model name with the real upstream model
- optionally injects `reasoning_effort` depending on the alias
- does not overwrite `reasoning_effort` if the client already sent it
- does not overwrite `reasoning.effort` if the client already sent it
- supports normal and streaming responses
- protects access with a local bearer token
- can use a separate upstream API key
- relays `/v1/models` from upstream with a light in-memory cache
- merges local aliases into the relayed `/v1/models` list

---

## Features

- idempotent install
- `uv` based project
- virtualenv exposed at `~/venv/<basename project dir>`
- `install.sh` compatible with upgrade
- `source run.sh [IP] [PORT]`
- local bearer token protection
- upstream bearer token support
- streaming compatible
- alias-based optional reasoning policy
- OpenAI-compatible `/v1/*` proxying
- `/v1/models` relayed from upstream with light cache
- local aliases merged into upstream model list
- aliases configurable from `.env`
- no Ollama-specific dependency in code

---

## Requirements

- Linux
- Python 3.11+
- `uv`
- an upstream OpenAI-compatible API base already ending with `/v1`

Examples:

- `https://api.openai.com/v1`
- `https://your-gateway.example.com/v1`
- `https://litellm.example.com/v1`

---

## Project layout

```text
qwen-nonthinking-proxy/
├── app.py
├── pyproject.toml
├── install.sh
├── run.sh
├── .env.example
└── README.md
````

---

## Install

```bash
chmod +x install.sh run.sh
./install.sh
```

If `.env` does not exist, it is created automatically from `.env.example`.

---

## Configuration

Edit `.env`:

```dotenv
UPSTREAM_BASE=https://api.openai.com/v1
UPSTREAM_API_KEY=
PROXY_API_TOKEN=change-me-long-random-token
REQUEST_TIMEOUT=600
REQUIRE_PROXY_AUTH=true
MODELS_CACHE_TTL=30
MODEL_ALIASES={"ai-chat":{"upstream_model":"gpt-4.1"},"ai-tools":{"upstream_model":"gpt-4.1","reasoning_effort":"low"},"ai-summary":{"upstream_model":"gpt-4.1","reasoning_effort":"none"}}

# LISTEN_HOST=0.0.0.0
# LISTEN_PORT=8000
```

### Important variables

* `UPSTREAM_BASE`: upstream OpenAI-compatible API base, already ending with `/v1`
* `UPSTREAM_API_KEY`: optional bearer token sent upstream
* `PROXY_API_TOKEN`: bearer token required by this proxy
* `REQUEST_TIMEOUT`: upstream timeout in seconds
* `REQUIRE_PROXY_AUTH`: set to `false` only if you explicitly want no local auth
* `MODELS_CACHE_TTL`: cache duration in seconds for `/v1/models`
* `MODEL_ALIASES`: JSON object defining aliases

---

## MODEL_ALIASES format

Example:

```dotenv
MODEL_ALIASES={"ai-chat":{"upstream_model":"gpt-4.1"},"ai-tools":{"upstream_model":"gpt-4.1","reasoning_effort":"low"},"ai-summary":{"upstream_model":"gpt-4.1","reasoning_effort":"none"}}
```

### Supported fields

For each alias:

* `upstream_model`: real model sent upstream
* `reasoning_effort`: optional default effort to inject

### Allowed `reasoning_effort` values

* `none`
* `low`
* `medium`
* `high`

### Default behavior

If `reasoning_effort` is omitted for an alias, the proxy does not inject anything.

That means:

* alias model name is still remapped to `upstream_model`
* but reasoning stays untouched unless the client requested it

### Client override behavior

If the client already sends:

* `reasoning_effort`
* or `reasoning: {"effort": ...}`

the proxy preserves it and does not overwrite it.

---

## Authentication model

This proxy can use two distinct tokens.

### 1. Local proxy token

Client sends this token to your proxy:

```bash
-H "Authorization: Bearer YOUR_PROXY_TOKEN"
```

This is checked against:

```dotenv
PROXY_API_TOKEN=...
```

### 2. Upstream token

The proxy can send a different token to the upstream:

```dotenv
UPSTREAM_API_KEY=...
```

If `UPSTREAM_API_KEY` is set, the proxy sends:

```http
Authorization: Bearer <UPSTREAM_API_KEY>
```

to the upstream.

If `UPSTREAM_API_KEY` is empty, the proxy removes the Authorization header before forwarding.

---

## Run

```bash
source ./run.sh 0.0.0.0 8000
```

or simply:

```bash
source ./run.sh
```

Default bind is `0.0.0.0:8000` unless overridden by arguments or environment.

---

## Alias behavior

### Example request without forced reasoning

```json
{
  "model": "ai-chat",
  "messages": [
    { "role": "user", "content": "Hello" }
  ]
}
```

Forwarded upstream as:

```json
{
  "model": "gpt-4.1",
  "messages": [
    { "role": "user", "content": "Hello" }
  ]
}
```

### Example request with alias default reasoning

If `.env` contains:

```dotenv
MODEL_ALIASES={"ai-tools":{"upstream_model":"gpt-4.1","reasoning_effort":"low"}}
```

then this request:

```json
{
  "model": "ai-tools",
  "messages": [
    { "role": "user", "content": "Analyze this problem" }
  ]
}
```

is forwarded upstream as:

```json
{
  "model": "gpt-4.1",
  "reasoning_effort": "low",
  "reasoning": { "effort": "low" },
  "messages": [
    { "role": "user", "content": "Analyze this problem" }
  ]
}
```

### Explicit client override is preserved

If the client sends:

```json
{
  "model": "ai-tools",
  "reasoning_effort": "high",
  "messages": [
    { "role": "user", "content": "Hello" }
  ]
}
```

the proxy still remaps `model`, but keeps:

```json
"reasoning_effort": "high"
```

The same applies if the client sends:

```json
"reasoning": { "effort": "medium" }
```

---

## Endpoints

### Health check

```bash
curl http://127.0.0.1:8000/healthz
```

### List exposed models

`/v1/models` is fetched from the upstream, cached in memory for a short time, then merged with local aliases.

Example:

```bash
curl http://127.0.0.1:8000/v1/models \
  -H "Authorization: Bearer YOUR_PROXY_TOKEN"
```

Behavior:

* fetch upstream `/models`
* cache the JSON payload in memory
* append local aliases if missing
* return merged model list

### Proxy chat completions

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_PROXY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ai-chat",
    "messages": [
      { "role": "user", "content": "Answer in one short sentence." }
    ]
  }'
```

### Streaming example

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_PROXY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ai-tools",
    "stream": true,
    "messages": [
      { "role": "user", "content": "Count from 1 to 5." }
    ]
  }'
```

---

## Non-supported paths

Only `/v1/*` is exposed.

Any other path returns:

```json
{
  "error": "Only /v1/* is exposed by this proxy"
}
```

---

## Systemd example

`run.sh` is compatible with systemd because it ends with `exec`.

Example unit:

```ini
[Unit]
Description=OpenAI-Compatible Alias Proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/qwen-nonthinking-proxy
ExecStart=/bin/bash -lc 'source ./run.sh 0.0.0.0 8000'
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

---

## Notes for H100 / DGX Spark

This proxy is CPU-light and model-agnostic.

Hardware compatibility depends mainly on the upstream inference server, not on this proxy.

The proxy only:

* authenticates requests
* rewrites alias model names
* optionally injects reasoning defaults
* relays `/v1/models` with short cache
* forwards requests and responses

---

## Upgrade

Re-run:

```bash
./install.sh
```

It will:

* keep using the same project directory
* refresh dependencies with `uv sync`
* recreate the `~/venv/<basename>` symlink if needed

---

## Generate a strong proxy token

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Then put the value into:

```dotenv
PROXY_API_TOKEN=...
```

---

## Typical usage flow

```bash
chmod +x install.sh run.sh
./install.sh
cp -n .env.example .env
nano .env
source ./run.sh 0.0.0.0 8000
```

Test:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_PROXY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ai-summary",
    "messages": [
      { "role": "user", "content": "Summarize this text." }
    ]
  }'
```
