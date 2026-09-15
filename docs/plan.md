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
| Web framework | Flask (lightweight, plays well with Twilio webhooks) |
| Database | SQLite (via `sqlite3` stdlib or `SQLAlchemy`) |
| WhatsApp integration | Twilio WhatsApp API |
| Scheduler | `APScheduler` (in-process cron, simplest for a single small VPS) |
| Hosting | Self-managed VPS (DigitalOcean/Linode droplet) |
| Process manager | `systemd` service (keeps Flask app + scheduler alive, restarts on crash) |
| Reverse proxy / TLS | Nginx + Let's Encrypt (Twilio requires HTTPS webhook URLs) |

## 2a. Alternative Tech Stack: Django Variant

If you want a web admin UI for managing chores/people/rotations (instead of only chat commands), Django is a reasonable alternative to the Flask stack above.

| Layer | Choice |
|---|---|
| Language | Python |
| Web framework | Django |
| Database | SQLite (Django ORM + migrations) |
| WhatsApp integration | Twilio WhatsApp API |
| Scheduler | `django-crontab` (simpler than Celery+Beat for a single hourly job) |
| Hosting | Self-managed VPS or PaaS (Fly.io/Railway/Render) |
| Process manager | `systemd` (VPS) or platform-managed (PaaS) |
| Reverse proxy / TLS | Nginx + Let's Encrypt (VPS only; PaaS handles this automatically) |

**Why consider it**: Django's auto-generated admin panel gives you a free web page to view/edit chores, people, and rotation state — useful if you want to check "who's on the hook this week" from a browser instead of only via chat commands.

**Trade-offs vs. Flask**:
- More boilerplate for this project's size (two routes: `POST /whatsapp/incoming`, `GET /done/<token>`) — Django's app/settings/urls scaffolding is built for larger multi-model apps.
- Scheduling is still a bolt-on either way; `django-crontab` is the lightweight choice here — avoid Celery+Beat unless you need it elsewhere, since it requires a Redis/RabbitMQ broker.
- Deploy is slightly heavier than Flask+gunicorn but not dramatically so.

**When to pick this instead**: you want the admin UI, or you already know Django better than Flask. Otherwise, the Flask stack in Section 2 stays the simpler fit.

## 3. System Components

```
┌─────────────┐      webhook (incoming msg)      ┌──────────────┐
│   Twilio    │ ───────────────────────────────▶ │  Flask app   │
│ WhatsApp API│ ◀─────────────────────────────── │  (webhooks)  │
└─────────────┘      outgoing msg (API call)      └──────┬───────┘
                                                          │
                                                   ┌──────▼───────┐
                                                   │   SQLite DB  │
                                                   │ chores, people│
                                                   │ rotation state│
                                                   └──────▲───────┘
                                                          │
                                                   ┌──────┴───────┐
                                                   │ APScheduler  │
                                                   │ (reminders + │
                                                   │  escalation) │
                                                   └──────────────┘
```

Two entry points into the app:
1. **Inbound webhook** (`POST /whatsapp/incoming`) — Twilio calls this whenever someone sends a message in the group. Used for commands (`add`, `list`, `remove`, `help`).
2. **Completion link** (`GET /done/<token>`) — the bot sends this link in reminders; opening it marks the chore done. No login needed since the token is unique and single-use.

A background scheduler runs independently of requests, checking due/overdue chores and sending messages proactively via the Twilio REST API (not the webhook).

## 4. Database Schema

**people**
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | |
| phone | TEXT | WhatsApp number, for @mentions in escalation text |

**chores**
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | |
| frequency_days | INTEGER | e.g. 1 = daily, 7 = weekly |
| rotation_order | TEXT | JSON list of person IDs, in turn order |
| rotation_index | INTEGER | whose turn it currently is |
| due_date | DATE | when it's next due |
| grace_hours | INTEGER | how long after due_date before escalating (default e.g. 24) |
| status | TEXT | `pending` / `reminded` / `escalated` / `done` |

**completion_tokens**
| column | type | notes |
|---|---|---|
| token | TEXT PK | random, e.g. via `secrets.token_urlsafe` |
| chore_id | INTEGER FK | |
| created_at | DATETIME | |
| used | BOOLEAN | prevents replay |

## 5. Core Logic

### Rotation
On chore creation, `rotation_index = 0`, assignee = `rotation_order[0]`.
On completion:
```
rotation_index = (rotation_index + 1) % len(rotation_order)
due_date = today + frequency_days
status = 'pending'
```

### Scheduler jobs (APScheduler, e.g. runs hourly)
1. **Reminder pass**: for chores where `due_date <= today` and `status == 'pending'` → generate a completion token, send WhatsApp message to the current assignee with the link, set `status = 'reminded'`.
2. **Escalation pass**: for chores where `status == 'reminded'` and `now > due_date + grace_hours` → post a message to the group chat naming the overdue person and chore, set `status = 'escalated'`. (Optionally re-escalate once every 24h until done — your call.)

### Completion
`GET /done/<token>` → look up token → if valid and unused → mark chore done, advance rotation, mark token used → reply with a simple "✅ Marked done" HTML page → optionally post confirmation to the group.

### Chat commands (parsed in the inbound webhook)
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
3. Clone your repo, set up a virtualenv, install dependencies.
4. Store Twilio credentials as environment variables (never commit them).
5. Run the Flask app under `gunicorn`, managed by a `systemd` unit so it restarts on crash/reboot.
6. Configure Nginx as a reverse proxy to gunicorn, get a TLS cert via certbot (Twilio requires HTTPS).
7. Point the Twilio webhook URL at your domain.

## 8. Suggested Project Structure
```
chore-bot/
├── app.py                # Flask app, routes
├── models.py              # SQLite schema + queries
├── rotation.py            # rotation/due-date logic
├── scheduler.py           # APScheduler jobs (reminders, escalation)
├── whatsapp.py            # Twilio send/receive helpers
├── commands.py            # chat command parsing
├── templates/
│   └── done.html          # confirmation page for completion link
├── chorebot.db             # SQLite file (gitignored)
├── requirements.txt
├── .env.example
└── chorebot.service        # systemd unit file
```

## 9. Open Decisions Left to You While Building
- Grace period before escalation (e.g. 24h?)
- Whether escalation re-fires daily until resolved, or just once
- Whether to also notify the *next* person in rotation when it's coming up ("you're on deck tomorrow")
- Command syntax refinements as you actually use it

## 10. Suggested Build Order
1. DB models + rotation logic (testable without any Twilio involvement)
2. Flask app skeleton + `/whatsapp/incoming` echoing messages back (confirms webhook wiring)
3. `add`/`list`/`remove` commands
4. Completion link flow
5. Scheduler: reminders
6. Scheduler: escalation
7. Deploy to VPS, connect real Twilio sandbox, dogfood with your household
