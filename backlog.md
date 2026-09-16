# Backlog — WhatsApp Chore Bot (Django build)

Derived from [docs/plan.md](docs/plan.md). Ordered roughly the way each task should be tackled — earlier tasks unblock later ones and can be tested without Twilio involved.

## Phase 0 — Project setup
- [x] Install Django, create the `chorebot` project and `chores` app, register `chores` in `INSTALLED_APPS` (plan §2, §8)

## Phase 1 — Data model & rotation logic
- [x] Define `Person` model (`name`, `phone`) in `chores/models.py` (plan §4)
- [x] Define `Chore` model (`name`, `frequency_days`, `rotation_order` JSONField, `rotation_index`, `due_date`, `grace_hours`, `status` choices) (plan §4)
- [x] Define `CompletionToken` model (`token` PK, FK to `Chore`, `created_at`, `used`) (plan §4)
- [x] Run `makemigrations` / `migrate`
- [x] Implement rotation logic in `chores/rotation.py`: advance `rotation_index`, recompute `due_date`, reset `status` to `pending` on completion (plan §5)
- [x] Sanity-check models + rotation logic in the Django shell (no Twilio needed yet)

## Phase 2 — Admin panel
- [ ] Register `Person`, `Chore`, `CompletionToken` in `chores/admin.py`
- [ ] Run `createsuperuser`, confirm `/admin/` shows all three models with working CRUD

## Phase 3 — WhatsApp webhook skeleton
- [ ] Add `POST /whatsapp/incoming` view + URL route
- [ ] Wire up Twilio sandbox (plan §6) and confirm the webhook receives a message and can echo a reply
- [ ] Add `chores/whatsapp.py` with Twilio send/receive helpers (wrap `twilio.rest.Client`)

## Phase 4 — Chat commands
- [ ] Add `chores/commands.py`: simple `|`-delimited parser (plan §5)
- [ ] Implement `add <chore> | every <N> days | <person1,person2,...>`
- [ ] Implement `list` — current assignee, due date, status per chore
- [ ] Implement `remove <chore>`
- [ ] Implement `help`
- [ ] Wire parsed commands into the webhook view from Phase 3

## Phase 5 — Completion link flow
- [ ] Add `GET /done/<token>` view + URL route
- [ ] Look up token → validate unused → mark chore done → advance rotation (via Phase 1 logic) → mark token used
- [ ] Add `templates/done.html` confirmation page
- [ ] Optionally post a confirmation message back to the group chat

## Phase 6 — Scheduler: reminders
- [ ] Decide scheduling approach: `django-crontab` vs. a plain management command + direct system crontab entry (see plan §2b — `django-crontab` is unmaintained with no confirmed Django 5/6 support; leaning toward the plain management command)
- [ ] Implement reminder pass in `chores/cron.py`: for `due_date <= today` and `status == 'pending'` → generate `CompletionToken`, send WhatsApp reminder with link, set `status = 'reminded'` (plan §5)

## Phase 7 — Scheduler: escalation
- [ ] Implement escalation pass: for `status == 'reminded'` and `now > due_date + grace_hours` → post to group chat naming the overdue person/chore, set `status = 'escalated'` (plan §5)
- [ ] Resolve open decision: re-escalate daily until resolved, or just once? (plan §9)

## Phase 8 — Deployment
- [ ] Write `.env.example` (Twilio SID/token, `DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`)
- [ ] Provision VPS (Ubuntu 24.04 or 26.04 LTS — plan §2b), install Python/nginx/certbot
- [ ] `migrate` + `createsuperuser` on the server
- [ ] Install the reminder/escalation job onto the system crontab
- [ ] Run the app under `gunicorn`, managed by a `systemd` unit (plan §7)
- [ ] Configure Nginx reverse proxy + TLS via certbot
- [ ] Point the Twilio webhook at the production domain, dogfood with the household

## Open decisions to resolve along the way (plan §9)
- Grace period before escalation (default suggestion: 24h)
- Escalation re-fire cadence (once vs. daily until resolved)
- Whether to notify the *next* person in rotation ahead of time ("you're on deck tomorrow")
- Whether the admin panel is open to all household members or just one person
