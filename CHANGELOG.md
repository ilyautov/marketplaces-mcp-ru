# Changelog

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — [SemVer](https://semver.org/lang/ru/).

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

[0.2.0]: https://github.com/ilyautov/marketplaces-mcp-ru/releases/tag/v0.2.0
