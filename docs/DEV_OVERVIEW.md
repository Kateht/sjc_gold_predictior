# SJC Gold Predictor - Developer Overview

## 1. Muc tieu ky thuat
SJC Gold Predictor la he thong full-stack de:
- Theo doi gia vang SJC va gia vang the gioi.
- Du bao gia (price) va xu huong (trend) theo so ngay.
- Quan ly model, nguon du lieu, crawler run, va user role.
- Cung cap tro ly AI hoi dap trong pham vi nghiep vu vang.

## 2. Cong nghe chinh
- Backend: FastAPI, SQLAlchemy, Alembic, Pydantic Settings, JWT.
- AI/ML runtime hien tai: numpy, pandas, yfinance, Google Gemini (optional).
- Frontend: React 18, TypeScript, Vite, React Router.
- Database: SQLite (local fallback) hoac PostgreSQL (docker/production).
- Orchestration: Docker Compose.

Ghi chu cap nhat:
- Forecast strategy "linear" da duoc toi uu bang numpy polyfit, khong con phu thuoc scikit-learn.
- Migration va model da chuan hoa boolean default theo PostgreSQL (`true`/`false`).

## 3. Cau truc monorepo

```text
sjc_gold_predictior/
  docker-compose.yml
  backend/
    Dockerfile
    entrypoint.sh
    requirements.txt
    alembic.ini
    alembic/
      versions/
    app/
      main.py
      api/
      core/
      db/
      services/
      ai/
      crawler/
    dataset/
    tests/
  frontend/
    package.json
    vite.config.ts
    src/
      App.tsx
      context/
      components/
      pages/
      lib/
      styles/
  docs/
```

## 4. Backend architecture
Backend theo huong layer ro rang:
- API layer (`app/api`): endpoint va request/response schema.
- Service layer (`app/services`): business logic (prediction, news, crawler, auth, export).
- Data layer (`app/db`): SQLAlchemy model, session, seed.
- Core layer (`app/core`): config, security, dependency, exception handling.
- AI layer (`app/ai`): forecast engine va utility tien xu ly.

### 4.1 App bootstrap va startup
- Entry point web app: `app/main.py`.
- Docker entrypoint: `backend/entrypoint.sh`.
  - Chay `alembic upgrade head`.
  - Sau do start uvicorn.
- Startup hook app goi `run_seed()` de tao/refresh default data.

### 4.2 Auth va phan quyen
- JWT access + refresh token.
- Endpoint auth: register, login, refresh, logout, me.
- Guard:
  - `get_current_user`: bat buoc dang nhap.
  - `require_admin`: yeu cau role admin.

### 4.3 Prediction flow
1. Nhan request tu `/predict` hoac `/predict/trend`.
2. Load lich su gia theo source (`sjc`/`world`).
3. Resolve model theo id/code/default va prediction kind.
4. Chay engine de tao du bao + trend score.
5. Luu `PredictionRecord` vao DB.
6. Tra typed response schema cho frontend.

### 4.4 Crawler flow
- API admin trigger crawler run metadata.
- Service spawn subprocess theo `GOLD_CLI_MODULE` + config path.
- Ket qua run (stdout/stderr/exit_code/status) duoc luu vao `crawler_runs`.

## 5. Frontend architecture
Frontend la SPA voi route + auth context:
- `App.tsx`: route config va global assistant mount.
- `context/AuthContext.tsx`: bootstrap session, login/register/logout flow.
- `lib/api.ts`: HTTP client + auto refresh token khi 401.
- `components/Shell.tsx`: layout, nav, session summary.
- `pages/*`: Dashboard, Predict, History, News, Admin, Auth.

### 5.1 Route va access control
- Public: Dashboard, Predict, News, Login.
- Auth required: History.
- Admin required: Admin page.

### 5.2 Assistant UI
- `GlobalAssistant` mount global o root app, hien o moi page (ke ca `/login`).
- Chat request den `/assistant/queries`.
- Assistant backend co topic guard, fallback logic va Gemini summary tuy chon.

## 6. Docker deploy profile (hien tai)

### 6.1 Compose behavior
- Service `db`: PostgreSQL 16 alpine, healthcheck bat buoc truoc backend.
- Service `backend`:
  - Build tu `backend/Dockerfile`.
  - Override `DATABASE_URL` sang Postgres trong compose.
  - Override `GOLD_CLI_MODULE` phu hop runtime trong container.
  - Healthcheck bang HTTP probe `/`.

### 6.2 Hardening da ap dung cho backend
- Chay bang user non-root trong image.
- `init: true`.
- `security_opt: no-new-privileges:true`.
- `cap_drop: ALL`.
- `tmpfs: /tmp`.
- Gioi han log size (`max-size`, `max-file`).

### 6.3 Build optimization da ap dung
- BuildKit dockerfile frontend syntax.
- Pip cache mount (`--mount=type=cache,target=/root/.cache/pip`).
- Doi `chown -R` sang `COPY --chown` de giam layer ton kem.
- `.dockerignore` bo sung cac thu muc/file khong can cho build context.

## 7. API groups (tom tat)
- Auth: `/auth/*`
- Prediction + Assistant: `/predict`, `/predict/trend`, `/assistant/queries`
- Market: `/price-chart`, `/overview`
- News: `/news/categories`, `/news/articles`, `/news/articles/{slug}`
- Sources: `/sources/gold`
- History user: `/history/predictions`, `/history/predictions/export`
- Admin: `/admin/*`, `/admin/crawler/*`, `/admin/predictions/export`

## 8. Convention va luu y dev
- Config doc tu `backend/.env` qua pydantic-settings.
- `DATABASE_URL` uu tien neu co; neu rong thi backend build Postgres URL tu `POSTGRES_*`.
- Trong docker compose, backend duoc force dung Postgres URL explicit.
- Frontend API base URL doc tu `VITE_API_BASE_URL`.
- Session frontend luu localStorage key `sjc_gold_session`.

## 9. Kiem thu hien co
- Co unit test cho prediction CSV export service:
  - `backend/tests/test_prediction_export_service.py`
- Test hien tai dung `unittest`.

## 10. Huong mo rong de xuat
- Tach crawler thanh worker image rieng de giam size backend API image.
- Tach requirements theo vai tro (`api` vs `crawler`).
- Them buildx remote cache cho CI/CD.
- Bo sung integration test cho auth + predict + admin workflows.
- Them observability: metrics, tracing, structured logging.
