# SponsorFlow

SponsorFlow is a small, self-hosted agentic outreach workspace for finding and contacting potential sponsors for the Hacktoberfest Hack Day at NIT Hamirpur.

It is a standalone application designed to provide a complete local workflow that is easy to understand, test, and extend.

## Product workflow

1. **Lead finder agent** searches a small, editable sponsor directory using the event brief and scores likely matches.
2. A human reviews the suggested leads and selects the people or companies worth contacting.
3. **Outreach agent** creates channel-specific drafts for email, LinkedIn, and a call briefing.
4. A human approves each draft. The default providers are safe local simulators, so no message leaves the machine accidentally.
5. Approved actions are recorded in the activity feed and the dashboard updates the lead status.


## Run locally

Requirements: Python 3.10+.

```powershell
python app.py
```

Open <http://127.0.0.1:8000>.

The database is created at `data/sponsorflow.db`. Use **Reset demo data** in the dashboard to restore the sample workspace.


### Real email through SMTP

Set the following environment variables before starting the app. The email provider is opt-in: email is sent only when `EMAIL_PROVIDER=smtp` and an email draft is explicitly approved in the dashboard.

```powershell
$env:EMAIL_PROVIDER = "smtp"
$env:SMTP_HOST = "smtp.your-provider.com"
$env:SMTP_PORT = "587"
$env:SMTP_USERNAME = "you@example.com"
$env:SMTP_PASSWORD = "your-app-password-or-smtp-password"
$env:SMTP_FROM = "you@example.com"
$env:SMTP_USE_SSL = "false"
python app.py
```

Use `SMTP_USE_SSL=true` for providers that require implicit TLS (usually port 465). For Gmail, use an app password rather than your normal account password. Never commit these values; `.env.example` contains placeholders only.

## API overview

- `GET /api/dashboard` - dashboard data.
- `POST /api/agents/find-leads` - score and add matching leads.
- `POST /api/outreach/drafts` - create drafts for selected leads.
- `POST /api/outreach/approve` - approve and execute one draft through the configured provider.
- `POST /api/reset` - restore demo data.

## Design

The interface uses a Linear-inspired dark workspace layout: a compact sidebar, metric cards, dense lead table, and a right-hand activity stream. The frontend is plain HTML/CSS/JavaScript so the project has no build step or dependency installation.
