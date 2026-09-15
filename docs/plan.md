# WhatsApp Chore Bot — Architecture Plan

## 1. Scope Summary
- **Users**: 2–4 people, one fixed household group
- **Core job**: track chores and make sure they get done
- **Assignment**: rotating turns per chore
- **Interaction**: WhatsApp group chat
- **Completion**: tap a link sent by the bot
- **Missed chores**: escalate to the whole group chat
- **Chore management**: open — anyone can add/edit chores and rotations via chat commands

## 2. Tech Stack
| Layer | Choice |
|---|---|
| Language | Python |
| Web framework | Django |
| Database | SQLite (Django ORM + migrations) |
| WhatsApp integration | Twilio WhatsApp API |
| Scheduler | `django-crontab` (registers jobs as real cron entries; simplest option that avoids a Celery/Redis broker) |
| Hosting | Self-managed VPS (DigitalOcean/Linode droplet) |
| Process manager | `systemd` service (keeps Django app alive under gunicorn, restarts on crash) |
| Reverse proxy / TLS | Nginx + Let's Encrypt (Twilio requires HTTPS webhook URLs) |

**Why Django**: the auto-generated admin panel gives a free web page to view/edit chores, people, and rotation state — handy for checking "who's on the hook this week" from a browser instead of only via chat commands. The ORM + migrations also replace hand-written SQLite schema management.

**Alternative considered**: Flask is lighter-weight for this app's actual surface area (two routes: the inbound webhook and the completion link) and has less scaffolding. If the admin panel ends up unused, Flask + SQLAlchemy + APScheduler is the leaner fallback — worth revisiting if Django's structure starts to feel like overhead.

## 2b. Recommended Versions

