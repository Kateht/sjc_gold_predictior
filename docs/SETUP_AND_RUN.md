# SJC Gold Predictor - Setup and Run Guide

Tai lieu nay tap trung vao cach setup moi truong va chay du an.

## 1. Yeu cau he thong

### 1.1 Neu chay local (khong docker)
- Python 3.11+
- Node.js 20+
- npm 10+
- (Optional) PostgreSQL 16 neu khong muon dung SQLite

### 1.2 Neu chay bang docker
- Docker Desktop
- Docker Compose v2

## 2. Clone va cau truc

```bash
git clone <your-repo-url>
cd sjc_gold_predictior
```

Backend nam o thu muc `backend`, frontend nam o `frontend`.



Quan trong:
- Khong commit API key that su len source control.
- Doi `JWT_SECRET_KEY` va `DEFAULT_ADMIN_PASSWORD` khi deploy.

## 4. Cach 1 - Chay nhanh bang Docker Compose (khuyen nghi)

Tu root project:

```bash
docker compose up --build
```

He thong se khoi dong:
- `db` o port 5432
- `backend` o port 8000
- `frontend` o port 3000

Compose da set `DATABASE_URL: ""` cho backend de backend tu dung `POSTGRES_*`.

Kiem tra nhanh:
- Backend health: `http://localhost:8000/`
- Frontend app: `http://localhost:3000/`

Dung he thong:

```bash
docker compose down
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

Tao file `.env` (neu can override API base):

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

Run dev server:

```bash
npm run dev -- --host 0.0.0.0 --port 3000
```

## 6. Seed data va account mac dinh
App backend goi seed o startup:
- Tao bang neu chua co.
- Seed admin user (neu `AUTO_SEED_ADMIN=true`).
- Seed model/news/source/dataset metadata.

Mac dinh (neu giu nguyen env):
- Email: `admin@local`
- Password: `Admin@12345`

## 7. Chay test
Hien co unit test cho prediction export service:

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py"
```

## 8. Troubleshooting nhanh

### Loi CORS tren frontend
- Kiem tra `CORS_ORIGINS` trong `backend/.env` co `http://localhost:3000`.

### Frontend goi sai API
- Kiem tra `VITE_API_BASE_URL`.
- Dam bao backend dang listen port 8000.

### Models/news khong hien thi tren DB moi
- Dam bao backend startup khong loi, vi seed chay trong startup hook.

### Loi ket noi Postgres trong Docker
- Kiem tra container `db` da healthy.
- Kiem tra bien `POSTGRES_*` trong `backend/.env`.

## 9. Lenh hay dung

```bash
# Build frontend production
cd frontend && npm run build

# Xem logs compose
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f db

# Rebuild tu dau
docker compose down -v
docker compose up --build
```
