# SponsorFlow

SponsorFlow is a small, self-hosted agentic outreach workspace for finding and contacting potential sponsors for the Hacktoberfest Hack Day at NIT Hamirpur.

It is a standalone application designed to provide a complete local workflow that is easy to understand, test, and extend.

## Product workflow

1. **Lead finder agent** searches a small, editable sponsor directory using the event brief and scores likely matches.
2. A human reviews the suggested leads and selects the people or companies worth contacting.
3. **Outreach agent** creates channel-specific drafts for email, LinkedIn, and a call briefing.
4. A human approves each draft. The default providers are safe local simulators, so no message leaves the machine accidentally.
5. Approved actions are recorded in the activity feed and the dashboard updates the lead status.

## Tasks to be achieved

- [x] Create a local SQLite-backed application with a simple API.
- [x] Add a lead-finding agent with relevance scoring and reasons.
- [x] Add email, LinkedIn, and phone-call outreach draft generation.
- [x] Add human approval before an outreach action can be executed.
- [x] Add safe simulated providers for all three channels.
- [x] Add optional AI-generated personalized drafts with a local fallback.
- [x] Import the four supplied community contacts when the lead finder runs.
- [x] Show full activity and message details in a click-to-open viewer.
- [x] Add a dashboard showing leads, scores, drafts, statuses, and activity.
- [x] Add demo data so the complete workflow works without credentials.
- [x] Add opt-in SMTP email delivery with explicit approval.
- [ ] Replace simulated LinkedIn with an approved LinkedIn integration or an export workflow.
- [ ] Replace simulated calls with a telephony provider such as Twilio.
- [ ] Add authentication and role-based access before deploying for a team.
- [ ] Add event-specific lead imports, deduplication, and richer company research.

## Run locally

Requirements: Python 3.10+.

```powershell
python app.py
```

Open <http://127.0.0.1:8000>.

The database is created at `data/sponsorflow.db`. Use **Reset demo data** in the dashboard to restore the sample workspace.

## Safety and provider configuration

The dashboard displays `RUNNING MODE` by default. Actual email delivery still requires `EMAIL_PROVIDER=smtp` and explicit approval; otherwise actions remain local and do not contact a third party. Do not add credentials to the repository.

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

### Optional AI-generated drafts

Set `AI_DRAFTS_ENABLED=true` and provide `OPENAI_API_KEY` to generate personalized subject lines and message bodies through the OpenAI Responses API. The app sends only the lead and event context needed to draft the message, requests `store=false`, and falls back to local personalized templates if the API is unavailable. An API key is not required for the demo.

```powershell
$env:AI_DRAFTS_ENABLED = "true"
$env:OPENAI_API_KEY = "your-openai-api-key"
$env:OPENAI_MODEL = "gpt-5"
```

### LinkedIn messages

The app cannot safely send ordinary one-to-one LinkedIn inbox messages using a normal developer application. LinkedIn requires OAuth and restricts most API products to approved applications; its generally available member permission is for sharing posts, not arbitrary inbox messaging. LinkedIn drafts therefore remain available for a human to send manually. Do not use browser automation or scraping to bypass LinkedIn restrictions.

Any real provider must include:

- explicit user approval,
- rate limiting,
- audit logging,
- unsubscribe handling,
- consent and platform policy checks,
- secrets loaded from environment variables or a secret manager.

LinkedIn automation must not bypass LinkedIn restrictions. The current implementation creates a suggested message and records a simulated action for a human to send manually or through an approved integration.

## API overview

- `GET /api/dashboard` - dashboard data.
- `POST /api/agents/find-leads` - score and add matching leads.
- `POST /api/outreach/drafts` - create drafts for selected leads.
- `POST /api/outreach/approve` - approve and execute one draft through the configured provider.
- `POST /api/reset` - restore demo data.

## Design

The interface uses a Linear-inspired dark workspace layout: a compact sidebar, metric cards, dense lead table, and a right-hand activity stream. The frontend is plain HTML/CSS/JavaScript so the project has no build step or dependency installation.
