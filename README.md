# marketplaces-mcp-ru: AI-доступ к кабинетам Wildberries и Ozon для Claude Code, Cursor, Codex и Cowork

> **Продаёте на WB и Ozon — дайте ИИ прямой доступ к обоим кабинетам.** Два MCP-сервера над Seller API Wildberries и Ozon: **793 метода** (продажи, остатки, цены, финансы, отзывы, поставки, реклама), собранных schema-driven из официальных OpenAPI-спеков. Числа приходят из **реального API**, а не выдумываются моделью. **Safety-гейт** не даёт случайно изменить цену или остаток. Авто-пагинация, мультикабинет, поиск по-русски. Для Claude Code, Cursor, Codex, Cowork и Claude Desktop.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Версия](https://img.shields.io/badge/%D0%B2%D0%B5%D1%80%D1%81%D0%B8%D1%8F-0.2.0-B5491F)](https://github.com/ilyautov/marketplaces-mcp-ru/commits/main)
[![Методов](https://img.shields.io/badge/%D0%BC%D0%B5%D1%82%D0%BE%D0%B4%D0%BE%D0%B2-793-2D7D4F)](#что-внутри)
[![Клиентов](https://img.shields.io/badge/%D0%BA%D0%BB%D0%B8%D0%B5%D0%BD%D1%82%D0%BE%D0%B2-4-D97757)](#установка)
[![Звёзды](https://img.shields.io/github/stars/ilyautov/marketplaces-mcp-ru?style=flat&label=%D0%B7%D0%B2%D1%91%D0%B7%D0%B4%D1%8B&color=B5491F&logo=github&logoColor=white)](https://github.com/ilyautov/marketplaces-mcp-ru/stargazers)

<!-- TODO: assets/social-preview.png + сайт marketplaces-mcp-ru.aifrontier.tech (как у humanizer-ru / small-business-ru) -->

## Зачем это нужно

**Вы продаёте на двух маркетплейсах одновременно, а данные — в двух разных кабинетах.** Продажи, остатки, цены, финансы, отзывы — всё руками, через два браузера, по очереди. ИИ-ассистент тут обычно бесполезен: либо ходит через браузер и спотыкается о капчу, либо выдумывает цифры, которые звучат уверенно.

`marketplaces-mcp-ru` заходит с другой стороны — даёт ИИ-агенту **прямой доступ к Seller API обоих кабинетов**:

- **Числа из реального API, а не из головы модели.** Продажи, остатки, маржа, финотчёт — это ответ Wildberries и Ozon, с источником и полями, а не правдоподобная выдумка.
- **Safety-гейт на всё, что трогает деньги.** Каждый метод помечен `read` / `write` / `destructive`; чтение идёт сразу, а смена цены или остатка требует явного подтверждения. Случайно «уронить цену в 3 раза» нельзя.
- **Без браузера и капчи.** Прямые HTTPS-вызовы по токену кабинета.

Скажите агенту обычными словами: «покажи продажи за неделю на обоих», «что пора дозаказать», «сравни цены с рынком» — он подберёт метод или готовый сценарий и проведёт по шагам.

> ⚠️ **alpha.** Помогает с операционкой продавца, но это инструмент, а не замена аналитика. Курированное ядро выверено боем на реальных кабинетах; импортированные из спеков методы — карта для разведки (пути надёжны, HTTP-глаголы подтверждайте по докам). Подробности — в разделе «Оговорки» и `HANDOFF.md`.

## Что внутри

**Не «один тул на эндпоинт» (это 300+ тулов, в которых агент тонет), а 8 generic мета-тулов над каталогом** — полное покрытие API при маленькой поверхности.

```
ваш ИИ-агент
      │
      ▼
 8 мета-тулов  ──►  каталог (endpoints.yaml)  ──►  общий core
 search / describe /                                клиент · safety · ошибки
 call / call_raw /                                  пагинация · реестр
 fetch_all / ...                                          │
 + типизированные тулы (wb_get_sales, ozon_get_prices, …)  ▼
                                          Wildberries / Ozon HTTPS API
```

**Мета-тулы (одинаковый набор на оба сервера, префикс `wb_` / `ozon_`):**

| Тул | Что делает |
|---|---|
| `*_check_auth` | Есть ли креды (секреты не печатает) |
| `*_search_methods` | Поиск метода — **по-русски или по-английски** |
| `*_describe_method` | Полная спека: метод, хост, путь, scope, safety, лимит, doc |
| `*_call_method` | Вызвать любой метод каталога (через safety-гейт) |
| `*_call_raw` | Вызвать **любой** путь, даже вне каталога (100% покрытие) |
| `*_fetch_all` | Авто-пагинация (offset / last_id / cursor / WB date-курсор) |

Плюс типизированные удобные тулы (`wb_get_sales`, `wb_get_stocks`, `ozon_get_products`, `ozon_get_prices`, …) и тулы кабинетов.

**Сценарии (workflows) — не сырые эндпоинты, а рецепты.** `*_list_workflows` / `*_get_workflow` выдают пошаговые рецепты с трактовкой и типичными ошибками. WB: `sales_pulse`, `stock_health`, `price_audit`, `reorder_planner`, `abc_analysis`, `reviews_pulse`. Ozon: `oos_risk_analysis`, `pricing_analysis`, `unit_economics`, `catalog_sync`, `content_quality_audit`, `abc_analysis`, `reviews_pulse`. Каждый шаг сверяется с каталогом.

**Покрытие — schema-driven из официальных OpenAPI-спеков:**

| Каталог | Файл | Методов | Секций |
|---|---|---:|---|
| Wildberries | `wb_mcp/endpoints.yaml` | **307** | 70 |
| Ozon Seller | `ozon_mcp/endpoints.yaml` | **441** | 67 |
| Ozon Performance (реклама) | `ozon_mcp/perf_endpoints.yaml` | **45** | 6 |

Курированное ядро (продажи/остатки/цены/финансы/отзывы) выверено вживую; остальное импортировано из спеков. `call_raw` достаёт всё, чего ещё нет в каталоге.

## Safety model

Ключи кабинета двигают цены, остатки и деньги. Каждый метод классифицирован:

- **read** → выполняется сразу;
- **write** → требует `confirm_write=true`;
- **destructive** → требует `confirm_write=true` **и** `i_understand_this_modifies_data=true`.

Гейт работает локально — без подтверждений наружу ничего не уходит. Аудит каталога: **0 мутаций, помеченных как read** на обоих серверах.

## Установка

Подробный пошаговый гайд под любую аудиторию — в **[QUICKSTART.md](QUICKSTART.md)**. Три пути, один результат:

1. **Проще всего — попроси своего ИИ (без терминала).** Открой Claude / Cowork и скажи: *«установи WB + Ozon MCP»* — агент проведёт по встроенному `install-skill/`. (Песочница Cowork не лезет на твою машину, поэтому финальный клик остаётся за тобой — скилл лишь доводит без ошибок. В Claude Code ставится полностью сам.)
2. **Скачать и кликнуть.** Возьми `marketplaces-mcp-ru-v<версия>.zip` из [GitHub Releases](https://github.com/ilyautov/marketplaces-mcp-ru/releases), распакуй, двойной клик `install.command` (macOS) / `install.bat` (Windows), вставь ключи.
3. **Технический.** `git clone https://github.com/ilyautov/marketplaces-mcp-ru` → `python3 install.py --client <твой-клиент>`.

<!-- TODO: создать публичный репозиторий ilyautov/marketplaces-mcp-ru и выложить zip в Releases -->

Ни `pip install`, ни правки JSON: зависимости ставятся сами при первом запуске (локальный venv), от тебя — только ключи. **4 клиента** через `--client`: `claude-desktop` и `opencode` получают записанный конфиг, `claude-code` и `codex` — готовые `* mcp add` команды.

**Где взять ключи:** Wildberries — seller.wildberries.ru → Настройки → Доступ к API; Ozon — seller.ozon.ru → Настройки → API-ключи. Ключи хранятся в `~/.marketplace-mcp/cabinets.json` (локально, chmod 600, никогда в репо). Поддержка **мультикабинета** — несколько магазинов с переключением из чата (`*_add_cabinet` / `*_use_cabinet`).

**Проверка после установки:**

```bash
python3 serve.py ozon --selfcheck
```

## Скрипты и рост каталога

В `scripts/`: `ingest_specs.py` / `ingest_ozon.py` (сборка каталогов из официальных спеков), `derive_pagination.py` и `fix_items_path_from_examples.py` (пагинация и `items_path`), `validate_items_path.py` (**live**-валидатор, гонять локально), `package_release.py` (чистый версионный zip), `smoke_mcp.py`. Каталоги дорастают аддитивно и идемпотентно — курированные safety и описания не перетираются.

## Тесты

```bash
python3 -m pytest tests/ -q        # 21 офлайн-тест, токены не нужны
```

## Оговорки (сверяйте с живой докой)

- **WB `Authorization`**: сервер шлёт **raw-токен без `Bearer`** (подтверждено боем). Если auth падает — первым делом проверьте это.
- **Импортированные из спеков методы: пути надёжны, HTTP-глаголы — нет.** Live-проба нашла GET-помеченные методы, которые на деле POST (405). Считайте импортированные записи картой разведки: подтверждайте глагол/тело по докам или зовите через `call_raw`. Курированное ядро (WB 7 категорий, Ozon 4 секции) и live-выверенный набор — надёжны.
- **Ozon дрейфует по версиям** (list v3, attributes v4, prices v5). При 404 — проверьте версию; `ingest_ozon.py` пере-выравнивает пути.
- **Ozon Performance** — пока каталог-артефакт + OAuth-обвязка по докам (контракт токен-эндпоинта не выверен боем, нужны рекламные креды). Подробности — `HANDOFF.md`.
- **Кабинет затеняет env**: активный кабинет в `cabinets.json` имеет приоритет над переменными окружения. Необъяснимый 401 / «Client-Id should be positive integer» — первым делом проверьте стор.

---

Собственный код, лучшие паттерны: архитектура берёт сильнейшие идеи зрелых marketplace-MCP (schema-driven каталог, safety-гейт, единые ошибки, авто-пагинация) без зависимости от чужих библиотек. Лицензия MIT.
