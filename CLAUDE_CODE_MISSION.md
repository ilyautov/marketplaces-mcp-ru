# Миссия для Claude Code — marketplaces-mcp-ru: проверить → дособрать → прогнать → оформить

Открой Claude Code в корне этого репо и выполни по шагам. В Claude Code bash = реальная машина, поэтому здесь работает всё, что не пошло в песочнице Cowork: настоящий `serve.py --selfcheck`, полный live-свип, реальная установка в клиент, `git push` и `gh release`.

Справочник по состоянию и оговоркам — `HANDOFF.md` и `README.md`. Ниже — исполняемый порядок.

---

## 0. Предусловия
- Python 3.10+, git, `gh` (GitHub CLI, авторизованный: `gh auth status`).
- **Сначала перевыпусти ключи** (старые засветились в рабочей сессии): WB-токен (seller.wildberries.ru → Настройки → Доступ к API), Ozon Client-Id+Api-Key (seller.ozon.ru → Настройки → API-ключи). Дальше используй НОВЫЕ.

## 1. ПРОВЕРИТЬ (офлайн, без ключей)
```bash
# тесты
env -u OZON_CLIENT_ID -u OZON_API_KEY -u WB_API_TOKEN python3 -m pytest tests/ -q   # ждём 21 passed

# каталоги грузятся, числа
python3 -c "import sys;sys.path.insert(0,'.');from core.registry import Catalog;\
print('wb',len(Catalog.from_yaml('wb_mcp/endpoints.yaml').all()),\
'ozon',len(Catalog.from_yaml('ozon_mcp/endpoints.yaml').all()),\
'perf',len(Catalog.from_yaml('ozon_mcp/perf_endpoints.yaml').all()))"   # 307 / 441 / 45

# selfcheck всех трёх серверов (в Cowork виснет, тут — нет). Запиши реальное число тулов в README/HANDOFF, если разошлось.
python3 serve.py wb --selfcheck
python3 serve.py ozon --selfcheck
python3 serve.py ozon-perf --selfcheck   # perf-сервер подключён (serve.py SERVICES), но контракт OAuth не выверен боем
```

## 2. ДОСОБРАТЬ (pip-пакет на реальной ОС)
```bash
pip install build --break-system-packages -q
python3 -m build                      # dist/marketplaces_mcp_ru-0.2.0-*.whl + .tar.gz
# проверь что все 6 yaml в wheel:
python3 -c "import zipfile,glob;w=glob.glob('dist/*.whl')[0];print('\n'.join(n for n in zipfile.ZipFile(w).namelist() if n.endswith('.yaml')))"
# поставь в чистый venv и проверь загрузку из site-packages:
python3 -m venv /tmp/vt && /tmp/vt/bin/pip install -q dist/*.whl && \
/tmp/vt/bin/python -c "from core.registry import Catalog;import core,os;assert 'site-packages' in core.__file__;print('pip OK')"
```

## 3. ПРОГНАТЬ (live, с НОВЫМИ ключами)
```bash
export WB_API_TOKEN=...; export OZON_CLIENT_ID=...; export OZON_API_KEY=...

# 3.1 полный свип items_path (нет 45с-лимита, свежий rate-бюджет). Правит на месте — ревью diff перед коммитом.
python3 scripts/validate_items_path.py ozon
python3 scripts/validate_items_path.py wb
git diff --stat wb_mcp/endpoints.yaml ozon_mcp/endpoints.yaml

# 3.2 реальная установка в свой клиент и e2e ЧЕРЕЗ сам MCP (не через скрипт):
python3 install.py --client claude-code      # или --client claude-desktop / codex / opencode
# затем в клиенте: ozon_get_products, wb_get_stocks, wb_get_sales, ozon_get_prices,
# финотчёт, отзывы — убедись что данные идут (Ozon-отзывы = 403 без Premium Plus, это норма).

# 3.3 если правки items_path валидны:
git add -A && git commit -m "Live items_path sweep (Claude Code, fresh rate budget)"
```
Если внезапный 401/«Client-Id should be positive integer» — проверь `~/.marketplace-mcp/cabinets.json`: активный кабинет имеет приоритет над env (грабли из памяти).

## 4. ОФОРМИТЬ (публикация на GitHub)
```bash
# репозиторий
gh repo create ilyautov/marketplaces-mcp-ru --public \
  --description "MCP-сервер для кабинетов Wildberries и Ozon: продажи, остатки, цены, финансы, отзывы через Seller API напрямую, без браузера. 793 метода schema-driven, safety-гейт на запись. Подключает ИИ (Claude Code, Cursor, Codex, ChatGPT) к API WB и Ozon. Open-source MIT."

git remote add origin https://github.com/ilyautov/marketplaces-mcp-ru.git
git push -u origin main      # или master — проверь `git branch`

# topics (≤20)
gh repo edit ilyautov/marketplaces-mcp-ru --add-topic mcp,model-context-protocol,wildberries,ozon,wildberries-api,ozon-api,ozon-seller,marketplace,seller-api,claude,claude-code,claude-cowork,cursor,codex-cli,chatgpt,anthropic,ai-agents,ecommerce,russia,python

# release с готовым zip
python3 scripts/package_release.py        # dist/marketplaces-mcp-ru-v0.2.0.zip
gh release create v0.2.0 dist/marketplaces-mcp-ru-v0.2.0.zip \
  --title "marketplaces-mcp-ru v0.2.0" \
  --notes "Два MCP-сервера над Seller API Wildberries (307 методов) и Ozon (441) + каталог Ozon Performance (45). Schema-driven из официальных OpenAPI-спеков, safety-гейт read/write/destructive, авто-пагинация, мультикабинет, поиск по-русски. Установка под 4 клиента (Claude Desktop/Code, Codex, OpenCode) + install-скилл для не-технических. 21 офлайн-тест. Выверено боем на реальных кабинетах."
```

## 5. ПО СТИЛЮ (опционально, как у humanizer-ru / small-business-ru)
- `assets/social-preview.png` (1280×640) → Settings → Social preview. Брендовые цвета: охра `#B5491F`, оранжевый `#D97757`, зелёный `#2D7D4F`.
- Сайт `marketplaces-mcp-ru.aifrontier.tech` (GitHub Pages / Netlify) с FAQ-страницами под SEO.
- `README.en.md` (английская версия) + ссылка `> [English version]` в шапке README.
- `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` — как в small-business-ru.

## Готово, когда
- [ ] 21 тест зелёный, 3 сервера selfcheck-ок, wheel ставится из чистого venv
- [ ] live-свип items_path прогнан, diff отревьюен и закоммичен
- [ ] e2e через MCP-клиент на обоих кабинетах отдаёт данные
- [ ] репо на GitHub, description + topics + release с zip
- [ ] старые ключи отозваны
