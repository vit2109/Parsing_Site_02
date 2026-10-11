"""
Тестирование сопоставления телефонов с адресами (ТОЛЬКО ПОЛНОЕ СОВПАДЕНИЕ)
"""

from parsing_site.phone_loader import (
    get_phone_loader, 
    get_phone_for_static,
    get_address_and_phone_for_static
)

def test_phone_matching():
    """Тестируем точное сопоставление"""
    
    loader = get_phone_loader()
    
    print("=" * 70)
    print("🔍 ТЕСТИРОВАНИЕ СОПОСТАВЛЕНИЯ ТЕЛЕФОНОВ (ТОЛЬКО ПОЛНОЕ СОВПАДЕНИЕ)")
    print("=" * 70)
    
    # Получаем все адреса из загруженных данных
    all_addresses = list(loader.get_all_phones().keys())
    
    if not all_addresses:
        print("❌ Нет загруженных адресов!")
        return
    
    print(f"\n📋 Загружено адресов: {len(all_addresses)}")
    print("\nПримеры адресов из БД:")
    for addr in all_addresses[:10]:
        print(f"  - {addr}")
    
    print("\n" + "-" * 70)
    print("🔎 ТЕСТИРОВАНИЕ ПОИСКА")
    print("-" * 70)
    
    # Тестовые адреса (должны точно совпадать с теми, что в Excel)
    test_addresses = [
        "г. Москва_4",
        "г. Москва_5",
        "г. Санкт-Петербург_1",
    ]
    
    # Добавляем реальные адреса из загруженных данных для проверки
    if all_addresses:
        test_addresses.extend(all_addresses[:3])
    
    for addr in test_addresses:
        print(f"\n📌 Поиск для: '{addr}'")
        
        # Точное совпадение
        phone = get_phone_for_static(addr)
        if phone:
            print(f"   ✅ Найден телефон: {phone}")
        else:
            print(f"   ❌ Телефон НЕ НАЙДЕН (нет точного совпадения)")
        
        # Проверяем нормализованный вариант
        normalized = loader._normalize_address(addr)
        print(f"   🔄 Нормализованный: '{normalized}'")
        
        # Проверяем, есть ли в словаре
        all_normalized = loader.get_all_normalized()
        if normalized in all_normalized:
            print(f"   ✅ Есть в нормализованном словаре: {all_normalized[normalized]}")
    
    print("\n" + "-" * 70)
    print("📊 СТАТИСТИКА")
    print("-" * 70)
    stats = loader.get_stats()
    print(f"Всего записей: {stats['total']}")
    print(f"Оригинальных записей: {stats['original_total']}")
    print(f"Файл: {stats['file']}")
    
    print("\n📋 Примеры записей (оригинальные):")
    for addr, phone in stats['sample']:
        print(f"  {addr} -> {phone}")

def test_specific_address(address: str):
    """Тест конкретного адреса"""
    print(f"\n🔍 ПРОВЕРКА АДРЕСА: '{address}'")
    print("-" * 50)
    
    loader = get_phone_loader()
    
    # Проверяем точное совпадение
    phone = get_phone_for_static(address)
    if phone:
        print(f"✅ Точное совпадение: {phone}")
    else:
        print(f"❌ Точное совпадение НЕ НАЙДЕНО")
    
    # Проверяем нормализованный
    normalized = loader._normalize_address(address)
    print(f"🔄 Нормализованный: '{normalized}'")
    
    # Проверяем все возможные варианты
    all_addresses = loader.get_all_phones()
    print(f"\n📋 Поиск похожих адресов в БД:")
    found = False
    for db_addr in all_addresses:
        db_normalized = loader._normalize_address(db_addr)
        if normalized == db_normalized:
            print(f"  ✅ ТОЧНОЕ СОВПАДЕНИЕ: '{db_addr}' -> {all_addresses[db_addr]}")
            found = True
        elif address.lower() in db_addr.lower() or db_addr.lower() in address.lower():
            print(f"  ⚠️ ЧАСТИЧНОЕ СОВПАДЕНИЕ (НЕ ИСПОЛЬЗУЕТСЯ): '{db_addr}' -> {all_addresses[db_addr]}")
            found = True
    
    if not found:
        print("  ❌ Совпадений не найдено")

if __name__ == "__main__":
    test_phone_matching()
    
    # Дополнительный тест конкретного адреса
    print("\n" + "=" * 70)
    test_specific_address("г. Москва_4")