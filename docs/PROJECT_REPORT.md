# SJC Gold Predictor - Project Report

## 1. Tong quan de tai

### 1.1 Bai toan
Thi truong vang co bien dong nhanh, nguoi dung can:
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

## 2. Pham vi va kien truc

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
- API endpoints duoc to chuc theo module:
  - Auth: register/login/refresh/logout/me.
  - Prediction: `/predict`, `/predict/trend`.
  - Assistant: `/assistant/queries`.
  - News: category/article listing + article detail.
  - Market: `/overview`, `/price-chart`.
  - Source: `/sources/gold`.
  - User history + export CSV.
  - Admin APIs cho model/dataset/crawler/user/prediction export.
- Co startup seed tu dong de he thong chay duoc tren DB moi.
- Co central exception handling va auth dependency guards.

### 3.2 Frontend
- SPA gom cac trang: Dashboard, Predict, History, News, Admin, Auth.
- Global floating assistant hien tren tat ca route.
- Session duoc luu localStorage, auto refresh token khi gap 401.
- Predict page co chart interactive, timeline view, chi tiet model context.
- Dashboard hien thi tong quan, chart, model cards, news feed.

### 3.3 Du lieu va model
- Seed model phong phu cho `price` va `trend` (builtin + artifact metadata).
- Seed tin tuc bang tieng Anh va category ro rang.
- Source metadata va dataset source metadata duoc khoi tao tu dau.

## 4. Luong nghiep vu chinh

### 4.1 Luong du bao
1. User chon source, range, model, so ngay.
2. Backend load lich su gia theo source.
3. Forecast engine sinh chuoi du bao.
4. Classifier suy ra trend score.
5. Ket qua + metadata model tra ve frontend.
6. Ban ghi prediction duoc luu de truy vet/export.

### 4.2 Luong assistant
1. Frontend gui cau hoi text den backend.
2. Service kiem tra cau hoi co lien quan domain vang hay khong.
3. Neu khong lien quan: tu choi trong pham vi he thong.
4. Neu lien quan: sinh cau tra loi theo du lieu du bao + summary (Gemini neu available).

### 4.3 Luong admin crawler
1. Admin submit task + tham so crawler.
2. Backend enqueue run metadata.
3. Lich su run duoc truy van qua API admin crawler.

## 5. Ket qua dat duoc
- Hoan thanh bo khung full-stack va endpoint nghiep vu quan trong.
- Frontend da co route guard theo role va trang thai dang nhap.
- Co kha nang export lich su du bao ra CSV cho user va admin.
- Dashboard/Predict co chart va thao tac tuong tac phuc vu phan tich nhanh.
- Co seed data de moi moi truong moi khoi dong khong bi "trang".

## 6. Kiem thu va xac thuc
- Co unit test cho prediction export service (`unittest`).
- Frontend co script build production (`tsc -b && vite build`) de validate typing/build.
- Docker compose cho phep smoke test full stack nhanh.

## 7. Han che hien tai
- Chua co bo integration test/day du E2E test.
- Crawler chua tach ra queue worker rieng (dang theo huong trigger metadata).
- Khia canh MLOps (model versioning, drift monitor, retraining pipeline) chua hoan chinh.
- API key/secret can quan ly chat hon cho moi truong production.

## 8. Huong phat trien tiep
- Them CI pipeline chay lint/test/build tu dong.
- Bo sung observability (log structure, metrics, tracing).
- Nang cap assistant theo RAG + context tu lich su thi truong.
- Them phan tich strategy va canh bao bien dong gia theo nguong.
- Hoan thien E2E test cho auth, predict, export, admin workflows.

## 9. Ket luan
Du an da dat duoc muc tieu xay dung mot he thong du bao gia vang co kha nang van hanh thuc te o muc MVP mo rong: co du bao, quan tri, truy vet lich su, va tro ly AI domain-specific. Kien truc hien tai du de tiep tuc nang cap theo huong production-ready voi testing, monitoring, va MLOps day du hon.
