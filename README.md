# OpenAI-Compatible Alias Proxy

FastAPI proxy for OpenAI-compatible `/v1/*` endpoints.

It lets you expose friendly aliases such as:

- `ai-multilingual`
- `ai-tools`
- `ai-thinking`
- `ai-vision`
- `ai-chat`
- `gpt-4`

Each alias is mapped from `.env` to:

- a real upstream model
- an optional default `reasoning_effort`
- optional default request parameters such as temperature/top_p/top_k
- an optional visibility flag for `/v1/models`

The proxy:

- replaces the alias model name with the real upstream model
- optionally injects `reasoning_effort` depending on the alias
- optionally injects alias-specific request parameters only when the client omits them
- does not overwrite `reasoning_effort` if the client already sent it
- does not overwrite `reasoning.effort` if the client already sent it
- does not overwrite alias `parameters` keys if the client already sent them
- supports normal and streaming responses
- protects access with a local bearer token
- can use a separate upstream API key
- relays `/v1/models` from upstream with a light in-memory cache
- merges local aliases into the relayed `/v1/models` list
- supports hiding specific aliases from `/v1/models` without disabling requests

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
- alias-based optional sampling/default parameter policy
- OpenAI-compatible `/v1/*` proxying
- `/v1/models` relayed from upstream with light cache
- local aliases merged into upstream model list
- aliases and default request parameters configurable from `.env`
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
MODEL_ALIASES={"ai-multilingual":{"upstream_model":"qwen3.6","reasoning_effort":"none","parameters":{"temperature":0.7,"top_p":0.80,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}},"ai-tools":{"upstream_model":"qwen3.6","parameters":{"temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.0,"presence_penalty":0.0,"repetition_penalty":1.0}},"ai-thinking":{"upstream_model":"qwen3.6","parameters":{"temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}},"ai-vision":{"upstream_model":"qwen3.6","reasoning_effort":"none","parameters":{"temperature":0.7,"top_p":0.80,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}},"ai-chat":{"upstream_model":"qwen3.6","reasoning_effort":"none","hidden":true,"parameters":{"temperature":0.7,"top_p":0.80,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}},"gpt-4":{"upstream_model":"qwen3.6","reasoning_effort":"none","hidden":true,"parameters":{"temperature":0.7,"top_p":0.80,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}}}

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
* `MODEL_ALIASES`: JSON object defining aliases and optional request defaults

---

## MODEL_ALIASES format

Example adapted for `qwen3.6` aliases:

```dotenv
MODEL_ALIASES={"ai-multilingual":{"upstream_model":"qwen3.6","reasoning_effort":"none","parameters":{"temperature":0.7,"top_p":0.80,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}},"ai-tools":{"upstream_model":"qwen3.6","parameters":{"temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.0,"presence_penalty":0.0,"repetition_penalty":1.0}},"ai-thinking":{"upstream_model":"qwen3.6","parameters":{"temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}},"ai-vision":{"upstream_model":"qwen3.6","reasoning_effort":"none","parameters":{"temperature":0.7,"top_p":0.80,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}},"ai-chat":{"upstream_model":"qwen3.6","reasoning_effort":"none","hidden":true,"parameters":{"temperature":0.7,"top_p":0.80,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}},"gpt-4":{"upstream_model":"qwen3.6","reasoning_effort":"none","hidden":true,"parameters":{"temperature":0.7,"top_p":0.80,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}}}
```

### Supported fields

For each alias:

* `upstream_model`: real model sent upstream
* `reasoning_effort`: optional default effort to inject
* `parameters`: optional JSON object of request defaults to inject, such as `temperature`, `top_p`, `top_k`, `min_p`, `presence_penalty`, or `repetition_penalty`
* `hidden`: optional boolean; when true, alias is not listed in `/v1/models`

### Allowed `reasoning_effort` values

* `none`
* `low`
* `medium`
* `high`

### Default behavior

If `reasoning_effort` is omitted for an alias, the proxy does not inject reasoning.

If `parameters` is omitted for an alias, the proxy does not inject extra request parameters.

That means:

* alias model name is still remapped to `upstream_model`
* reasoning stays untouched unless the client requested it or the alias defines `reasoning_effort`
* sampling/default parameters stay untouched unless the alias defines `parameters`

### Sampling/default parameter presets

Use the `parameters` field to define per-alias defaults. These are applied only when the client omits the same key.

Recommended presets from `.env.example`:

* Thinking mode for general tasks: `temperature=1.0`, `top_p=0.95`, `top_k=20`, `min_p=0.0`, `presence_penalty=1.5`, `repetition_penalty=1.0`
* Thinking mode for precise coding tasks, such as WebDev: `temperature=0.6`, `top_p=0.95`, `top_k=20`, `min_p=0.0`, `presence_penalty=0.0`, `repetition_penalty=1.0`
* Instruct or non-thinking mode: `temperature=0.7`, `top_p=0.80`, `top_k=20`, `min_p=0.0`, `presence_penalty=1.5`, `repetition_penalty=1.0`

Example alias:

```dotenv
MODEL_ALIASES={"ai-thinking":{"upstream_model":"qwen3.6","parameters":{"temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0}}}
```

### Client override behavior

If the client already sends:

* `reasoning_effort`
* or `reasoning: {"effort": ...}`
* or any key also defined in alias `parameters`

the proxy preserves it and does not overwrite it.

## Hide aliases from `/v1/models`

You can keep old aliases working while hiding them from discovery.

Example:

```dotenv
MODEL_ALIASES={"ai-chat":{"upstream_model":"qwen3.6","reasoning_effort":"none","hidden":true},"ai-thinking":{"upstream_model":"qwen3.6"}}
```

This only affects `/v1/models` output. Requests using hidden aliases still work.

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
* skip aliases marked with `"hidden": true`
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
