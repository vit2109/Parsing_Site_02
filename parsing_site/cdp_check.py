"""Проверка, что Chrome слушает CDP (обычно http://127.0.0.1:9222)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def cdp_endpoint_ok(cdp_url: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Проверяет, что по адресу CDP отвечает Chrome DevTools Protocol."""
    base = cdp_url.rstrip("/")
    url = f"{base}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError as exc:
        return False, f"CDP не отвечает на {url}: {exc.reason}"
    except TimeoutError:
        return False, f"Таймаут при обращении к {url}"
    except json.JSONDecodeError:
        return False, f"Некорректный ответ CDP на {url}"
    browser = payload.get("Browser", "?")
    return True, browser


def format_cdp_help(cdp_url: str, reason: str = "") -> str:
    """Формирует понятную инструкцию по исправлению ошибки подключения к CDP."""
    lines = [
        f"Не удалось подключиться к браузеру по {cdp_url}.",
    ]
    if reason:
        lines.append(f"Причина: {reason}")
    lines.extend(
        [
            "",
            "Частая ошибка: Chrome запущен так:",
            "  chrome.exe --remote-debugging-port=9222",
            "без --user-data-dir, пока уже открыт обычный Chrome.",
            "В этом случае порт отладки НЕ включается.",
            "",
            "Правильный запуск (сценарии PowerShell могут быть отключены):",
            "  1) Закройте все окна Chrome (Диспетчер задач → chrome.exe).",
            "  2) start_chrome.bat",
            "     или: python main.py chrome",
            "     или вручную:",
            '     chrome.exe --remote-debugging-port=9222 --user-data-dir=".chrome-profile"',
            "",
            "Проверка: в браузере откройте http://127.0.0.1:9222/json/version",
            "Должен появиться JSON с полем Browser.",
        ]
    )
    return "\n".join(lines)
