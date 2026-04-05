# SJC Gold Predictor - Project Report

## 1. Tong quan de tai

### 1.1 Bai toan
Thi truong vang bien dong nhanh, nguoi dung can:
- Theo doi gia vang noi dia va the gioi tren cung mot giao dien.
- Co du bao ngan han de ho tro quyet dinh.
- Co cong cu quan ly model, du lieu va van hanh he thong.

### 1.2 Muc tieu
Xay dung he thong full-stack gom:
- Dashboard quan sat gia va chi so tong hop.
- Prediction module cho gia va xu huong.
- News va history module.
- Admin module cho model, user, dataset, crawler, export.
- AI assistant phuc vu hoi dap trong domain vang.

## 2. Kien truc va pham vi

### 2.1 Pham vi chuc nang
- Dang ky/dang nhap/JWT refresh.
- Du bao gia theo so ngay va du bao trend.
- Xem chart lich su va tong quan thi truong.
- Xem tin tuc theo category.
- Luu va export lich su du bao CSV.
- Quan tri model, user, dataset, crawler run.

### 2.2 Kien truc he thong
- Frontend (React + TypeScript + Vite) goi REST API.
- Backend (FastAPI) xu ly business logic, auth, prediction, export.
- DB layer (SQLAlchemy + Alembic) quan ly du lieu nghiep vu.
- Data source layer: dataset CSV noi bo + yfinance cho world gold/FX.
- Optional AI layer: Gemini de tom tat cau tra loi, co fallback local.

## 3. Thanh phan da trien khai

### 3.1 Backend
- API theo module:
  - Auth: register/login/refresh/logout/me.
  - Prediction: `/predict`, `/predict/trend`.
  - Assistant: `/assistant/queries`.
  - News: category/article listing + article detail.
  - Market: `/overview`, `/price-chart`.
  - Source: `/sources/gold`.
  - User history + export CSV.
  - Admin APIs cho model/dataset/crawler/user/prediction export.
- Startup seed tu dong cho DB moi.
- Exception handling va auth guard trung tam.

### 3.2 Frontend
- SPA gom Dashboard, Predict, History, News, Admin, Auth.
- Global assistant hien tren tat ca route.
- Session luu localStorage, auto refresh token khi gap 401.
- Predict page co chart interactive, timeline view, details view.

### 3.3 Du lieu va model
- Seed model cho `price` va `trend` (builtin + artifact metadata).
- Seed news category/article.
- Seed source va dataset metadata.

## 4. Luong nghiep vu chinh

### 4.1 Luong du bao
1. User chon source, range, model, so ngay.
2. Backend load lich su gia theo source.
3. Forecast engine tao chuoi du bao.
4. Classifier tinh trend score.
5. Tra ket qua + metadata model cho frontend.
6. Luu prediction record de truy vet/export.

### 4.2 Luong assistant
1. Frontend gui cau hoi den backend.
2. Service kiem tra domain relevance.
3. Neu khong lien quan: tu choi trong pham vi he thong.
4. Neu lien quan: tra loi theo du lieu du bao + summary (Gemini neu available).

### 4.3 Luong admin crawler
1. Admin submit task + tham so.
2. Backend enqueue va trigger subprocess theo GOLD_CLI_MODULE.
3. Lich su run truy van qua API admin crawler.

## 5. Nang cap ky thuat trong dot cap nhat gan nhat

### 5.1 Docker va deploy
- Backend Dockerfile toi uu:
  - BuildKit pip cache.
  - Chay non-root user.
  - Doi `chown -R` sang `COPY --chown`.
  - Entrypoint rieng (`alembic upgrade head` + uvicorn).
- Compose profile backend duoc harden:
  - `init: true`
  - `security_opt: no-new-privileges:true`
  - `cap_drop: ALL`
  - `tmpfs: /tmp`
  - Gioi han log file size.

### 5.2 Runtime reliability
- Khac phuc crash-loop migration tren Postgres do boolean default.
- Chuan hoa `server_default` boolean thanh `true`/`false` trong:
  - SQLAlchemy models
  - Alembic initial migration

### 5.3 Dependency optimization
- Bo cac package nang khong can cho runtime du bao hien tai:
  - tensorflow
  - pandas_datareader
  - scikit-learn
  - joblib
  - python-multipart
- Forecast linear duoc thay bang numpy polyfit de giam footprint.

## 6. Ket qua xac thuc
- `docker compose config` pass.
- `docker compose build backend` pass.
- `docker compose up -d db backend frontend` pass.
- Backend va DB dat trang thai healthy.
- Kiem tra endpoint host:
  - `http://127.0.0.1:8000` -> 200
  - `http://127.0.0.1:3000` -> 200

## 7. Han che hien tai
- Backend image van lon do stack khoa hoc du lieu (pandas/numpy/matplotlib).
- Chua tach crawler worker/image rieng.
- Chua co bo integration test/E2E day du.
- Chua co MLOps pipeline day du (versioning, drift, retraining).

## 8. Huong phat trien tiep
- Tach backend API image va crawler worker image.
- Tach requirements theo vai tro (api/crawler).
- Them buildx remote cache cho CI/CD.
- Bo sung observability (metrics, tracing, structured log).
- Hoan thien E2E test cho auth/predict/export/admin.

## 9. Ket luan
Du an da dat muc MVP mo rong va da tien mot buoc gan hon toi production-ready: deploy Docker on dinh hon, startup migration an toan tren Postgres, va runtime backend da duoc harden co he thong. Nen tang hien tai phu hop de tiep tuc mo rong theo huong worker separation, testing day du, va MLOps.
