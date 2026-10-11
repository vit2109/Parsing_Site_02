"""Сохранение извлечённых таблиц в CSV/JSONL (используется при extract_tables = true)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from parsing_site.config import OutputConfig
from parsing_site.parser import ExtractedData


@dataclass(slots=True)
class ProcessResult:
    """Метрики одного запуска универсального HTML-парсера."""

    timestamp: str
    url: str
    title: str
    fields: dict[str, Any]
    metrics: dict[str, float]
    table_shapes: list[tuple[int, int]]
    deltas: dict[str, float]
    notes: list[str] = field(default_factory=list)


class DataProcessor:
    """Накапливает снимки страницы и считает метрики.

    Свою логику добавляйте в `custom_compute`.
    """

    def __init__(self, output: OutputConfig) -> None:
        """Готовит пути файлов и пустую историю результатов процесса."""
        self._output = output
        self._history: list[ProcessResult] = []
        self._jsonl_path = output.data_dir / "snapshots.jsonl"
        self._csv_path = output.data_dir / "metrics.csv"

    @property
    def history(self) -> list[ProcessResult]:
        """Возвращает копию накопленной в памяти истории."""
        return list(self._history)

    def process(self, data: ExtractedData, html: str | None = None) -> ProcessResult:
        """Считает метрики/дельты, сохраняет результат и возвращает его."""
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        metrics = _collect_metrics(data)
        metrics.update(self.custom_compute(data, self._history))

        previous = self._history[-1] if self._history else None
        deltas = _compute_deltas(metrics, previous.metrics if previous else None)

        result = ProcessResult(
            timestamp=timestamp,
            url=data.url,
            title=data.title,
            fields=data.fields,
            metrics=metrics,
            table_shapes=[(int(df.shape[0]), int(df.shape[1])) for df in data.tables],
            deltas=deltas,
            notes=_build_notes(data, deltas),
        )
        self._history.append(result)
        self._persist(result, data, html)
        return result

    def custom_compute(
        self, data: ExtractedData, history: list[ProcessResult]
    ) -> dict[str, float]:
        """Место для прикладных расчётов.

        Верните словарь числовых метрик — они попадут в CSV и в дельты.
        """
        extra: dict[str, float] = {}
        extra["poll_index"] = float(len(history) + 1)
        extra["tables_count"] = float(len(data.tables))
        extra["fields_count"] = float(len(data.fields))

        numeric_values = _numeric_field_values(data.fields)
        if numeric_values:
            extra["fields_sum"] = float(sum(numeric_values))
            extra["fields_avg"] = float(sum(numeric_values) / len(numeric_values))
            extra["fields_min"] = float(min(numeric_values))
            extra["fields_max"] = float(max(numeric_values))

        for index, table in enumerate(data.tables):
            numeric = table.select_dtypes(include="number")
            if numeric.empty:
                continue
            extra[f"table_{index}_numeric_sum"] = float(numeric.to_numpy().sum())
            extra[f"table_{index}_numeric_mean"] = float(numeric.to_numpy().mean())
        return extra

    def _persist(
        self, result: ProcessResult, data: ExtractedData, html: str | None
    ) -> None:
        """Записывает включённые форматы и последние извлечённые таблицы."""
        self._output.data_dir.mkdir(parents=True, exist_ok=True)

        if self._output.save_jsonl:
            payload = {
                "timestamp": result.timestamp,
                "url": result.url,
                "title": result.title,
                "fields": result.fields,
                "metrics": result.metrics,
                "deltas": result.deltas,
                "table_shapes": result.table_shapes,
            }
            with self._jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

        if self._output.save_csv:
            _append_metrics_csv(self._csv_path, result)

        if self._output.save_html and html:
            stamp = result.timestamp.replace(":", "-")
            (self._output.data_dir / f"page_{stamp}.html").write_text(
                html, encoding="utf-8"
            )

        if data.tables:
            latest_dir = self._output.data_dir / "latest_tables"
            latest_dir.mkdir(parents=True, exist_ok=True)
            for index, table in enumerate(data.tables):
                table.to_csv(latest_dir / f"table_{index}.csv", index=False)


def format_result(result: ProcessResult) -> str:
    """Форматирует результат универсального парсинга для терминала."""
    lines = [
        f"[{result.timestamp}] {result.title}",
        f"  URL: {result.url}",
    ]
    if result.fields:
        lines.append("  Поля:")
        for key, value in result.fields.items():
            lines.append(f"    {key}: {_short(value)}")
    if result.table_shapes:
        shapes = ", ".join(f"{rows}x{cols}" for rows, cols in result.table_shapes)
        lines.append(f"  Таблицы: {shapes}")
    if result.metrics:
        interesting = {
            key: value
            for key, value in result.metrics.items()
            if key not in {"poll_index", "tables_count", "fields_count"}
        }
        if interesting:
            lines.append("  Метрики:")
            for key, value in interesting.items():
                lines.append(f"    {key}: {value:g}")
    if result.deltas:
        lines.append("  Изменения с прошлого опроса:")
        for key, value in result.deltas.items():
            sign = "+" if value > 0 else ""
            lines.append(f"    {key}: {sign}{value:g}")
    for note in result.notes:
        lines.append(f"  ! {note}")
    return "\n".join(lines)


def _collect_metrics(data: ExtractedData) -> dict[str, float]:
    """Выбирает числовые значения из именованных полей страницы."""
    metrics: dict[str, float] = {}
    for key, value in data.fields.items():
        number = _to_float(value)
        if number is not None:
            metrics[key] = number
    return metrics


def _numeric_field_values(fields: dict[str, Any]) -> list[float]:
    """Собирает все числа из одиночных и списочных значений полей."""
    values: list[float] = []
    for value in fields.values():
        if isinstance(value, list):
            for item in value:
                number = _to_float(item)
                if number is not None:
                    values.append(number)
        else:
            number = _to_float(value)
            if number is not None:
                values.append(number)
    return values


def _to_float(value: Any) -> float | None:
    """Мягко извлекает число из Python-значения или локализованной строки."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
        filtered = "".join(ch for ch in cleaned if ch.isdigit() or ch in ".-")
        if filtered in {"", "-", ".", "-."}:
            return None
        try:
            return float(filtered)
        except ValueError:
            return None
    return None


