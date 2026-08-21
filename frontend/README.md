# TİLKO — Next.js arayüz

Karanlık, cam efektli (glassmorphism) frontend. Backend FastAPI (`http://127.0.0.1:8000`) ayakta olmalı.

## 1) Node.js

Makinede Node yoksa önce LTS kur:

```powershell
winget install -e --id OpenJS.NodeJS.LTS
```

Yeni bir terminal aç (PATH güncellensin), sonra:

```powershell
node -v
npm -v
```

## 2) Kütüphaneler

Proje kökünden:

```powershell
cd frontend
npm install
```

Resmi shadcn kurulumu (isteğe bağlı; Button / Input / Card / Accordion zaten `src/components/ui` içinde):

```powershell
npx shadcn@latest init
npx shadcn@latest add button input card accordion badge
```

## 3) Çalıştır

Backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm run dev
```

Tarayıcı: [http://localhost:3000](http://localhost:3000)

API adresi `frontend/.env.local` içinde `NEXT_PUBLIC_API_BASE`.
