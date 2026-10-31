# playground-gateway

Шлюз рабочей области «Обкатка» портала «Пульс ИИ». Принимает промпты от портала
(bearer-ключ), применяет дневную квоту, выполняет через **Codex CLI** и стримит
ответ обратно. Каждый прогон пишется в SQLite (`data/runs.sqlite`) — это данные
этапа 0 для отточки промптов.

Привязка к текущему Codex: шлюз вызывает тот же бинарь `codex` и ту же авторизацию
(`~/.codex/auth.json`), что и агенты Hermes. Агентный слой Hermes не используется.

## API

- `GET /healthz` — живость + статистика прогонов
- `POST /v1/chat` — тело `{"prompt": "...", "material_id": "m1", "step_index": 2}`;
  заголовки: `Authorization: Bearer <GATEWAY_API_KEY>`, опционально `X-Client-Key`
  (квота по нему, иначе по IP). Ответ — `text/plain` потоком, заголовки
  `X-Engine: codex`, `X-Quota-Left: N`

## Установка на стенд

```bash
git clone <repo> ~/playground-gateway && cd ~/playground-gateway
./deploy/install.sh        # venv + юнит + env с автоключом, systemctl --user
```

Порт слушает `127.0.0.1:8787`; наружу публикуется через Caddy/nginx с TLS
(`playground.<домен>` → `127.0.0.1:8787`).

## Переменные окружения (`~/playground-gateway.env`)

| Переменная | По умолчанию | Что |
|---|---|---|
| `GATEWAY_API_KEY` | генерируется install.sh | bearer-ключ портала |
| `CODEX_BIN` | `codex` из PATH | путь к бинарю Codex CLI |
| `CODEX_ARGS` | `--skip-git-repo-check` | доп. аргументы `codex exec` |
| `CODEX_TIMEOUT` | 120 | секунды на прогон |
| `MAX_OUTPUT` | 20000 | кап вывода, знаков |
| `CONCURRENCY` | 2 | одновременные прогоны |
| `RUNS_PER_DAY` | 10 | квота на клиента |
| `DB_PATH` | `./data/runs.sqlite` | база прогонов |

## Портал

В `portal/.env` портала:

```
PLAYGROUND_GATEWAY_URL=https://playground.<домен>
PLAYGROUND_GATEWAY_KEY=<GATEWAY_API_KEY со стенда>
```

Роут `/api/playground/chat` переключится с мока на шлюз автоматически.

## Проверка на сервере

```bash
curl -s http://127.0.0.1:8787/healthz
curl -sN -X POST http://127.0.0.1:8787/v1/chat \
  -H "Authorization: Bearer $GATEWAY_API_KEY" -H "X-Client-Key: test" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Привет! Ответь одним предложением."}'
```

## Тесты

```bash
pip install pytest httpx
python -m pytest -q
```
