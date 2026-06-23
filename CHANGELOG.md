# Changelog

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — [SemVer](https://semver.org/lang/ru/).

## [Unreleased]

### Изменено (установка — по фрикшен-логу реальной сессии)
- **Каноническая установка (F3).** `install.py` теперь копирует приложение в
  `~/.marketplace-mcp/app` и привязывает конфиг туда, а не к месту клона. Папку с
  репозиторием (в т.ч. примонтированную в Cowork) можно перемещать/удалять — MCP
  не сломается. Флаг `--in-place` оставляет старое поведение (dev/ручной режим).
- **Главный путь «скинул репо → агент поставил».** Раз приложение копируется
  наружу, на примонтированной Cowork-папке не нужны git-операции — это обходит
  FUSE-ошибку `Operation not permitted` при `git clone` (F1/F2). SKILL.md
  переписан под это + troubleshooting.
- **Интерактив спрашивает 3 поля, не 5 (F5).** Ozon Performance (реклама) — за
  флагом `--with-ads`; нетехнический продавец вводит WB + Ozon Client-Id/Api-Key.
- **Breadcrumb для верификации (F4).** `install.py` пишет секрет-free
  `~/.marketplace-mcp/last_install.json` (серверы, путь serve.py, время) — можно
  подтвердить установку, не читая защищённый конфиг клиента. Стандарт проверки в
  SKILL.md: после рестарта через сами MCP-тулы, а не чтением конфига.
- **Gatekeeper (F6).** В README и SKILL.md добавлена ветка про карантин
  скачанного `install.command` (правый клик → «Открыть» / `xattr -d`).
- Убраны протухшие TODO про «нет git remote» (репозиторий опубликован).

## [0.2.1] — 2026-06-24

### Исправлено (безопасность)
- **Дыра в safety-гейте: 4 мутирующих WB-метода были помечены `safety: read`**
  (`wb_put_api_warehouses_warehouseid`,
  `wb_put_api_dbw_warehouses_warehouseid_contacts`, `wb_patch_api_questions`,
  `wb_patch_api_feedbacks_answer`). `call_method` гейтит по полю каталога, поэтому
  эти PUT/PATCH выполнялись бы сразу, без `confirm_write`. Закрыто на четырёх
  уровнях:
  - проставлен `safety: write` четырём записям в `wb_mcp/endpoints.yaml`;
  - `call_method` теперь пропускает `spec.safety` через `infer_safety(method, …)`
    — мутирующий глагол нельзя понизить ниже `write` даже устаревшим `read`;
  - эвристика импорта (`ingest_specs.py`, `ingest_ozon.py`) больше не применяет
    READ-исключение к PUT/PATCH — оно осмысленно только для POST-with-body;
  - тест-линтер `tests/test_safety_catalog.py` + CI падают, если в каталоге
    появится PUT/PATCH/DELETE с `safety: read`.

### Добавлено
- **CI** (`.github/workflows/ci.yml`): pytest на Python 3.10–3.12 + selfcheck
  трёх серверов на каждый push/PR.
- Дистрибуция как плагин: `.claude-plugin/` (plugin + marketplace), `.mcp.json`,
  `gemini-extension.json` (+ `GEMINI.md`), `.cursor-plugin/`, `.codex-plugin/`,
  `PRIVACY_POLICY.md`, issue-шаблоны и dependabot.

## [0.2.0] — 2026-06-24

Первый публичный релиз.

### Добавлено
- **Два MCP-сервера** над Seller API: Wildberries (307 методов) и Ozon (441),
  плюс каталог Ozon Performance / реклама (45 методов) — **793 метода** всего,
  schema-driven из официальных OpenAPI-спеков.
- **8 generic мета-тулов** на каждый сервер (`*_search_methods`,
  `*_describe_method`, `*_call_method`, `*_call_raw`, `*_fetch_all`,
  `*_check_auth`, …) вместо «тул на эндпоинт» — полное покрытие при малой
  поверхности. Selfcheck: wb 19, ozon 19, ozon-perf 14 тулов.
- **Safety-гейт** read / write / destructive: чтение идёт сразу, запись и
  удаление требуют явного подтверждения.
- **Сценарии (workflows)** — пошаговые рецепты с трактовкой и типичными
  ошибками (sales_pulse, stock_health, price_audit, reorder_planner,
  abc_analysis, reviews_pulse и др.).
- **Авто-пагинация** (offset / last_id / cursor / WB date-курсор), **поиск
  по-русски и по-английски**, **мультикабинет** (несколько магазинов).
- **Установщик под 4 клиента** (`install.py --client …`): Claude Desktop,
  Claude Code, Codex, OpenCode. Плюс зеро-терминальная установка через
  install-скилл для не-технических пользователей.
- **Windows-инсталлер** `install.bat` с авто-установкой Python через winget;
  `install.command` (macOS) и `install.sh` (Linux).
- Хранение ключей локально в `~/.marketplace-mcp/cabinets.json` (`chmod 600`),
  секреты не пишутся в конфиг клиента и не попадают в чат.
- **21 офлайн-тест** (ключи не нужны), `serve.py --selfcheck` для всех серверов.

### Оговорки
- **alpha.** Курированное ядро (продажи/остатки/цены/финансы/отзывы) выверено
  боем на реальных кабинетах; импортированные из спеков методы — карта для
  разведки: пути надёжны, HTTP-глаголы подтверждайте по докам или зовите через
  `call_raw`.
- Контракт OAuth у Ozon Performance подключён, но не выверен боем (нужны perf-креды).

[0.2.1]: https://github.com/ilyautov/marketplaces-mcp-ru/releases/tag/v0.2.1
[0.2.0]: https://github.com/ilyautov/marketplaces-mcp-ru/releases/tag/v0.2.0
