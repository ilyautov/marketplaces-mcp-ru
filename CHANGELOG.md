# Changelog

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — [SemVer](https://semver.org/lang/ru/).

## [0.5.2] — 2026-09-07

### Добавлено
- **npm-запускалка** `npx -y marketplaces-mcp-ru` (папка `npm/`). Сервер остаётся
  на Python и PyPI; пакет на npm находит `uv` (PATH, `~/.local/bin`, `~/.cargo/bin`),
  при отсутствии скачивает официальный релиз uv с проверкой sha256 в
  `~/.cache/marketplaces-mcp-ru/` и запускает закреплённую версию с PyPI. Без uv —
  запасной путь через `python3 -m pip install --target`. Всё, что пишет запускалка,
  идёт в stderr; stdout остаётся транспортом MCP.
- `server.json`: третий пакет `npm` рядом с `pypi` и `oci`; workflow `publish-npm.yml`
  (npm Trusted Publishing по тегу); `publish-registry.yml` ждёт и npm тоже.
- `tests/test_versions.py`: версия `npm/package.json` и `mcpName` сверяются с pyproject
  и `server.json`.

## [0.5.1] — 2026-09-07

Технический релиз: MCP Registry отверг `server.json` 0.5.0 (описание длиннее
100 символов), поэтому OCI-пакет и запись в реестре за 0.5.0 не вышли. Описание
укорочено, добавлен тест на лимиты реестра. Код серверов не менялся.

## [0.5.0] — 2026-09-07

Два новых маркетплейса: Яндекс Маркет и Авито. Те же мета-инструменты, тот же
safety-гейт, те же кабинеты. Каталог вырос с 793 до 1022 методов, объединённый
сервер — с 80 до 106 инструментов.

### Добавлено
- **Яндекс Маркет** (`yandex_mcp`, префикс `ym_`, команда `yandex-mcp`, `serve.py yandex`).
  Каталог из официальной OpenAPI-спецификации Partner API: 165 методов, 29 секций
  (заказы, товары, остатки, цены, карантин цен, акции, отзывы, чаты, 27 отчётов,
  индекс качества). Авторизация одним `Api-Key` (`YANDEX_MARKET_API_KEY`).
  Типизированные инструменты: `ym_get_campaigns`, `ym_get_orders`, `ym_get_offers`,
  `ym_get_stocks`, `ym_get_prices`, `ym_set_price` (запись, с подтверждением).
  Четыре сценария в `yandex_mcp/workflows.yaml`.
- **Авито** (`avito_mcp`, префикс `avito_`, команда `avito-mcp`, `serve.py avito`).
  64 метода из восьми разделов API для бизнеса: заказы Авито Доставки, остатки
  и цены объявлений, статистика, рейтинг и отзывы, мессенджер, продвижение,
  автозагрузка, баланс. OAuth2 client_credentials (`AVITO_CLIENT_ID` +
  `AVITO_CLIENT_SECRET`), токен кешируется. Типизированные инструменты:
  `avito_whoami`, `avito_get_items`, `avito_get_orders`, `avito_get_stocks`,
  `avito_get_item_stats`, `avito_get_reviews`, `avito_get_chats`,
  `avito_get_balance`, `avito_update_price`, `avito_update_stock`.
  Четыре сценария в `avito_mcp/workflows.yaml`.
- **Пагинация**: стили `page_token` (Яндекс, `pageToken` в query и
  `paging.nextPageToken` в ответе) и `page_query` (Авито, `page=1,2,3…`).
- **OAuth**: `ServiceConfig.token_encoding="form"` — токен-запрос в
  `application/x-www-form-urlencoded` (Авито). Ozon Performance по-прежнему JSON.
- **Ingest**: `scripts/ingest_openapi.py` — общий импорт OpenAPI 3 с выводом
  `items_path` из схемы ответа и картой секций; `scripts/ingest_avito.py` собирает
  каталог Авито из компактных описаний разделов (`scripts/avito_specs/`).
- Оба сервиса подключены везде: `install.py` (флаги `--yandex-api-key`,
  `--avito-client-id/--avito-client-secret`, записи `yandex-market` и `avito` в
  конфигах клиентов), `.mcpb`, `server.json`, Docker-образ, `doctor`, кнопки
  VS Code / Cursor, тесты.

### Изменено
- README (RU/EN), лендинг, описания в PyPI / MCP Registry / .mcpb / plugin:
  проект теперь описан как MCP для Wildberries, Ozon, Яндекс Маркета и Авито.
- Таксономия сущностей: «объявления» (Авито) относятся к товарам.

### Известные ограничения
- Каталоги Яндекс Маркета и Авито собраны по спецификациям и не прогнаны на
  реальных кабинетах. Ошибки в именах полей возможны; `describe_method` и
  `call_raw` помогут поправить запрос на месте.

## [0.4.0] — 2026-09-07

Дистрибуция, часть вторая: Docker-образ и второй пакет в MCP Registry, HTTP-режим
для серверов и контейнеров, команда `doctor`. Логика работы с API не менялась.

### Добавлено
- **Docker / GHCR.** `Dockerfile` собирает объединённый сервер в образ
  `ghcr.io/ilyautov/marketplaces-mcp-ru:<версия>` (плюс `:latest`), непривилегированный
  пользователь, том `/data` под `cabinets.json`. Образ несёт метку
  `io.modelcontextprotocol.server.name`, по которой MCP Registry проверяет владельца.
- **MCP Registry: OCI-пакет** рядом с PyPI в `server.json`. Публикация теперь
  автоматическая: `publish-registry.yml` на каждом теге собирает образ, гоняет по
  нему настоящий `docker run`, ждёт появления версии на PyPI и публикует
  `server.json` через GitHub OIDC. Ручной `mcp-publisher` остался как запасной путь.
- **HTTP-транспорт** (`core/transport.py`). `MCP_TRANSPORT=http` переводит любой
  сервер (и объединённый) на Streamable HTTP: `MCP_HTTP_HOST`, `MCP_HTTP_PORT`,
  `MCP_HTTP_ALLOWED_HOSTS`. По умолчанию по-прежнему stdio. Аутентификации у
  HTTP-режима нет, об этом сказано в README и в предупреждении на stderr при
  привязке не к localhost.
- **`doctor`** (`core/doctor.py`): `python3 serve.py doctor`, `marketplaces-mcp-ru doctor`,
  `docker run … doctor`. По всем трём серверам: сколько инструментов и методов,
  найдены ли ключи и где (кабинет / env), а с `--live` один реальный read-вызов
  в каждый настроенный кабинет. `--json` для машин. Секреты не печатает.
  Код возврата 0 только если все настроенные кабинеты ответили.
- **`llms-install.md`** — короткая инструкция для агентов (Cline, Claude Code, Cursor).
- CI: leg на macOS, сборка и смоук Docker-образа на каждом PR;
  `tests/test_versions.py` держит одну версию во всех файлах релиза.

### Исправлено
- **Свежая установка с PyPI падала на импорте.** На PyPI вышел `mcp` 2.x, где
  `mcp.server.fastmcp` переименован, а `pyproject.toml` не держал верхнюю границу.
  `uvx marketplaces-mcp-ru` 0.3.3 у новых пользователей ломался ещё до старта;
  `serve.py` (zip / .mcpb) не задевало, он пинил `<2` сам. Теперь `mcp>=1.2,<2`,
  `httpx<1`, `pyyaml<7` закреплены и в pyproject, и в CI.
- README: число инструментов у серверов (21 / 21 / 16, было 19 / 19 / 14).

## [0.3.3] — 2026-07-16

Патч по итогам отладочной сессии на Windows: сервер не поднимался ни у одного
пользователя Windows, ставившего расширение через bootstrap-лаунчер. Баг был не
в `.mcpb`, а в `serve.py` — то есть задевал и установку из zip/терминала.

### Исправлено
- **Windows: `import mcp` падал с `No module named 'pywintypes'` (первопричина).**
  `_inject_site_packages()` клал site-packages в `sys.path` голым
  `sys.path.insert()`, который **не обрабатывает `.pth`-файлы**. На Windows `mcp`
  жёстко зависит от `pywin32` (`pywin32>=310; sys_platform == "win32"`), а его
  `pywin32.pth` как раз и подключает `win32/`-каталоги и регистрирует DLL-папку.
  Без этого зависимости считались битыми при каждом старте, и лаунчер уходил в
  переустановку. Теперь используется `site.addsitedir()` (кросс-платформенно).
- **Неудачное «самолечение» портило рабочий venv.** `venv.EnvBuilder(clear=True)`
  делал `rmtree` изнутри процесса, который уже импортировал нативные расширения
  (`.pyd`). На Windows загруженная DLL заблокирована ОС: очистка падала на
  середине дерева и оставляла venv в наполовину удалённом состоянии — хуже, чем
  до «починки». Пересоздание venv вынесено в отдельный subprocess
  (`python -m venv --clear`).
- **Пустой namespace-пакет проходил проверку зависимостей.** `_deps_importable()`
  проверял только `import mcp`: пустая папка `mcp/`, оставшаяся от прерванной
  переустановки, трактуется Python как namespace-пакет и импортируется успешно.
  Теперь проверяется реально используемый подмодуль (`mcp.server.fastmcp`).

### Документация
- QUICKSTART: раздел про запуск на Windows — заглушка `python.exe` из Microsoft
  Store (App Execution Alias) перехватывает `python` в `PATH` и молча падает;
  как проверить (`where python`) и починить.

Спасибо за подробный отчёт об отладке, который позволил найти первопричину.

## [0.3.2] — 2026-07-03

Дистрибуция: четыре канала установки поверх одного репозитория, все на общем
объединённом сервере. Логика продукта не менялась — только упаковка и доставка.

### Добавлено
- **Объединённый сервер** (`core/combined.py`): WB + Ozon + Ozon Performance на
  одном FastMCP — 58 инструментов, имена инструментов разведены по префиксам, так
  что объединение без коллизий. Стоит за `.mcpb` и за `uvx`. Отдельные серверы
  `wb` / `ozon` / `ozon-perf` работают как прежде.
- **`.mcpb`-бандл для Claude Desktop**: установка в один двойной клик без
  терминала и Gatekeeper. Манифест проходит официальный валидатор `@anthropic-ai/mcpb`,
  ключи собираются в окне настроек и прокидываются как переменные окружения.
  Собирается `scripts/package_mcpb.py`, прикладывается к каждому релизу.
- **PyPI / `uvx`**: `uvx marketplaces-mcp-ru` запускает объединённый сервер прямо
  из PyPI. Публикация через OIDC Trusted Publishing (`publish-pypi.yml`, без
  токенов). Новый console-script `marketplaces-mcp-ru`.
- **MCP Registry**: `server.json` для листинга + маркер владения в README.
- **Лендинг** `marketplaces-mcp-ru.aifrontier.tech` (GitHub Pages из `docs/`).
- **`docs/DISTRIBUTION.md`** — release-runbook по всем каналам.

### Исправлено
- **CI**: `gitleaks-action` получает `GITHUB_TOKEN` (падал на каждом PR); включён
  Dependency Graph для `dependency-review`; `actions/checkout` поднят до v7.0.0.

## [0.3.1] — 2026-07-02

Патч безопасности и надёжности по итогам полного код-ревью. Каждое исправление
закрыто тестом (всего офлайн-тестов стало вдвое больше).

### Безопасность
- **Запрет эксфильтрации ключей через `*_call_raw`.** Добавлен allowlist хостов
  на сервис (`.wildberries.ru` / `.ozon.ru`): запрос на чужой хост отклоняется
  до отправки, `path` обязан начинаться с `/` (закрыт трюк с подменой хоста
  через путь).
- **Изоляция токенов между кабинетами.** OAuth-токен (Ozon Performance) теперь
  кэшируется по конкретному набору ключей, а не глобально — смена кабинета сразу
  берёт правильный токен; ответ 401 инвалидирует кэш.
- **`*_fetch_all` больше не обходит safety-гейт.** Мутирующий метод, ошибочно
  помеченный `read` в каталоге, не прокрутится в цикле пагинации без
  подтверждения (тот же verb-floor, что и в `call_method`).

### Исправлено
- **`cabinets.json`** — атомарная запись (temp + `os.replace`), права `0600` на
  файл и `0700` на каталог с момента создания, повреждённый файл бэкапится в
  `.corrupt-N` вместо тихого обнуления ключей, блокировка между тремя
  процессами (wb/ozon/ozon_perf).
- **Ретраи** больше не повторяют `POST/PATCH` после таймаута чтения (защита от
  задвоения записи); повторяются только безопасные `GET/HEAD` и фаза соединения.
- **Пагинация offset** не останавливается на «короткой» странице, когда сервер
  режет размер страницы (пропадали данные); касты `int(total/page_count)` больше
  не падают на нечисловом значении; битый `Retry-After` не роняет запрос.
- Размер `details` в ошибке ограничен; path-параметры URL-энкодятся.

### Установка
- `serve.py` не запускает pip на каждом старте — venv подключается до проверки
  импортов, добавлен штамп версий зависимостей, офлайн-старт с готовым venv
  работает мгновенно; зависимости запинены сверху (`mcp>=1.2,<2` и т.д.).
- `install.py --client claude-code|codex` сохраняет переданные ключи (раньше
  молча терял); слияние конфига атомарное, с бэкапом повреждённого; обновление
  через staging-копию с откатом; breadcrumb пишет все конфиги.
- `install.bat` отсекает Python-заглушку из WindowsApps; шелл-установщики
  требуют Python 3.10+.

### Инфраструктура
- В wheel/sdist теперь попадает `core/entities.yaml` — карта методов и русский
  поиск работают у pip-установки.
- В релизном zip нормализуются права; внутренний `HANDOFF.md` исключён.
- CI: добавлены `windows-latest` и Python 3.13; релизный workflow по тегу `v*`.

## [0.3.0] — 2026-06-24

### Добавлено — самоочевидная карта методов и сущностей (#8)
- **Тул `*_map`** — обзор возможностей сервиса: бизнес-сущности (Товары, Цены,
  Остатки, Заказы, Поставки, Отзывы, Аналитика, Финансы, Реклама, Аккаунт) с
  синонимами, счётчиками и ключевыми методами (read-методы первыми).
  `entity="reviews"` — зум в одну сущность. Один вызов = вся карта, агент не
  теряется в 793 методах.
- **Умный поиск.** `*_search_methods` срезает стоп-слова («дай/покажи/мне»),
  понимает синонимы («оценки»→отзывы, «остатки»→stocks) и поднимает методы
  нужной сущности наверх. Сырые EN-токены работают как раньше.
- **Тег сущности** в выводе `search_methods` и `describe_method`.
- Курируемая таксономия — `core/entities.yaml` (10 сущностей, RU/EN-синонимы,
  пер-сервисный матч по секциям, покрытие ≥85% каждого каталога с гард-тестом).
  Дизайн — `docs/superpowers/specs/2026-06-24-method-entity-map-design.md`.

### Добавлено — кабинеты и ключи без терминала (#7)
- **Смена ключа из чата с явным согласием.** Новый тул `*_set_key` (и
  `*_add_cabinet` теперь тоже) требует `i_understand_key_goes_to_chat=true` —
  иначе ничего не пишет и отправляет к безопасной двери (установщик, где ключ в
  чат не попадает). Две двери, осознанный выбор.
- **Авто-имя кабинета из API.** При заведении/смене ключа дёргаем seller-info
  маркетплейса (WB `GET /api/v1/seller-info`; Ozon `POST /v1/seller/info`) и
  называем кабинет реальным именем магазина. Это же — лёгкая валидация ключа
  «в момент добавления». seller-info — best-effort: 403 из-за нехватки категории
  ≠ мёртвый ключ, поэтому ключ сохраняется в любом случае. (Поле имени у Ozon —
  кандидаты + graceful fallback, выверка боем отдельным шагом.)
- **Алиасы кабинетов** — человеческие имена (кириллица/пробелы), они же id;
  дефолт = имя из API, ручной алиас перебивает.
- **Подсказка о мёртвом ключе.** На 401/403 ответ обогащается «похоже, ключ истёк
  или отозван — смени через `*_set_key` или переустанови».
- **Мультимагазин в установщике** — интерактивный цикл «Добавить ещё магазин?».
- Внутренне: `MarketplaceClient.request/call_spec` принимают `creds_override`
  (валидация не-сохранённого ключа без записи в стор); `ServiceConfig.whoami`.
  Дизайн — `docs/superpowers/specs/2026-06-24-terminal-free-cabinet-key-lifecycle-design.md`.

## [0.2.2] — 2026-06-24

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

[0.3.0]: https://github.com/ilyautov/marketplaces-mcp-ru/releases/tag/v0.3.0
[0.2.2]: https://github.com/ilyautov/marketplaces-mcp-ru/releases/tag/v0.2.2
[0.2.1]: https://github.com/ilyautov/marketplaces-mcp-ru/releases/tag/v0.2.1
[0.2.0]: https://github.com/ilyautov/marketplaces-mcp-ru/releases/tag/v0.2.0
