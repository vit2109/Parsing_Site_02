"""Извлечение таблиц и блоков HTML по CSS-селекторам (режим extract, не tracking)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from io import StringIO
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup, Tag


@dataclass(slots=True)
class ExtractedData:
    """Результат универсального разбора страницы вне режима карты."""

    url: str
    title: str
    fields: dict[str, Any] = field(default_factory=dict)
    tables: list[pd.DataFrame] = field(default_factory=list)
    outline: dict[str, Any] = field(default_factory=dict)


def parse_html(
    html: str,
    *,
    url: str = "",
    title: str = "",
    selectors: dict[str, str] | None = None,
    extract_tables: bool = True,
    tables_limit: int = 10,
    with_outline: bool = False,
) -> ExtractedData:
    """Извлекает выбранные CSS-поля, HTML-таблицы и необязательный обзор DOM."""
    soup = _make_soup(html)
    page_title = title or _text(soup.find("title")) or ""

    fields: dict[str, Any] = {}
    for name, spec in (selectors or {}).items():
        fields[name] = _extract_by_spec(soup, spec)

    tables: list[pd.DataFrame] = []
    if extract_tables:
        tables = _read_tables(html, limit=tables_limit)

    outline: dict[str, Any] = {}
    if with_outline:
        outline = build_outline(soup)

    return ExtractedData(
        url=url,
        title=page_title,
        fields=fields,
        tables=tables,
        outline=outline,
    )


def build_outline(soup: BeautifulSoup) -> dict[str, Any]:
    """Собирает краткую структуру страницы для подбора селекторов."""
    headings = [
        {"tag": tag.name, "text": _text(tag)[:200]}
        for tag in soup.find_all(["h1", "h2", "h3"])
        if _text(tag)
    ]
    ids = [tag["id"] for tag in soup.find_all(id=True)]
    classes: Counter[str] = Counter()
    for tag in soup.find_all(class_=True):
        class_value = tag.get("class") or []
        if isinstance(class_value, str):
            classes[class_value] += 1
        else:
            classes.update(class_value)

    tables_info = []
    for index, table in enumerate(soup.find_all("table"), start=1):
        rows = table.find_all("tr")
        cols = max((len(row.find_all(["th", "td"])) for row in rows), default=0)
        caption = _text(table.find("caption"))
        tables_info.append(
            {
                "index": index,
                "rows": len(rows),
                "cols": cols,
                "caption": caption,
                "id": table.get("id") or "",
            }
        )

    return {
        "headings": headings[:40],
        "ids": ids[:80],
        "top_classes": classes.most_common(30),
        "tables": tables_info,
        "forms": len(soup.find_all("form")),
        "links": len(soup.find_all("a")),
        "images": len(soup.find_all("img")),
    }


def format_outline(data: ExtractedData) -> str:
    """Форматирует обзор DOM в удобный для терминала текст."""
    lines = [
        f"URL: {data.url}",
        f"Заголовок: {data.title}",
        "",
        "Заголовки:",
    ]
    headings = data.outline.get("headings") or []
    if headings:
        for item in headings:
            lines.append(f"  <{item['tag']}> {item['text']}")
    else:
        lines.append("  (нет h1–h3)")

    lines.append("")
    lines.append("Таблицы:")
    tables = data.outline.get("tables") or []
    if tables:
        for item in tables:
            caption = f" «{item['caption']}»" if item["caption"] else ""
            ident = f" id={item['id']}" if item["id"] else ""
            lines.append(
                f"  #{item['index']}: {item['rows']} строк x {item['cols']} "
                f"колонок{ident}{caption}"
            )
    else:
        lines.append("  (нет <table>)")

    lines.append("")
    lines.append("Частые class:")
    top_classes = data.outline.get("top_classes") or []
    if top_classes:
        for name, count in top_classes:
            lines.append(f"  .{name}  ({count})")
    else:
        lines.append("  (нет)")

    ids = data.outline.get("ids") or []
    lines.append("")
    lines.append("id (первые):")
    if ids:
        for ident in ids[:25]:
            lines.append(f"  #{ident}")
    else:
        lines.append("  (нет)")

    lines.append("")
    lines.append(
        f"Формы: {data.outline.get('forms', 0)}, "
        f"ссылки: {data.outline.get('links', 0)}, "
        f"картинки: {data.outline.get('images', 0)}"
    )
    return "\n".join(lines)


def _make_soup(html: str) -> BeautifulSoup:
    """Создаёт BeautifulSoup с резервным стандартным HTML-парсером."""
    try:
        return BeautifulSoup(html, "lxml")
    # lxml может выбросить разные ошибки загрузки/разбора; стандартный parser — fallback.
    except Exception:  # noqa: BLE001
        return BeautifulSoup(html, "html.parser")


def _extract_by_spec(soup: BeautifulSoup, spec: str) -> Any:
    """Извлекает текст или атрибут по спецификации ``селектор@атрибут``."""
    selector, _, attr = spec.partition("@")
    selector = selector.strip()
    attr = attr.strip()
    if not selector:
        return None

    nodes = soup.select(selector)
    if not nodes:
        return None

    values = [_node_value(node, attr) for node in nodes]
    values = [value for value in values if value not in (None, "")]
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return values


def _node_value(node: Tag, attr: str) -> str | None:
    """Возвращает указанный атрибут узла либо очищенный текст."""
    if attr:
        value = node.get(attr)
        if value is None:
            return None
        if isinstance(value, list):
            return " ".join(value).strip()
        return str(value).strip()
    return _text(node)


def _text(node: Tag | None) -> str:
    """Схлопывает пробелы в текстовом содержимом HTML-узла."""
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def _read_tables(html: str, *, limit: int) -> list[pd.DataFrame]:
    """Читает непустые HTML-таблицы через pandas с резервным парсером."""
    try:
        frames = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError:
        return []
    # pandas оборачивает ошибки HTML-бэкендов в несколько разных типов.
    except Exception:  # noqa: BLE001
        try:
            frames = pd.read_html(StringIO(html), flavor="bs4")
        except Exception:  # noqa: BLE001
            return []
    return [frame for frame in frames[:limit] if not frame.empty]
