# Customer Portal API

[中文](README.md)

A standalone consumer-facing / admin backend service that reuses this repository's existing platform registration kernel, platform metadata, task runtime, account assets, proxies, and system capabilities.

## Implemented Capabilities

- Auth endpoints: login, refresh token, logout, current user
- Consumer-facing endpoints:
  - `GET /api/app/platforms`
  - `GET /api/app/config/options`
  - `GET /api/app/products`
  - `POST /api/app/tasks/register`
  - `GET /api/app/tasks`
  - `GET /api/app/tasks/{task_id}`
  - `GET /api/app/tasks/{task_id}/events`
  - `GET /api/app/tasks/{task_id}/logs/stream`
  - `GET /api/app/orders`
  - `POST /api/app/orders`
  - `GET /api/app/orders/{order_no}`
  - `POST /api/app/payments/{order_no}/submit`
  - `GET /api/app/subscriptions`
  - `GET /api/app/profile`
  - `PATCH /api/app/profile`
- Admin endpoints:
  - Users, roles, permissions, platform authorization, product catalog
  - Platforms, config, registration tasks, task queries, task logs
  - Accounts, platform actions, proxies, Solver status
- Payment endpoints:
  - `POST /api/payment/callback/{channel_code}`

## Directory

```text
customer_portal_api/
├── app/
│   ├── routers/
│   ├── services/
│   ├── bootstrap.py
│   ├── config.py
│   ├── db.py
│   ├── deps.py
│   ├── models.py
│   └── security.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── main.py
```

## Local Setup

### 1. Install dependencies

Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you only want to install from the new project's own path, you can also run:

```bash
pip install -r customer_portal_api/requirements.txt
```

### 2. Configure environment variables

Copy the environment variable template:

```bash
cp customer_portal_api/.env.example customer_portal_api/.env
```

Commonly used variables:

- `PORTAL_JWT_SECRET`
- `PORTAL_ADMIN_USERNAME`
- `PORTAL_ADMIN_PASSWORD`
- `PORTAL_ADMIN_EMAIL`
- `PORTAL_START_SOLVER`
- `ACCOUNT_MANAGER_DATABASE_URL`

### 3. Start the service

Run from the repository root:

```bash
source .venv/bin/activate
export $(grep -v '^#' customer_portal_api/.env | xargs)
python -m uvicorn customer_portal_api.main:app --host 0.0.0.0 --port 8100 --reload
```

API docs:

- Swagger UI: `http://127.0.0.1:8100/docs`
- OpenAPI JSON: `http://127.0.0.1:8100/openapi.json`

Default admin account:

- Username: `admin`
- Password: `admin123456`

On first startup, the admin account is automatically written to the database.

## Docker Deployment

Run from the repository root:

```bash
docker compose -f customer_portal_api/docker-compose.yml up --build
```

By default, the service listens on:

- `http://127.0.0.1:8100`

## Design Notes

- The new project reuses this repository's existing platform registration and task execution kernel, without reimplementing platform plugin logic
- The new project's own tables for users, refresh tokens, platform authorization, orders, subscriptions, and task ownership share the same SQLite database as the existing business tables
- The consumer-facing registration endpoint creates real registration tasks, and the task-ownership table restricts each user to seeing only their own tasks
- The payment flow already covers product seeding, placing orders, submitting payment, payment callbacks, subscription activation, and platform registration entitlement activation
