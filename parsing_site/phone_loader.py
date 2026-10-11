"""
Загрузка телефонов из Excel файла addresses_updated_02.xlsx
Сопоставление по полному совпадению поля "adres" с названием статичного объекта
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from parsing_site.config import ROOT

logger = logging.getLogger(__name__)


class PhoneLoader:
    """Загрузка телефонов из Excel и сопоставление с адресами по полному совпадению"""

    def __init__(self, excel_path: Path | None = None) -> None:
        """Загружает адреса и телефоны из указанного или стандартного XLSX."""
        self.excel_path = excel_path or ROOT / "addresses_updated_02.xlsx"
        self._data: dict[str, str] = {}  # нормализованный адрес -> телефон
        self._original_data: dict[str, str] = {}  # оригинальный адрес -> телефон
        self._normalized_original: dict[
            str, str
        ] = {}  # нормализованный -> оригинальный
        self._load_data()

    def _normalize_address(self, address: str) -> str:
        """
        Нормализует адрес для сопоставления:
        - Удаляет лишние пробелы
        - Приводит к нижнему регистру
        - Удаляет точки и запятые
        - Удаляет лишние пробелы внутри
        """
        if not address:
            return ""

        # Приводим к нижнему регистру
        normalized = address.lower().strip()

        # Удаляем множественные пробелы
        normalized = re.sub(r"\s+", " ", normalized)

        # Удаляем точки и запятые (но не в номерах)
        normalized = re.sub(r"[.,;:]", "", normalized)

        # Удаляем лишние пробелы в начале и конце
        normalized = normalized.strip()

        return normalized

    def _load_data(self) -> None:
        """Загружает данные из Excel файла"""
        if not self.excel_path.exists():
            logger.warning("Файл телефонов не найден: %s", self.excel_path)
            return

        try:
            # Читаем Excel файл
            df = pd.read_excel(self.excel_path)

            # Проверяем наличие необходимых колонок
            if "adres" not in df.columns:
                logger.warning("В файле телефонов отсутствует колонка 'adres'")
                return

            if "telephone" not in df.columns:
                logger.warning("В файле телефонов отсутствует колонка 'telephone'")
                return

            # Заполняем словари
            for _, row in df.iterrows():
                adres = str(row["adres"]).strip()
                telephone = str(row["telephone"]).strip()

                if adres and adres != "nan" and telephone and telephone != "nan":
                    # Сохраняем оригинальный адрес
                    self._original_data[adres] = telephone

                    # Сохраняем нормализованный адрес для поиска
                    normalized = self._normalize_address(adres)
                    if normalized:
                        self._data[normalized] = telephone
                        self._normalized_original[normalized] = adres

            logger.info(
                "Загружено %s телефонов из %s (исходных записей: %s)",
                len(self._data),
                self.excel_path.name,
                len(self._original_data),
            )

        # Ошибка внешнего XLSX не должна останавливать основной мониторинг.
        except Exception:
            logger.exception("Ошибка загрузки Excel с телефонами")

    def get_phone(self, address: str) -> str | None:
        """
        Получить телефон по точному совпадению адреса
        Возвращает телефон только при полном совпадении
        """
        if not address:
            return None

        # Пробуем точное совпадение с оригинальным адресом
        if address in self._original_data:
            return self._original_data[address]

        # Пробуем точное совпадение с нормализованным адресом
        normalized = self._normalize_address(address)
        if normalized in self._data:
            return self._data[normalized]

        return None

    def get_phone_strict(self, address: str) -> str | None:
        """
        Строгое сопоставление - только полное совпадение
        Без всяких частичных совпадений
        """
        return self.get_phone(address)

    def get_all_phones(self) -> dict[str, str]:
        """Получить все телефоны (оригинальные адреса)"""
        return self._original_data.copy()

    def get_all_normalized(self) -> dict[str, str]:
        """Получить все телефоны (нормализованные адреса)"""
        return self._data.copy()

    def find_exact_match(self, address: str) -> tuple[str | None, str | None]:
        """
        Найти точное совпадение
        Возвращает: (найденный_адрес, телефон) или (None, None)
        """
        if not address:
            return None, None

        # Проверяем оригинальный адрес
        if address in self._original_data:
            return address, self._original_data[address]

        # Проверяем нормализованный адрес
        normalized = self._normalize_address(address)
        if normalized in self._data:
            # Связываем результат с адресом напрямую: один телефон может
            # принадлежать нескольким различным адресам.
            return self._normalized_original[normalized], self._data[normalized]

        return None, None

    def get_stats(self) -> dict[str, Any]:
        """Статистика по загруженным данным"""
        return {
            "total": len(self._data),
            "original_total": len(self._original_data),
            "file": str(self.excel_path),
            "sample": list(self._original_data.items())[:5],
        }

    def verify_matching(self, test_addresses: list[str]) -> dict[str, dict]:
        """
        Проверка сопоставления для списка адресов
        Возвращает словарь с результатами проверки
        """
        results = {}
        for addr in test_addresses:
            phone = self.get_phone(addr)
            results[addr] = {
                "phone": phone,
                "found": phone is not None,
                "normalized": self._normalize_address(addr),
            }
        return results


# Создаем глобальный экземпляр
_phone_loader: PhoneLoader | None = None


def get_phone_loader() -> PhoneLoader:
    """Получить экземпляр PhoneLoader (синглтон)"""
    global _phone_loader
    if _phone_loader is None:
        _phone_loader = PhoneLoader()
    return _phone_loader


def get_phone_for_static(static_name: str) -> str | None:
    """
    Получить телефон по имени статичной точки (ТОЛЬКО ПОЛНОЕ СОВПАДЕНИЕ)
    """
    loader = get_phone_loader()
    return loader.get_phone(static_name)


def get_address_and_phone_for_static(static_name: str) -> tuple[str | None, str | None]:
    """
    Получить адрес и телефон по имени статичной точки (ТОЛЬКО ПОЛНОЕ СОВПАДЕНИЕ)
    """
    loader = get_phone_loader()
    return loader.find_exact_match(static_name)