| Component | Version | Notes |
|---|---|---|
| Python | 3.12.x | Widest package/compatibility coverage; hold off on 3.13/3.14 until deps confirm support |
| Django | 5.2 LTS | Long-term support release (security fixes into ~2028) — matters for a hobby app you won't touch often |
| django-crontab | 0.7.1 | Latest stable release; unmaintained but small enough that's not a concern here |
| twilio (Python SDK) | ^9.x | Current major version of the official SDK |
| gunicorn | 23.x | |
| Nginx | 1.24+ (Ubuntu 24.04's packaged version) or 1.27 mainline | |
| Ubuntu | 24.04 LTS | target OS for the VPS deployment steps in Section 7 |
| certbot | latest via `snap`/`apt` | self-updates, no need to pin |

SQLite itself doesn't need a separate install/version pin — it ships with Python's `sqlite3` module.

Pin exact versions in `requirements.txt` at build time (`pip freeze` after installing) rather than trusting this table verbatim — check for newer patch/minor releases when you actually start building, since this plan was written 2026-09-15.

## 3. System Components

```
┌─────────────┐      webhook (incoming msg)      ┌──────────────┐
│   Twilio    │ ───────────────────────────────▶ │  Django app  │
│ WhatsApp API│ ◀─────────────────────────────── │  (views)     │
└─────────────┘      outgoing msg (API call)      └──────┬───────┘
                                                          │
                                                   ┌──────▼───────┐
                                                   │   SQLite DB  │
                                                   │ chores, people│
                                                   │ rotation state│
                                                   │ (Django ORM) │
                                                   └──────▲───────┘
                                                          │
                                                   ┌──────┴───────┐
                                                   │django-crontab│
                                                   │ (reminders + │
                                                   │  escalation) │
                                                   └──────────────┘
```

Two entry points into the app:
1. **Inbound webhook** (`POST /whatsapp/incoming`) — Twilio calls this whenever someone sends a message in the group. Used for commands (`add`, `list`, `remove`, `help`).
2. **Completion link** (`GET /done/<token>`) — the bot sends this link in reminders; opening it marks the chore done. No login needed since the token is unique and single-use.

Plus a third, optional surface:
3. **Django admin** (`/admin/`) — auto-generated CRUD UI over the models below, for anyone with a login to inspect or manually fix chores/rotation state.

A `django-crontab` job runs independently of requests (via real system cron calling `manage.py crontab run <id>`), checking due/overdue chores and sending messages proactively via the Twilio REST API (not the webhook).

## 4. Database Schema

Implemented as Django models in `chores/models.py`; fields below map directly to model fields, with migrations generated via `makemigrations`/`migrate`.

**Person**
| field | type | notes |
|---|---|---|
| id | AutoField PK | |
| name | CharField | |
| phone | CharField | WhatsApp number, for @mentions in escalation text |

**Chore**
| field | type | notes |
|---|---|---|
| id | AutoField PK | |
| name | CharField | |
| frequency_days | IntegerField | e.g. 1 = daily, 7 = weekly |
| rotation_order | JSONField | list of Person IDs, in turn order |
| rotation_index | IntegerField | whose turn it currently is |
| due_date | DateField | when it's next due |
| grace_hours | IntegerField | how long after due_date before escalating (default e.g. 24) |
| status | CharField (choices) | `pending` / `reminded` / `escalated` / `done` |

**CompletionToken**
| field | type | notes |
|---|---|---|
| token | CharField PK | random, e.g. via `secrets.token_urlsafe` |
| chore | ForeignKey → Chore | |
| created_at | DateTimeField (auto_now_add) | |
| used | BooleanField | prevents replay |

Register all three in `chores/admin.py` (`admin.site.register(...)`) to get the admin panel views for free.

## 5. Core Logic

### Rotation
On chore creation, `rotation_index = 0`, assignee = `rotation_order[0]`.
On completion:
```
rotation_index = (rotation_index + 1) % len(rotation_order)
due_date = today + frequency_days
status = 'pending'
```

### Scheduler jobs (`django-crontab`, e.g. runs hourly)
Defined as plain functions in `chores/cron.py`, registered in `settings.py`'s `CRONJOBS`, installed onto the system crontab via `python manage.py crontab add`.
1. **Reminder pass**: for chores where `due_date <= today` and `status == 'pending'` → generate a completion token, send WhatsApp message to the current assignee with the link, set `status = 'reminded'`.
2. **Escalation pass**: for chores where `status == 'reminded'` and `now > due_date + grace_hours` → post a message to the group chat naming the overdue person and chore, set `status = 'escalated'`. (Optionally re-escalate once every 24h until done — your call.)

### Completion
`GET /done/<token>` → look up token → if valid and unused → mark chore done, advance rotation, mark token used → reply with a simple "✅ Marked done" template → optionally post confirmation to the group.

### Chat commands (parsed in the inbound webhook view)
- `add <chore> | every <N> days | <person1,person2,...>`
- `list` — show all chores, current assignee, due date, status
- `remove <chore>`
- `help`

Keep the parser simple (split on `|`, trim whitespace) — no need for NLP here.

## 6. Twilio Setup Steps
1. Create a free Twilio account.
2. Activate the WhatsApp Sandbox (Console → Messaging → Try WhatsApp) for development; everyone in the household joins the sandbox by sending the join code once.
3. Note your Sandbox number, Account SID, and Auth Token.
4. Set the sandbox's "when a message comes in" webhook to `https://<your-vps-domain>/whatsapp/incoming`.
5. For production later (no sandbox banner, custom number), apply for a Twilio WhatsApp Business sender — separate approval step, not needed to start building.

## 7. VPS Deployment Steps
1. Spin up a small droplet (Ubuntu, 1GB RAM is plenty).
2. Install Python, pip, nginx, certbot.
3. Clone your repo, set up a virtualenv, install dependencies (`django`, `gunicorn`, `twilio`, `django-crontab`).
4. Store Twilio credentials and `DJANGO_SECRET_KEY` as environment variables (never commit them).
5. Run `python manage.py migrate` to create the SQLite schema, then `python manage.py createsuperuser` for admin panel access.
6. Run `python manage.py crontab add` to install the reminder/escalation jobs onto the system crontab.
7. Run the Django app under `gunicorn` (`chorebot.wsgi:application`), managed by a `systemd` unit so it restarts on crash/reboot.
8. Configure Nginx as a reverse proxy to gunicorn, get a TLS cert via certbot (Twilio requires HTTPS).
9. Point the Twilio webhook URL at your domain.

## 8. Suggested Project Structure
```
chorebot/
├── manage.py
├── chorebot/                # project package
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── chores/                  # app
│   ├── models.py            # Person, Chore, CompletionToken
│   ├── admin.py             # registers models for the admin panel
│   ├── views.py             # webhook + completion link views
│   ├── urls.py
│   ├── rotation.py          # rotation/due-date logic
│   ├── commands.py          # chat command parsing
│   ├── whatsapp.py          # Twilio send/receive helpers
│   ├── cron.py              # django-crontab job functions (reminders, escalation)
│   └── migrations/
├── templates/
│   └── done.html            # confirmation page for completion link
├── db.sqlite3                # gitignored
├── requirements.txt
├── .env.example
└── chorebot.service           # systemd unit file (runs gunicorn chorebot.wsgi)
```

## 9. Open Decisions Left to You While Building
- Grace period before escalation (e.g. 24h?)
- Whether escalation re-fires daily until resolved, or just once
- Whether to also notify the *next* person in rotation when it's coming up ("you're on deck tomorrow")
- Command syntax refinements as you actually use it
- Whether the Django admin panel should be open to all household members (shared login) or just one "admin" person

## 10. Suggested Build Order
1. `django-admin startproject chorebot && python manage.py startapp chores` — models + rotation logic (testable in the Django shell, no Twilio involvement)
2. Register models in `admin.py`, run `migrate` + `createsuperuser` — confirms the admin panel works end to end
3. Webhook view skeleton + `/whatsapp/incoming` echoing messages back (confirms webhook wiring)
4. `add`/`list`/`remove` commands
5. Completion link flow
6. `django-crontab` job: reminders
7. `django-crontab` job: escalation
8. Deploy to VPS, connect real Twilio sandbox, dogfood with your household
