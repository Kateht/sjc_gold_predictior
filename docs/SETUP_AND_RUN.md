# SJC Gold Predictor - Setup and Run Guide

Tai lieu nay tap trung vao setup moi truong va van hanh he thong theo cau hinh moi nhat.

## 1. Yeu cau he thong

### 1.1 Chay local (khong docker)
- Python 3.11+
- Node.js 20+
- npm 10+
- (Optional) PostgreSQL 16 neu khong muon dung SQLite fallback

### 1.2 Chay bang Docker
- Docker Desktop
- Docker Compose v2

## 2. Clone source

```bash
git clone <your-repo-url>
cd sjc_gold_predictior
```

## 3. Cau hinh moi truong

Backend doc env tu `backend/.env`.

Khuyen nghi:
- Khong commit API key that su len source control.
- Doi `JWT_SECRET_KEY` va `DEFAULT_ADMIN_PASSWORD` khi deploy.

Trong docker compose hien tai:
- Backend duoc override `DATABASE_URL` sang Postgres explicit.
- DB service dung bo bien `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` tai compose.

## 4. Cach 1 - Chay bang Docker Compose (khuyen nghi)

Tu root project:

```bash
docker compose up -d --build db backend frontend
```

He thong se khoi dong:
- db: port 5432
- backend: port 8000
- frontend: port 3000

Kiem tra nhanh:

```bash
docker compose ps
```

Mong doi:
- db: healthy
- backend: healthy
- frontend: up

Kiem tra HTTP:
- Backend: http://127.0.0.1:8000/
- Frontend: http://127.0.0.1:3000/

Dung he thong:

```bash
docker compose down
```

Reset hoan toan (xoa volume DB):

```bash
docker compose down -v
```

## 5. Cach 2 - Chay local thu cong

### 5.1 Chay backend

```bash
cd backend
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Cai package:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Chay migration:

```bash
alembic upgrade head
```

Chay backend:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5.2 Chay frontend

Mo terminal moi:

```bash
cd frontend
npm install
```

Neu can override API base tao `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

Chay dev server:

```bash
npm run dev -- --host 0.0.0.0 --port 3000
```

## 6. Seed data va account mac dinh
Backend se seed o startup:
- Tao bang neu chua co.
- Seed admin user (neu `AUTO_SEED_ADMIN=true`).
- Seed model/news/source/dataset metadata.

Default account (neu giu nguyen env):
- Email: admin@local
- Password: Admin@12345

## 7. Chay test

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py"
```

## 8. Troubleshooting nhanh

### 8.1 Backend restart loop tren Docker do migration
Dau hieu:
- Backend restart lien tuc.
- Log Alembic bao loi boolean default (`is_active BOOLEAN DEFAULT 1`).

Cach xu ly:

```bash
docker compose build backend
docker compose down -v
docker compose up -d db backend frontend
```

### 8.2 Frontend goi sai API
- Kiem tra `VITE_API_BASE_URL`.
- Dam bao backend nghe o port 8000.

### 8.3 CORS error
- Kiem tra `CORS_ORIGINS` trong `backend/.env` co localhost:3000.

### 8.4 Docker pull/build timeout (TLS handshake)
- Retry lai command build.
- Kiem tra mang, proxy, firewall Docker Desktop.

## 9. Lenh hay dung

```bash
# Xem logs compose
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f db

# Build backend image
docker compose build backend

# Recreate backend service
docker compose up -d --force-recreate backend

# Build frontend production
cd frontend && npm run build
```

## 10. Luu y deploy production
- Backend docker da bat mot so hardening:
	- init process
	- no-new-privileges
	- cap_drop all
	- tmpfs /tmp
	- log rotation
- Van nen bo sung:
	- Secret manager cho API keys/passwords
	- Reverse proxy TLS (Nginx/Traefik)
	- Monitoring + alerting
