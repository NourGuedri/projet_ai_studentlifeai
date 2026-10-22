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

## 3b. Tableau de bord, notifications et administration

New API (all under `/api/`, JWT required):

| Route | Who | What |
|---|---|---|
| `notifications/`, `notifications/unread-count/`, `notifications/<id>/read/`, `notifications/read-all/` | everyone | own notifications (bell + `/notifications` page) |
| `reports/` (POST) | everyone | report a published formation or one of its quizzes |
| `admin/stats/` | admin | usage statistics for the admin dashboard |
| `admin/users/` (list, create, PATCH role/active, DELETE) | admin | user and role management |
| `admin/formations/` (+ `<id>/unpublish/`, DELETE) | admin | moderation of formations |
| `admin/reports/` (+ `<id>/resolve/`) | admin | handle reports (dismiss, unpublish, delete) |
| `admin/announcements/` (POST) | admin | notify everybody or one role |

Create the first administrator with `python manage.py createsuperuser` (it gets the `admin` role), then manage everybody else from **Administration** in the sidebar.
Run `python manage.py migrate` after pulling (two new apps: `notifications`, `administration`).

**For the other modules:** to notify a user from your own code:

```python
from notifications.services import notify
notify(user, "Planning mis à jour", "Votre cours de jeudi est annulé.", link="/planning", kind="warning")  # kind: info | success | warning | announcement
```

Run the tests with `python manage.py test`.

## 4. Layout

```
backend/   config/ (settings, urls)  common/ (ai, text extraction, permissions)
           accounts/  profiles/  learning/
frontend/  src/app/ (pages)  src/components/  src/lib/ (api client, auth)
```
