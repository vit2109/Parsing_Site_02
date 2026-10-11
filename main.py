"""
Точка входа: python main.py [команда].

Команды обрабатывает parsing_site.runner: веб-интерфейс, Chrome с CDP,
проверка подключения, снимок HTML из data_test, однократный inspect и цикл опроса.
"""

from parsing_site.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
