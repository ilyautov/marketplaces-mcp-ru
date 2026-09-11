#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор страниц docs/<маркетплейс>-api.html.

Карта методов собирается из тех же каталогов, что грузит сервер
(`*/endpoints.yaml`), поэтому страница не расходится с кодом: поменялся
каталог, перегенерировали страницу. Проза лежит здесь же, в PAGES.

Запуск:  python3 scripts/build_marketplace_pages.py
Проверка без записи:  python3 scripts/build_marketplace_pages.py --check
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE = "https://marketplaces-mcp-ru.aifrontier.tech"
# Второй набор серверов, тех же рук и того же устройства. Ссылка стоит в
# навигации, а не только в подвале: девять серверов на двух поддоменах, и
# пришедший за API Ozon иначе не узнает, что есть Диадок.
BUSINESS = "https://business-mcp-ru.aifrontier.tech/"
REPO = "https://github.com/ilyautov/marketplaces-mcp-ru"

# --- группировка разделов каталога в темы, понятные продавцу ----------------
# Ключ: как раздел называется в endpoints.yaml. Значение: тема на странице.
OZON_THEMES = {
    "Товары и карточки": ["products", "ProductAPI", "categories", "brands",
                          "barcodes", "quants", "Digital", "certificates",
                          "CertificationAPI"],
    "Цены и остатки": ["prices", "stocks", "Prices&StocksAPI", "strategies"],
    "Заказы FBS и доставка": ["fbs", "orders_fbs", "DeliveryFBS",
                              "FBSWarehouseSetup", "rFBSWarehouseSetup", "FBS",
                              "pass", "PolygonAPI", "polygons", "DeliveryAPI",
                              "OrderAPI", "Receipt"],
    "Заказы FBO и склады": ["fbo", "FBO", "orders_fbo", "FboSupplyRequest",
                            "FboPostingAPI", "WarehouseAPI", "warehouses",
                            "clusters"],
    "Кросс-док FBP": ["DraftDirectFBP", "DeliveryFBP", "DraftDropOffFBP",
                      "DraftPickupFBP", "OrderDirectFBP", "OrderDropOffFBP",
                      "OrderPickupFBP", "DeliveryFBPDraft"],
    "Возвраты и отмены": ["returns", "ReturnsAPI", "RFBSReturnsAPI",
                          "cancellations", "CancellationAPI", "CancelReasonAPI"],
    "Финансы и отчёты": ["finance", "FinanceAPI", "invoices", "reports",
                         "ReportAPI"],
    "Аналитика": ["analytics", "AnalyticsAPI"],
    "Отзывы, вопросы и чаты": ["reviews", "Questions&Answers", "chats",
                               "ChatAPI", "rating", "SellerRating"],
    "Акции и продвижение": ["promotions", "SellerActions", "Premium"],
    "Кабинет и служебное": ["SellerInfo", "APIkey", "Notification", "BetaMethod"],
}

OZON_PERF_THEMES = {
    "Кампании и объявления": ["Campaign", "Ad"],
    "Статистика рекламы": ["Statistics"],
    "Товары в рекламе": ["Product"],
    "Продвижение в поиске": ["Search-Promo"],
    "Вендорская реклама": ["Vendor"],
}

YANDEX_THEMES = {
    "Заказы, возвраты и невыкупы": ["Заказы", "Статистика заказов и товаров",
                                    "Возвраты и невыкупы", "Доставка возвратов"],
    "Отчёты": ["Отчёты"],
    "Отгрузки, поставки и склады": ["Отгрузки и поставки (first-mile)",
                                    "Заявки на поставку", "Склады"],
    "Товары и карточки": ["Товары", "Товары (каталог)",
                          "Карточки товаров (контент)", "Категории",
                          "Скрытые товары"],
    "Цены, тарифы и карантин": ["Цены", "Карантин цен", "Тарифы и комиссии"],
    "Продвижение и реклама": ["Буст продаж и ставки (реклама)",
                              "Акции и продвижение"],
    "Отзывы, вопросы и чаты": ["Чаты с покупателями", "Отзывы о товарах",
                               "Вопросы о товарах", "Рейтинг и индекс качества"],
    "Самовывоз и регионы доставки": ["Точки продаж и ПВЗ (самовывоз)",
                                     "Регионы доставки", "Доставка"],
    "Кабинет и служебное": ["Настройки продавца", "Магазины (кампании) продавца",
                            "Токен и доступ (пользователь)",
                            "Статусы операций (система)"],
}

