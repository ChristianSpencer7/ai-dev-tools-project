# WhatsApp Chore Bot

A small Django app that tracks household chores, rotates who's turn it is, reminds the current assignee over WhatsApp, and escalates to the group chat if a chore is missed.

See [docs/plan.md](docs/plan.md) for the full architecture plan (tech stack, data model, deployment steps) and [backlog.md](backlog.md) for the current task breakdown.

## Tech stack
- Python 3.12 + Django 5.2 LTS
- SQLite (Django ORM)
- Twilio WhatsApp API
- Deployed to a VPS behind Nginx, run under gunicorn/systemd

## Project layout
```
chorebot/       # Django project (settings, urls, wsgi)
chores/         # app: models, admin, views, chat commands, WhatsApp helpers
docs/plan.md    # architecture plan
backlog.md      # task backlog
```

## Local setup
```bash
python -m venv .venv
.venv/Scripts/activate      # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser   # for /admin/ access
python manage.py runserver
```

## Environment variables
Copy `.env.example` to `.env` (once added) and fill in:
- `DJANGO_SECRET_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_NUMBER`

Never commit real credentials — `.env` and `db.sqlite3` are already gitignored.
