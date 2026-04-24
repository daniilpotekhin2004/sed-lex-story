# LexQuest Frontend

React + TypeScript + Vite SPA для работы с пайплайном генерации (Stable Diffusion через Celery).

## Требования
- Node 18+
- Для Android-сборки: JDK 21, Android SDK и Capacitor Android-проект в `frontend/android`
- Для Capacitor CLI нужен Node 22+, локально проверен Node 24.5.0

## Установка и запуск
```bash
cd frontend
npm install
# настройте .env по .env.example
npm run dev -- --host --port 5174
```

## Android build
Из корня репозитория:

```bat
build_android.bat
```

Подробная локальная конфигурация описана в `../FRONTEND_SETUP.md`.

## Конфигурация
- `VITE_API_BASE_URL` — базовый URL API (по умолчанию `http://localhost:8000/api`).

Создайте `.env` на основе `.env.example`.

## Архитектура
- `src/api` — HTTP-клиент (axios) и функции для эндпоинтов генерации.
- `src/shared` — общие типы.
- `src/hooks` — React Query мутейшн/квери + Zustand для истории задач.
- `src/components` — layout и UI блока генерации.
- `src/pages` — страницы: генерация, задачи, настройки.

## Основные сценарии
- Страница “Генерация”: форма prompt + параметры (варианты, размер, cfg/steps, пресеты), статус активной задачи, результаты и история задач.
- Страница “История”: загрузка серверного списка задач с пагинацией.
- Страница “Настройки”: отображение текущего API base и переключение темы.
- Логин по JWT (`/auth/login`) + загрузка профиля (`/auth/me`), защита приватных маршрутов.
- Тема (light/dark) и последние параметры генерации сохраняются в `localStorage`.

## API ожидаемый контракт
- `POST /generation/generate` — `{prompt, style?, num_variants?, width?, height?}` → `{task_id}`.
- `GET /generation/tasks/{task_id}` — статус Celery-задачи с `state/ready/success/result.paths|image_url`.
- `POST /generation/pipeline-check` — диагностическая проверка (используется редко).
- `GET /tasks` — серверная история задач с пагинацией.
- `POST /auth/login` → `{ access_token }`, `GET /auth/me` → пользователь.

Ошибки сети/HTTP выводятся пользователю; статус задачи обновляется polling-ом до готовности.