# Хосты Wildberries: у WB не один домен, а свой на каждое назначение.
WB_HOST_LABELS = {
    "marketplace-api.wildberries.ru": "Сборочные задания и поставки FBS, DBS, DBW, самовывоз",
    "seller-analytics-api.wildberries.ru": "Аналитика продавца: поисковые запросы, остатки, удержания, платное хранение",
    "content-api.wildberries.ru": "Карточки товаров, характеристики, категории, медиа, ярлыки",
    "advert-api.wildberries.ru": "Рекламные кампании, ставки, поисковые кластеры",
    "devapi-digital.wildberries.ru": "Цифровые товары: контент, предложения, ключи активации",
    "feedbacks-api.wildberries.ru": "Отзывы, вопросы, закреплённые отзывы",
    "discounts-prices-api.wildberries.ru": "Цены, скидки, календарь акций",
    "common-api.wildberries.ru": "Информация о продавце, тарифы, комиссии, новости",
    "supplies-api.wildberries.ru": "Поставки на склад WB и данные для их формирования",
    "finance-api.wildberries.ru": "Финансовые отчёты и баланс",
    "statistics-api.wildberries.ru": "Статистика: продажи, заказы, остатки, отчёт о реализации",
    "user-management-api.wildberries.ru": "Пользователи продавца и их права",
    "advert-media-api.wildberries.ru": "Медиа в рекламе и статистика по ним",
    "dp-calendar-api.wildberries.ru": "Календарь акций и участие в них",
    "buyer-chat-api.wildberries.ru": "Чат с покупателями",
    "documents-api.wildberries.ru": "Документы продавца",
    "returns-api.wildberries.ru": "Возвраты покупателями",
}

SAFETY_RU = {"read": "чтение", "write": "запись", "destructive": "необратимые"}

# Отдельные пакеты под каждый маркетплейс: тот же сервер, но имя, которым его
# ищут. Комбайн остаётся основным, обёртки нужны ровно для поиска и для тех,
# кому не нужны четыре площадки сразу.
WRAPPERS = {
    "ozon-api": ("ozon-mcp-ru", "Ozon"),
    "wildberries-api": ("wildberries-mcp-ru", "Wildberries"),
    "yandex-market-api": ("yandex-market-mcp-ru", "Яндекс Маркет"),
    "avito-api": ("avito-mcp-ru", "Авито"),
}



def load(rel: str) -> list[dict]:
    data = yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))
    return data["endpoints"]


def theme_rows(endpoints: list[dict], themes: dict[str, list[str]]) -> list[tuple]:
    """Свернуть разделы каталога в темы. Незамапленный раздел = ошибка сборки."""
    by_section = defaultdict(list)
    for e in endpoints:
        by_section[e.get("section", "?")].append(e)

    mapped = {s for names in themes.values() for s in names}
    unknown = sorted(set(by_section) - mapped)
    if unknown:
        raise SystemExit(
            "Разделы каталога не разложены по темам, поправь карту в скрипте: "
            + ", ".join(unknown)
        )

    rows = []
    for theme, sections in themes.items():
        eps = [e for s in sections for e in by_section.get(s, [])]
        c = Counter(e.get("safety", "?") for e in eps)
        rows.append((theme, len(eps), c["read"], c["write"], c["destructive"]))
    rows.sort(key=lambda r: -r[1])

    assert sum(r[1] for r in rows) == len(endpoints), "методы потерялись при группировке"
    return rows


def host_rows(endpoints: list[dict]) -> list[tuple]:
    c = Counter(e["host"] for e in endpoints)
    unknown = sorted(set(c) - set(WB_HOST_LABELS))
    if unknown:
        raise SystemExit("Нет подписи для хостов: " + ", ".join(unknown))
    return [(h, n, WB_HOST_LABELS[h]) for h, n in c.most_common()]


def esc(s: str) -> str:
    return html.escape(s, quote=True)


