# StudentLife AI: Sprint 1 + "Révision et formations" (Sprint 3)

Django REST API (`backend/`) + Next.js / React / Tailwind CSS frontend (`frontend/`).
The UI is in French, responsive (sidebar on PC, drawer menu on tablet and phone), blue / green / white.

## 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r ../requirements.txt
python manage.py migrate      # migrations are included
python manage.py runserver    # http://localhost:8000  (admin: /admin)
```

## 2. Frontend

```bash
cd frontend
npm install
npm run dev                        # http://localhost:3000
```

Register a **student** account and a **teacher** account (two browsers or one private window) to test both sides.

Teachers can create and edit saved quizzes, manually or with AI, and attach them to their own formations. Students can take published formation quizzes and generate private AI practice quizzes from course text; practice quizzes are corrected in the browser and are not saved. Only teachers can create, edit, or delete saved quizzes.

AI quiz generation can also extract text from course PDFs and from formation lesson content and PDF, DOCX, TXT, or MD lesson files. Up to 40,000 characters of combined source text are sent to the AI. Scanned/image-only PDFs cannot be read unless they contain selectable text.


```

The configured model must support Gemini's `generateContent` endpoint. The former
`gemini-2.5-flash` model is no longer available to new users; `gemini-3.8-flash`
is the current default. `GEMINI_TIMEOUT` is the request timeout in seconds (default
120); a read timeout is retried once automatically.

## 4. Layout

```
backend/   config/ (settings, urls)  common/ (ai, text extraction, permissions)
           accounts/  profiles/  learning/
frontend/  src/app/ (pages)  src/components/  src/lib/ (api client, auth)
```
