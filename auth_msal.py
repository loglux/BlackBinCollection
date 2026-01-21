#!/usr/bin/env python3
"""
Аутентификация через MSAL (Microsoft Authentication Library).
Поддерживает Device Code Flow для headless серверов.
"""

import json
import time
import os
from dotenv import load_dotenv

try:
    from msal import PublicClientApplication
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False
    print("MSAL библиотека не установлена.")
    print("Установите: pip install msal")
    exit(1)

# Загрузка переменных
load_dotenv()

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
TENANT_ID = os.getenv('TENANT_ID')

# Scopes для Microsoft Graph API
# offline_access добавляется автоматически, не нужно указывать явно
SCOPES = [
    "Calendars.ReadWrite",
    "User.Read"
]

print("\n" + "="*80)
print("АУТЕНТИФИКАЦИЯ ЧЕРЕЗ MSAL (Device Code Flow)")
print("="*80 + "\n")

# Создаем Public Client Application (для Device Code Flow)
authority = f"https://login.microsoftonline.com/{TENANT_ID}"
app = PublicClientApplication(
    CLIENT_ID,
    authority=authority
)

# Инициируем Device Code Flow
flow = app.initiate_device_flow(scopes=SCOPES)

if "user_code" not in flow:
    print("✗ Не удалось инициировать Device Code Flow")
    print(json.dumps(flow, indent=2))
    exit(1)

# Информация для пользователя
print("="*80)
print("ШАГ 1: Перейдите по этому URL:")
print("="*80)
print(f"\n{flow['verification_uri']}")
print()

print("="*80)
print("ШАГ 2: Введите этот код:")
print("="*80)
print(f"\n{flow['user_code']}")
print()

print("="*80)
print("Ожидание аутентификации...")
print("="*80)
print()

# Получаем токен (этот метод блокирует выполнение до завершения аутентификации)
result = app.acquire_token_by_device_flow(flow)

if "access_token" in result:
    print("\n✓ Аутентификация успешна!")

    # Сохранение токена в формате O365
    # ВАЖНО: scope должен быть списком, а не строкой!
    scope = result.get('scope', [])
    if isinstance(scope, str):
        scope = scope.split(' ')

    token_data_o365 = {
        "token_type": "Bearer",
        "scope": scope,
        "expires_in": result.get('expires_in', 3600),
        "ext_expires_in": result.get('ext_expires_in', 3600),
        "access_token": result['access_token'],
        "refresh_token": result.get('refresh_token', ''),
        "expires_at": time.time() + result.get('expires_in', 3600)
    }

    # Сохранение в файл
    with open('o365_token.txt', 'w') as f:
        json.dump(token_data_o365, f, indent=2)

    print("\n✓ Токен сохранен в o365_token.txt")

    # Проверка файла
    file_size = os.path.getsize('o365_token.txt')
    print(f"✓ Размер файла: {file_size} байт")

    print("\n" + "="*80)
    print("ГОТОВО! Теперь можно запустить blackbin.py")
    print("="*80 + "\n")

else:
    print("\n✗ Аутентификация не удалась")
    print("\nОшибка:", result.get("error"))
    print("Описание:", result.get("error_description"))
    exit(1)