# --- проза страниц ----------------------------------------------------------
PAGES = {
    "ozon-api": {
        "title": "API Ozon Seller: как получить ключ, карта методов и частые ошибки",
        "h1": "API Ozon Seller: ключ, методы и ошибки",
        "desc": ("Как получить Client-Id и Api-Key в кабинете Ozon Seller, что умеет "
                 "Seller API и Performance API, карта из 486 методов по темам и разбор "
                 "частых ошибок: 401, 404 при дрейфе версий, 405 на импортированных "
                 "методах."),
        "lead": ("Ozon разводит продавца по двум разным API с разной авторизацией. "
                 "Seller API отвечает за товары, заказы, цены, финансы и отзывы, "
                 "Performance API за рекламу. Ниже: где взять ключи для обоих, что "
                 "внутри каждого раздела и что означают ошибки, на которые уходит "
                 "больше всего времени."),
        "keys": [
            ("Seller API: Client-Id и Api-Key",
             "Зайдите в кабинет <b class=\"mono\">seller.ozon.ru</b>, откройте "
             "<b>Настройки</b>, раздел <b>API-ключи</b>. Ozon выдаёт пару: "
             "<b class=\"mono\">Client-Id</b> (число) и <b class=\"mono\">Api-Key</b>. "
             "Оба уходят в заголовки одноимённых имён, хост запроса "
             "<b class=\"mono\">api-seller.ozon.ru</b>."),
            ("Performance API: client_id и client_secret",
             "Рекламный кабинет живёт отдельно и авторизуется по OAuth2: пара "
             "<b class=\"mono\">client_id</b> и <b class=\"mono\">client_secret</b> "
             "меняется на токен, хост <b class=\"mono\">api-performance.ozon.ru</b>. "
             "Ключи Seller API там не работают, и наоборот."),
            ("Куда положить, чтобы не хранить в открытую",
             "Сервер спросит ключи при первом запуске и положит их в "
             "<b class=\"mono\">~/.marketplace-mcp/cabinets.json</b> с правами "
             "<b class=\"mono\">chmod 600</b>. В репозиторий и в чат они не попадают. "
             "Магазинов можно подключить несколько и переключаться между ними прямо "
             "из чата."),
        ],
        "errors": [
            ("401 или «Client-Id should be positive integer», хотя ключ верный",
             "Первым делом смотрите не переменные окружения, а "
             "<b class=\"mono\">~/.marketplace-mcp/cabinets.json</b>: активный кабинет "
             "в этом файле имеет приоритет над env и молча затеняет то, что вы "
             "экспортировали в терминале."),
            ("404 на методе, который точно существует",
             "Ozon дрейфует по версиям, и разные разделы живут на разных: список "
             "товаров на <b class=\"mono\">v3</b>, атрибуты на <b class=\"mono\">v4</b>, "
             "цены на <b class=\"mono\">v5</b>. При 404 проверяйте версию в пути раньше "
             "всего остального."),
            ("405 Method Not Allowed",
             "Скорее всего это метод, импортированный из спецификации: путь у таких "
             "записей надёжный, а HTTP-глагол не всегда. Живая проба находила методы, "
             "помеченные GET, которые на деле POST. Сверьтесь с документацией или "
             "вызовите через <b class=\"mono\">call_raw</b>."),
        ],
        "prompts": [
            "покажи продажи на Ozon за неделю по дням",
            "какие товары с красным индексом цены",
            "вытащи отчёт о начислениях за прошлый месяц",
            "собери отзывы ниже 4 звёзд и сгруппируй жалобы",
        ],
        "methods_note": (" Оговорка про Ozon: он использует POST и для чтения тоже, "
                         "поэтому класс тут определяется по последнему сегменту пути, "
                         "а не по HTTP-глаголу. /v1/report/list читает, /v1/report/create "
                         "пишет."),
        "doc": ("https://docs.ozon.ru/api/seller/", "docs.ozon.ru/api/seller"),
        "faq": [
            ("Как получить API-ключ Ozon?",
             "seller.ozon.ru, раздел Настройки, пункт API-ключи. Ozon выдаёт пару "
             "Client-Id и Api-Key, оба нужны. Для рекламы ключи берутся отдельно, в "
             "Performance API, и авторизация там по OAuth2."),
            ("Чем Seller API отличается от Performance API у Ozon?",
             "Это два разных API с разной авторизацией и разными хостами. Seller API "
             "(api-seller.ozon.ru) отвечает за товары, заказы, цены, остатки, финансы и "
             "отзывы. Performance API (api-performance.ozon.ru) отвечает только за "
             "рекламу. Ключи одного в другом не работают."),
            ("Почему API Ozon отвечает 404 на существующий метод?",
             "Ozon дрейфует по версиям путей: список товаров на v3, атрибуты на v4, "
             "цены на v5. При 404 проверьте версию в пути раньше всего остального."),
            ("Сколько методов Ozon поддерживает marketplaces-mcp-ru?",
             "486: 441 метод Seller API и 45 методов Performance API. Каждый со схемой "
             "параметров и пометкой чтение, запись или необратимое действие."),
        ],
    },
    "wildberries-api": {
        "title": "API Wildberries: токен, 17 хостов, карта методов и ошибки",
        "h1": "API Wildberries: токен, хосты и ошибки",
        "desc": ("Как получить токен API в кабинете продавца Wildberries, почему у WB не "
                 "один домен, а семнадцать, полная таблица хостов, карта из 307 методов "
                 "и разбор ошибок: 401 из-за префикса Bearer и лимиты запросов."),
        "lead": ("Главная засада Wildberries не в токене, а в адресе. Единого "
                 "<b class=\"mono\">api.wildberries.ru</b> не существует: у каждого "
                 "назначения свой хост, и запрос на неверный домен выглядит как "
                 "сломанная авторизация. Ниже полная таблица хостов из каталога, "
                 "который грузит сервер."),
        "keys": [
            ("Где взять токен",
             "Кабинет <b class=\"mono\">seller.wildberries.ru</b>, раздел "
             "<b>Настройки</b>, пункт <b>Доступ к API</b>. Токен один на все хосты, но "
             "при создании выбираются категории доступа: выданный только под контент "
             "токен не пустят в статистику."),
            ("Как он уходит в запрос",
             "В заголовок <b class=\"mono\">Authorization</b>, и это важный нюанс: "
             "сервер шлёт raw-токен <b>без префикса</b> "
             "<b class=\"mono\">Bearer</b>. Подтверждено на практике. Если "
             "авторизация падает при верном токене, проверьте это первым."),
            ("Где он лежит",
             "В <b class=\"mono\">~/.marketplace-mcp/cabinets.json</b> с правами "
             "<b class=\"mono\">chmod 600</b>, локально. В репозиторий и в чат токен не "
             "попадает."),
        ],
        "errors": [
            ("401 при верном токене",
             "Две причины по частоте. Первая: WB ждёт raw-токен в "
             "<b class=\"mono\">Authorization</b> без <b class=\"mono\">Bearer</b>. "
             "Вторая: активный кабинет в "
             "<b class=\"mono\">~/.marketplace-mcp/cabinets.json</b> имеет приоритет над "
             "переменными окружения и затеняет то, что вы экспортировали."),
            ("404 или пустой ответ на рабочем методе",
             "Проверьте хост. У WB семнадцать доменов по назначению, и статистика на "
             "домене контента не отвечает. Таблица хостов выше."),
            ("429, превышен лимит запросов",
             "Лимиты у WB заданы поштучно и местами очень жёсткие: у части методов это "
             "один запрос в минуту, у отчётов бывает и реже. Лимит привязан к методу, "
             "а не к аккаунту целиком, поэтому упереться можно на одном отчёте, пока "
             "остальное работает."),
        ],
        "prompts": [
            "покажи продажи на WB за неделю",
            "вытащи финотчёт реализации за прошлый месяц",
            "что пора дозаказать, посчитай дни покрытия",
            "какие товары рискуют уйти в out-of-stock",
        ],
        "doc": ("https://dev.wildberries.ru/", "dev.wildberries.ru"),
        "faq": [
            ("Как получить API-токен Wildberries?",
             "seller.wildberries.ru, раздел Настройки, пункт Доступ к API. Токен один на "
             "все хосты, но при создании выбираются категории доступа: выданный только "
             "под контент токен не пустят в статистику."),
            ("Почему API Wildberries отвечает 401, хотя токен верный?",
             "Wildberries ждёт raw-токен в заголовке Authorization без префикса Bearer. "
             "Вторая частая причина: активный кабинет в ~/.marketplace-mcp/cabinets.json "
             "имеет приоритет над переменными окружения и молча затеняет их."),
            ("Какой адрес у API Wildberries?",
             "Единого адреса нет. У Wildberries семнадцать хостов по назначению: "
             "marketplace-api для сборочных заданий, statistics-api для продаж и "
             "остатков, content-api для карточек, discounts-prices-api для цен, "
             "seller-analytics-api для аналитики, feedbacks-api для отзывов и так далее. "
             "Полная таблица есть на этой странице."),
            ("Что делать при «превышен лимит запросов к API Wildberries»?",
             "Лимиты заданы поштучно, у части методов это один запрос в минуту. Лимит "
             "привязан к методу, а не к аккаунту, поэтому упереться можно на одном "
             "отчёте, пока остальные методы работают. Помогает кэшировать ответ и не "
             "дёргать отчёт в цикле."),
        ],
    },
    "yandex-market-api": {
        "title": "API Яндекс Маркета для продавцов: Api-Key, методы и ошибки",
        "h1": "API Яндекс Маркета: ключ и карта методов",
        "desc": ("Как получить Api-Key в кабинете партнёра Яндекс Маркета, что умеет "
                 "Partner API, карта из 165 методов по темам: заказы, отчёты, поставки, "
                 "товары, цены, отзывы и индекс качества."),
        "lead": ("У Яндекс Маркета одна точка входа и один ключ, так что подключение "
                 "проще, чем у соседей. Тонкость в другом: методы адресуются не только "
                 "магазином, но и бизнесом, и перепутать эти два идентификатора легко."),
        "keys": [
            ("Где взять Api-Key",
             "Кабинет партнёра <b class=\"mono\">partner.market.yandex.ru</b>, раздел "
             "<b>Настройки</b>, пункт <b>Доступ к API</b>. Ключ уходит в заголовок "
             "<b class=\"mono\">Api-Key</b>, хост "
             "<b class=\"mono\">api.partner.market.yandex.ru</b>."),
            ("Бизнес и кампания это разные идентификаторы",
             "Часть методов адресуется идентификатором бизнеса, часть номером кампании "
             "(магазина). Подставить один вместо другого даёт не ошибку доступа, а "
             "пустой ответ, что путает сильнее."),
            ("Где он лежит",
             "В <b class=\"mono\">~/.marketplace-mcp/cabinets.json</b> с правами "
             "<b class=\"mono\">chmod 600</b>, локально."),
        ],
        "errors": [
            ("Пустой ответ вместо данных",
             "Чаще всего перепутаны идентификатор бизнеса и номер кампании. Ошибки "
             "доступа при этом не будет, ответ придёт корректный и пустой."),
            ("Ошибка в имени поля",
             "Каталог методов собран из официального OpenAPI-документа, а живой прогон "
             "на реальных кабинетах ещё не делался. Неточности в именах полей возможны. "
             "<b class=\"mono\">describe_method</b> покажет схему, "
             "<b class=\"mono\">call_raw</b> даст поправить запрос на месте."),
            ("Метод не находится по названию",
             "Ищите по теме, а не по имени: спросите агента «что ты умеешь по Яндекс "
             "Маркету», он покажет разделы и подберёт метод сам."),
        ],
        "prompts": [
            "покажи заказы на Яндекс Маркете за неделю",
            "какой у меня индекс качества и что его роняет",
            "собери отчёт по продажам за месяц",
            "покажи товары в карантине цен",
        ],
        "doc": ("https://yandex.ru/dev/market/partner-api/doc/ru/",
                "yandex.ru/dev/market/partner-api"),
        "faq": [
            ("Как получить API-ключ Яндекс Маркета?",
             "partner.market.yandex.ru, раздел Настройки, пункт Доступ к API. Ключ "
             "уходит в заголовок Api-Key, хост api.partner.market.yandex.ru."),
            ("Почему Partner API возвращает пустой ответ?",
             "Чаще всего перепутаны идентификатор бизнеса и номер кампании. Часть "
             "методов адресуется бизнесом, часть кампанией, и подстановка одного вместо "
             "другого даёт не ошибку доступа, а корректный пустой ответ."),
            ("Сколько методов Яндекс Маркета поддерживает marketplaces-mcp-ru?",
             "165, собранных из официального OpenAPI-документа: заказы, отчёты, "
             "поставки, товары, цены, отзывы, чаты и индекс качества. Живой прогон на "
             "реальных кабинетах пока не делался, поэтому неточности в именах полей "
             "возможны."),
        ],
    },
    "avito-api": {
        "title": "API Авито для бизнеса: client_id, client_secret и карта методов",
        "h1": "API Авито: доступ и карта методов",
        "desc": ("Как получить client_id и client_secret в разделе Интеграции на Авито, "
                 "как работает OAuth2, карта из 64 методов: объявления, заказы Авито "
                 "Доставки, мессенджер, продвижение, отзывы и остатки."),
        "lead": ("Авито авторизуется по OAuth2, а не по постоянному ключу: пара "
                 "<b class=\"mono\">client_id</b> и <b class=\"mono\">client_secret</b> "
                 "меняется на токен с ограниченным сроком жизни. Обновление токена "
                 "сервер берёт на себя."),
        "keys": [
            ("Где взять пару",
             "На <b class=\"mono\">avito.ru</b>: <b>Для бизнеса</b>, раздел "
             "<b>Интеграции</b>, пункт <b>API</b>. Там выдаётся "
             "<b class=\"mono\">client_id</b> и <b class=\"mono\">client_secret</b>. "
             "Хост запросов <b class=\"mono\">api.avito.ru</b>."),
            ("Как это превращается в токен",
             "Пара меняется на access-токен по OAuth2, срок жизни ограничен. Сервер "
             "обновляет токен сам, вручную ничего перевыпускать не нужно."),
            ("Где всё лежит",
             "В <b class=\"mono\">~/.marketplace-mcp/cabinets.json</b> с правами "
             "<b class=\"mono\">chmod 600</b>, локально."),
        ],
        "errors": [
            ("401 после того, как всё работало",
             "Токен Авито живёт ограниченное время. Если запрос идёт мимо сервера, "
             "своим кодом, токен надо обновлять; через сервер это происходит само."),
            ("403 на методе, который есть в документации",
             "У Авито доступ к разделам выдаётся по заявке и не одинаков у всех "
             "аккаунтов. Мессенджер и Авито Доставка открываются не каждому бизнесу."),
            ("Ошибка в имени поля",
             "Каталог собран из официальных документов, живой прогон на реальных "
             "кабинетах ещё не делался. <b class=\"mono\">describe_method</b> покажет "
             "схему, <b class=\"mono\">call_raw</b> даст поправить запрос на месте."),
        ],
        "prompts": [
            "покажи статистику по объявлениям за неделю",
            "какие заказы Авито Доставки в работе",
            "собери непрочитанные сообщения из мессенджера",
            "обнови остатки по объявлениям",
        ],
        "doc": ("https://developers.avito.ru/", "developers.avito.ru"),
        "faq": [
            ("Как получить API-ключ Авито?",
             "На avito.ru: раздел Для бизнеса, пункт Интеграции, подраздел API. Авито "
             "выдаёт не ключ, а пару client_id и client_secret, которая по OAuth2 "
             "меняется на токен с ограниченным сроком жизни."),
            ("Есть ли у Авито API для объявлений и мессенджера?",
             "Да. В каталоге 64 метода: объявления и статистика, заказы Авито Доставки, "
             "мессенджер, продвижение, отзывы и рейтинг, остатки, автозагрузка "
             "объявлений файлом, баланс и операции."),
            ("Почему API Авито отвечает 403?",
             "Доступ к разделам у Авито выдаётся по заявке и не одинаков у всех "
             "аккаунтов. Мессенджер и Авито Доставка открываются не каждому бизнесу."),
        ],
    },
}