def _compute_deltas(
    current: dict[str, float], previous: dict[str, float] | None
) -> dict[str, float]:
    """Считает изменившиеся метрики относительно предыдущего снимка."""
    if not previous:
        return {}
    deltas: dict[str, float] = {}
    for key, value in current.items():
        if key == "poll_index":
            continue
        if key in previous:
            delta = value - previous[key]
            if abs(delta) > 1e-12:
                deltas[key] = delta
    return deltas


def _build_notes(data: ExtractedData, deltas: dict[str, float]) -> list[str]:
    """Формирует диагностические заметки о пустом или изменившемся результате."""
    notes: list[str] = []
    if not data.fields and not data.tables:
        notes.append(
            "Данные не извлечены. Заполните [extract.selectors] в config.toml "
            "или проверьте, что на странице есть таблицы."
        )
    changed = [key for key, value in deltas.items() if value != 0]
    if changed:
        notes.append("Изменились: " + ", ".join(changed))
    return notes


def _short(value: Any, limit: int = 120) -> str:
    """Обрезает длинное отображение значения для терминала."""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _append_metrics_csv(path: Path, result: ProcessResult) -> None:
    """Дописывает метрики в CSV, расширяя заголовок при появлении новых колонок."""
    row = {
        "timestamp": result.timestamp,
        "url": result.url,
        "title": result.title,
        **result.metrics,
        **{f"delta_{key}": value for key, value in result.deltas.items()},
    }
    fieldnames: list[str] = []
    old_rows: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = list(reader.fieldnames or [])
            old_rows = list(reader)

    for key in row:
        if key not in fieldnames:
            fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(old_rows)
        writer.writerow(row)
