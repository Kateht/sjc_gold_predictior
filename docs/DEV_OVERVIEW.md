# SJC Gold Predictor - Developer Overview

## 1. Muc tieu ky thuat
SJC Gold Predictor la he thong full-stack de:
- Theo doi gia vang SJC va gia vang the gioi.
- Du bao gia (price) va xu huong (trend) theo so ngay.
- Quan ly model, nguon du lieu, crawler run, va user role.
- Cung cap tro ly AI hoi dap trong pham vi nghiep vu vang.

## 2. Cong nghe chinh
- Backend: FastAPI, SQLAlchemy, Alembic, Pydantic Settings, JWT.
- AI/ML: TensorFlow, scikit-learn, yfinance, Google Gemini (optional).
- Frontend: React 18, TypeScript, Vite, React Router.
- Database: SQLite (local default) hoac PostgreSQL (docker/production style).
- Orchestration: Docker Compose.

## 3. Cau truc monorepo

```text
sjc_gold_predictior/
  docker-compose.yml
  backend/
    Dockerfile
    requirements.txt
    alembic.ini
    app/
      main.py
      api/
      core/
      db/
      services/
      ai/
      crawler/
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
- API layer (`app/api`): Dinh nghia endpoint va schema input/output.
- Service layer (`app/services`): Chua business logic (prediction, news, crawler, auth, export).
- Data layer (`app/db`): SQLAlchemy model, session, seed logic.
- Core layer (`app/core`): Config, security, dependencies, exception handlers.
- AI layer (`app/ai`): Forecast engine, preprocess utility.

### 4.1 App bootstrap
- Entry point: `app/main.py`.
- Startup hook goi `run_seed()` de:
  - `Base.metadata.create_all()`.
  - Seed admin, model, news category/article, source, dataset source.
- Tat ca router mount duoi `API_V1_PREFIX` (mac dinh `/api/v1`).

### 4.2 Auth va phan quyen
- JWT access + refresh token.
- Endpoint auth: register, login, refresh, logout, me.
- Guard:
  - `get_current_user`: bat buoc dang nhap.
  - `require_admin`: yeu cau role admin.

### 4.3 Prediction flow
1. Nhan request tu `/predict` hoac `/predict/trend`.
2. Load du lieu lich su theo source (`sjc`/`world`).
3. Resolve model theo id/code/default va prediction kind.
4. Chay engine de tao du bao + trend score.
5. Luu `PredictionRecord` vao DB (co co `used_fallback`).
6. Tra response typed schema cho frontend.

### 4.4 News va Overview
- News API cung cap category list, article list, article by slug.
- Overview API tong hop:
  - Gia SJC noi dia (dataset).
  - Gia vang the gioi (yfinance).
  - Ty gia USD/VND (yfinance fallback).
  - Arbitrage gap noi dia vs quy doi the gioi.

### 4.5 Admin operations
- Model registry: create/update/activate/deactivate/default.
- Dataset registry: CRUD-like + export CSV theo dataset.
- Crawler run: trigger task, xem danh sach run, xem chi tiet run.
- User management: doi role, toggle active.
- Prediction export: export CSV toan bo history (co bo loc).

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
- Assistant backend co topic guard, tra loi theo domain vang, model, history, admin.

## 6. Data va model seeding
`app/db/init_db.py` seed cac nhom du lieu:
- Default admin account (neu `AUTO_SEED_ADMIN=true`).
- Nhieu model `price` va `trend` (builtin + artifact metadata).
- News category/article bang tieng Anh.
- Gold source links va dataset source links.

Seed duoc viet theo huong "refresh/upsert-ish" cho model/news: DB cu van duoc cap nhat metadata moi khi app startup.

## 7. API groups (tom tat)
- Auth: `/auth/*`
- Prediction + Assistant: `/predict`, `/predict/trend`, `/assistant/queries`
- Market: `/price-chart`, `/overview`
- News: `/news/categories`, `/news/articles`, `/news/articles/{slug}`
- Sources: `/sources/gold`
- History user: `/history/predictions`, `/history/predictions/export`
- Admin: `/admin/*`, `/admin/crawler/*`, `/admin/predictions/export`

## 8. Convention va luu y dev
- Config doc tu `backend/.env` qua `pydantic-settings`.
- `DATABASE_URL` uu tien neu co; neu rong thi backend tu build Postgres URL tu `POSTGRES_*`.
- Docker compose dang override `DATABASE_URL: ""` de force Postgres service.
- Frontend API base URL doc tu `VITE_API_BASE_URL`.
- Session frontend luu localStorage key `sjc_gold_session`.

## 9. Kiem thu hien co
- Co bo unit test cho prediction CSV export service:
  - `backend/tests/test_prediction_export_service.py`
- Test hien tai dung `unittest` (khong can pytest plugin).

## 10. Huong mo rong de xuat
- Them monitoring (Prometheus/Grafana) cho API latency va crawler health.
- Them task queue (Celery/RQ) cho crawler run async real.
- Bo sung integration test cho auth + predict + admin workflows.
- Tach model registry metadata va artifact storage theo S3/MinIO.