NAV = """<header>
  <div class="wrap nav">
    <a class="brand" href="{site}/" aria-label="marketplaces-mcp-ru, на главную">
      <span class="bars" aria-hidden="true"><span></span><span></span><span></span></span>
      marketplaces-mcp-ru <small>· AI Frontier</small>
    </a>
    <nav class="nav-links" aria-label="Основная навигация">
      <a href="ozon-api.html">Ozon</a>
      <a href="wildberries-api.html">Wildberries</a>
      <a href="yandex-market-api.html">Яндекс Маркет</a>
      <a href="avito-api.html">Авито</a>
      <a href="{business}">Деловые сервисы: hh.ru, VK, ЭДО</a>
      <a class="btn btn-primary" href="{repo}">GitHub</a>
    </nav>
  </div>
</header>"""

FOOTER = """<footer>
  <div class="wrap foot">
    <div>
      <span class="alpha">alpha</span>
      &nbsp; Инструмент, а не замена аналитику. Решения по цене и закупкам за вами.
    </div>
    <div>
      <a href="{repo}">GitHub</a> ·
      <a href="{business}">business-mcp-ru</a> ·
      <a href="https://t.me/gorilla_under_hood">Telegram</a> ·
      Сделано в <a href="https://aifrontier.tech">AI Frontier</a> · MIT
    </div>
  </div>
</footer>"""


