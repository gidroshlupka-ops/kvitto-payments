# Kvitto Payments

API оплат курса. Суммы везде в копейках, целым числом: 19 900 ₽ — это `1990000`.

При старте создаются тарифы `basic` (990000), `standard` (1990000) и `premium` (2990000). Промокод `KVITTO10` даёт скидку 10%, регистр не важен.

## Запуск

Нужен Python 3.11+.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

macOS и Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Приложение откроется на http://127.0.0.1:8000. Корень `/` не используется. Список тарифов: http://127.0.0.1:8000/tariffs. Интерактивная документация: http://127.0.0.1:8000/docs.

Команда запуска указывает модуль `app.main`: файл приложения лежит в `app/main.py`.

## Тесты

```bash
pytest
```

Успешный прогон заканчивается строкой `62 passed`.

## Примеры запросов

Создание платежа. Заголовок `Idempotency-Key` нужен, чтобы повтор того же запроса вернул этот платёж, а не создал второй. `tariff_id` возьмите из `GET /tariffs`.

```bash
curl -X POST http://127.0.0.1:8000/payments -H "Content-Type: application/json" -H "Idempotency-Key: order-1" -d "{\"tariff_id\":2,\"email\":\"student@school.ru\",\"method\":\"card\"}"
```

Вебхук банка. Для нового платежа статус `pending`, поэтому переход в `succeeded` разрешён.

```bash
curl -X POST http://127.0.0.1:8000/webhooks/bank -H "Content-Type: application/json" -d "{\"payment_id\":1,\"status\":\"succeeded\"}"
```

В PowerShell вызывайте `curl.exe`, не `curl`: в PowerShell `curl` — это другой командлет.