def render_theme_table(rows, caption):
    body = "\n".join(
        "        <tr><td>%s</td><td class=\"num\">%d</td><td class=\"num\">%d</td>"
        "<td class=\"num\">%d</td><td class=\"num\">%d</td></tr>"
        % (esc(t), n, r, w, d) for t, n, r, w, d in rows)
    total = sum(r[1] for r in rows)
    return """      <div class="tw">
      <table class="mtable">
        <caption>%s</caption>
        <thead><tr><th>Раздел</th><th class="num">Методов</th><th class="num">Чтение</th><th class="num">Запись</th><th class="num">Необратимые</th></tr></thead>
        <tbody>
%s
        </tbody>
        <tfoot><tr><th>Всего</th><th class="num">%d</th><th class="num"></th><th class="num"></th><th class="num"></th></tr></tfoot>
      </table>
      </div>""" % (esc(caption), body, total)


def render_host_table(rows):
    body = "\n".join(
        "        <tr><td><b class=\"mono\">%s</b></td><td class=\"num\">%d</td><td>%s</td></tr>"
        % (esc(h), n, esc(label)) for h, n, label in rows)
    return """      <div class="tw">
      <table class="mtable">
        <caption>Хосты API Wildberries: свой домен на каждое назначение</caption>
        <thead><tr><th>Хост</th><th class="num">Методов</th><th>За что отвечает</th></tr></thead>
        <tbody>
%s
        </tbody>
      </table>
      </div>""" % body


def build_page(slug: str, cfg: dict, tables_html: str) -> str:
    url = "%s/%s.html" % (SITE, slug)
    wrap_pkg, wrap_name = WRAPPERS[slug]
    wrap_repo = "https://github.com/ilyautov/" + wrap_pkg
    # Вопрос «а можно только один маркетплейс» задают чаще, чем кажется, и
    # ответ на него это имя пакета. Дописывается здесь, а не в PAGES, чтобы
    # формулировка на всех четырёх страницах была одна.
    faq = list(cfg["faq"]) + [(
        "Можно поставить только %s, без остальных маркетплейсов?" % wrap_name,
        "Да, для этого есть отдельный пакет %s: он поднимает один сервер %s, без "
        "остальных площадок. Внутри тот же код и тот же каталог, что в "
        "marketplaces-mcp-ru, они приходят зависимостью. Строка установки лежит "
        "в его репозитории." % (wrap_pkg, wrap_name),
    )]
    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq
        ],
    }
    crumbs_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "marketplaces-mcp-ru",
             "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": cfg["h1"], "item": url},
        ],
    }

    keys = "\n".join(
        """        <div class="step">
          <div>
            <h3>%s</h3>
            <p>%s</p>
          </div>
        </div>""" % (esc(h), body) for h, body in cfg["keys"])

    errors = "\n".join(
        """        <div class="faq-item">
          <h3>%s</h3>
          <p>%s</p>
        </div>""" % (esc(h), body) for h, body in cfg["errors"])

    prompts = "\n".join('          <span class="prompt">%s</span>' % esc(p)
                        for p in cfg["prompts"])

    faq_html = "\n".join(
        """        <div class="faq-item">
          <h3>%s</h3>
          <p>%s</p>
        </div>""" % (esc(q), esc(a)) for q, a in faq)

    doc_url, doc_label = cfg["doc"]

    return """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{site}/assets/social-preview.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{url}">
<link rel="icon" type="image/png" href="assets/social-preview.png">
<link rel="apple-touch-icon" href="assets/social-preview.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Lora:wght@500;600;700&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
<script type="application/ld+json">
{crumbs}
</script>
<script type="application/ld+json">
{faq_ld}
</script>
</head>
<body>

{nav}

<main id="top">

  <section class="s">
    <div class="wrap">
      <nav class="crumbs" aria-label="Хлебные крошки">
        <a href="index.html">Главная</a> · {h1}
      </nav>
      <div class="sec-head">
        <h1>{h1}</h1>
        <p>{lead}</p>
      </div>
    </div>
  </section>

  <!-- КЛЮЧИ -->
  <section class="s alt" id="keys">
    <div class="wrap">
      <div class="sec-head">
        <h2>Как получить доступ</h2>
      </div>
      <div class="steps">
{keys}
      </div>
    </div>
  </section>

  <!-- КАРТА МЕТОДОВ -->
  <section class="s" id="methods">
    <div class="wrap">
      <div class="sec-head">
        <h2>Карта методов</h2>
        <p>Таблицы собраны из того же каталога, который грузит сервер, поэтому они не расходятся с кодом. Колонки показывают, как метод классифицирует safety-гейт: перед записью агент предупреждает, перед необратимым действием требует подтверждения.{methods_note}</p>
      </div>
{tables}
      <p class="small" style="color:var(--mute);margin-top:20px;max-width:70ch">
        Курированное ядро выверено на живых кабинетах. Остальное импортировано из спецификаций: пути надёжны, HTTP-глаголы не всегда, считайте такие записи картой для разведки. Официальная документация: <a href="{doc_url}">{doc_label}</a>.
      </p>
    </div>
  </section>

  <!-- ОШИБКИ -->
  <section class="s alt" id="errors">
    <div class="wrap">
      <div class="sec-head">
        <h2>Частые ошибки и что они значат</h2>
      </div>
      <div class="faq">
{errors}
      </div>
    </div>
  </section>

  <!-- В ЧАТЕ -->
  <section class="s" id="chat">
    <div class="wrap">
      <div class="sec-head">
        <h2>То же самое одной фразой</h2>
        <p>Если разбираться с методами руками не хочется, всё перечисленное выше вызывается из чата обычными словами. Проект и есть MCP-сервер: он отдаёт эти методы ИИ-ассистенту как инструменты, а тот подбирает нужный сам.</p>
      </div>
      <div class="usage">
        <div class="ucard">
          <h3>Скажите так</h3>
{prompts}
        </div>
        <div class="ucard">
          <h3>Что для этого нужно</h3>
          <p>Ключи из первого раздела и одна строка установки. Нужен только {wrap_name}: отдельный пакет <a href="{wrap_repo}"><b class="mono">{wrap_pkg}</b></a>, тот же сервер одним маркетплейсом. Нужны все четыре: <b class="mono">npx -y marketplaces-mcp-ru</b> или <b class="mono">uvx marketplaces-mcp-ru</b>, а в Claude Desktop бандл <b class="mono">.mcpb</b> из релизов ставится в один клик.</p>
          <p style="margin-top:12px"><a class="btn btn-primary" href="index.html#install">Как установить</a></p>
        </div>
      </div>
    </div>
  </section>

  <!-- FAQ -->
  <section class="s alt" id="faq">
    <div class="wrap">
      <div class="sec-head">
        <h2>Частые вопросы</h2>
      </div>
      <div class="faq">
{faq_html}
      </div>
    </div>
  </section>

  <section class="s">
    <div class="wrap">
      <div class="oss">
        <div class="kicker">открытый проект</div>
        <h2>Каталог методов открыт. Берите, форкайте, улучшайте.</h2>
        <p>Всё это лежит в репозитории под MIT, включая машиночитаемые каталоги, из которых собраны таблицы на этой странице. Нашли неточность в методе, поправьте или заведите issue.</p>
        <div class="cta-row">
          <a class="btn btn-primary" href="{repo}">★ Открыть на GitHub</a>
          <a class="btn btn-ghost" href="{wrap_repo}">Пакет {wrap_pkg}</a>
          <a class="btn btn-ghost" href="{repo}/issues">Завести issue</a>
        </div>
        <div class="repo-line">github.com/ilyautov/marketplaces-mcp-ru</div>
      </div>
    </div>
  </section>

</main>

{footer}

</body>
</html>
""".format(
        title=esc(cfg["title"]), desc=esc(cfg["desc"]), url=url, site=SITE,
        crumbs=json.dumps(crumbs_ld, ensure_ascii=False, indent=2),
        faq_ld=json.dumps(faq_ld, ensure_ascii=False, indent=2),
        nav=NAV.format(site=SITE, repo=REPO, business=BUSINESS), h1=esc(cfg["h1"]), lead=cfg["lead"],
        keys=keys, tables=tables_html, doc_url=doc_url, doc_label=doc_label,
        methods_note=cfg.get("methods_note", ""),
        errors=errors, prompts=prompts, faq_html=faq_html, repo=REPO,
        wrap_pkg=wrap_pkg, wrap_name=esc(wrap_name), wrap_repo=wrap_repo,
        footer=FOOTER.format(repo=REPO, business=BUSINESS),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="ничего не писать, только собрать и сверить с файлами на диске")
    args = ap.parse_args()

    ozon = load("ozon_mcp/endpoints.yaml")
    perf = load("ozon_mcp/perf_endpoints.yaml")
    wb = load("wb_mcp/endpoints.yaml")
    ya = load("yandex_mcp/endpoints.yaml")
    av = load("avito_mcp/endpoints.yaml")

    total = len(ozon) + len(perf) + len(wb) + len(ya) + len(av)
    if total != 1022:
        raise SystemExit("Всего методов %d, а README обещает 1022. Сверь цифру." % total)

    # у Авито и Яндекса разделы уже названы по-русски, группировать нечего
    av_themes = {s: [s] for s in sorted({e["section"] for e in av})}

    tables = {
        "ozon-api": (render_theme_table(theme_rows(ozon, OZON_THEMES),
                                        "Seller API, %d метода" % len(ozon))
                     + "\n" +
                     render_theme_table(theme_rows(perf, OZON_PERF_THEMES),
                                        "Performance API (реклама), %d методов" % len(perf))),
        "wildberries-api": (render_host_table(host_rows(wb))),
        "yandex-market-api": render_theme_table(theme_rows(ya, YANDEX_THEMES),
                                                "Partner API, %d метода" % len(ya)),
        "avito-api": render_theme_table(theme_rows(av, av_themes),
                                        "API Авито, %d метода" % len(av)),
    }

    stale = []
    for slug, cfg in PAGES.items():
        page = build_page(slug, cfg, tables[slug])
        path = DOCS / (slug + ".html")
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != page:
                stale.append(path.name)
        else:
            path.write_text(page, encoding="utf-8")
            print("собрано: docs/%s.html (%d байт)" % (slug, len(page.encode())))

    if args.check:
        if stale:
            print("страницы разошлись с каталогом: " + ", ".join(stale), file=sys.stderr)
            return 1
        print("все страницы совпадают с каталогом")
        return 0

    # sitemap: главная плюс сгенерированные страницы
    today = date.today().isoformat()
    urls = ["%s/" % SITE] + ["%s/%s.html" % (SITE, s) for s in PAGES]
    body = "\n".join(
        "  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n"
        "    <changefreq>weekly</changefreq>\n    <priority>%s</priority>\n  </url>"
        % (u, today, "1.0" if i == 0 else "0.8") for i, u in enumerate(urls))
    (DOCS / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + body + "\n</urlset>\n", encoding="utf-8")
    print("собрано: docs/sitemap.xml (%d адресов)" % len(urls))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
