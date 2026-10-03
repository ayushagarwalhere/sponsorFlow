from __future__ import annotations

import json
import os
import smtplib
import sqlite3
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "sponsorflow.db"
STATIC_DIR = ROOT / "static"
EVENT_BRIEF = (
    "Hacktoberfest Hack Day × ISTE-NITH on 11th October 2026 at NIT Hamirpur, "
    "as part of MLH Fall 2026, with 400+ student developers expected."
)
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "simulated").lower()
AI_DRAFTS_ENABLED = os.getenv("AI_DRAFTS_ENABLED", "false").lower() in {"1", "true", "yes"}
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

DEMO_COMPANIES = [
    ("GitLab", "DevTools", "India", "opensource, developer tools, hackathon", "developer-relations@gitlab.example", "Aarav Mehta"),
    ("DigitalOcean", "Cloud", "India", "cloud, developers, student programs", "community@digitalocean.example", "Maya Shah"),
    ("Postman", "DevTools", "Bengaluru", "API, developers, student community", "campus@postman.example", "Rohan Kapoor"),
    ("BrowserStack", "Testing", "Mumbai", "developer tools, testing, engineering", "community@browserstack.example", "Isha Verma"),
    ("Himalayan Outdoor Co.", "Retail", "Himachal Pradesh", "outdoor, youth, local community", "partnerships@himalayan.example", "Neha Thakur"),
    ("Acme Textiles", "Manufacturing", "Delhi", "manufacturing, education", "hello@acmetextiles.example", "Vikram Sethi"),
]

# These are the supplied contacts. They should enter the pipeline when the
# lead finder runs, rather than appearing in the initial demo workspace.
SUPPLIED_LEADS = [
    ("Spring House Workspace", "Community Workspace", "India", "community, workspace, startup, developers", "devansh@springhouse.in", "Devansh Sharma"),
    ("NetSmartz", "Technology Services", "India", "community, technology, developers, education", "sanjay.mittu@netsmartz.com", "Sanjay Mittu"),
    ("StrataScratch", "Data Education", "Remote", "community, data, developers, education", "suman@stratascratch.com", "Suman S"),
    ("India Accelerator", "Startup Accelerator", "India", "community, startups, founders, developers", "rohan.chauhan@indiaaccelerator.co", "Rohan Chauhan"),
]

CONTACT_ROLES = {
    "Devansh Sharma": "Community Manager",
    "Sanjay Mittu": "Community Manager",
    "Suman S": "Community Manager",
    "Rohan Chauhan": "Community Manager",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                industry TEXT NOT NULL,
                location TEXT NOT NULL,
                contact TEXT NOT NULL,
                email TEXT NOT NULL,
                fit_score INTEGER NOT NULL DEFAULT 0,
                fit_reason TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id),
                channel TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                approved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER REFERENCES leads(id),
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )
        activity_columns = {row["name"] for row in db.execute("PRAGMA table_info(activities)").fetchall()}
        if "details" not in activity_columns:
            db.execute("ALTER TABLE activities ADD COLUMN details TEXT NOT NULL DEFAULT ''")


def add_activity(db: sqlite3.Connection, lead_id: int | None, kind: str, message: str, details: str = "") -> None:
    db.execute(
        "INSERT INTO activities (lead_id, kind, message, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (lead_id, kind, message, details, now()),
    )


def reset_demo() -> None:
    with connect() as db:
        db.execute("DELETE FROM activities")
        db.execute("DELETE FROM drafts")
        db.execute("DELETE FROM leads")
        for company, industry, location, tags, email, contact in DEMO_COMPANIES:
            db.execute(
                """INSERT INTO leads
                (company, industry, location, contact, email, fit_score, fit_reason, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)""",
                (company, industry, location, contact, email, 0, tags, now()),
            )
        add_activity(db, None, "system", "Workspace ready. Run the lead finder to load the supplied contacts.")


def seed_supplied_leads() -> int:
    """Import supplied contacts without deleting the existing workspace."""
    added = 0
    with connect() as db:
        existing = {row["company"] for row in db.execute("SELECT company FROM leads").fetchall()}
        for company, industry, location, tags, email, contact in SUPPLIED_LEADS:
            if company in existing:
                continue
            db.execute(
                """INSERT INTO leads
                (company, industry, location, contact, email, fit_score, fit_reason, status, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, 'new', ?)""",
                (company, industry, location, contact, email, tags, now()),
            )
            added += 1
    return added


def score_lead(row: tuple[str, str, str, str, str, str]) -> tuple[int, str]:
    company, industry, location, tags, _, _ = row
    text = f"{company} {industry} {location} {tags}".lower()
    signals = {
        "open source": 30,
        "developer": 25,
        "devtools": 25,
        "hackathon": 20,
        "student": 15,
        "community": 15,
        "cloud": 10,
        "testing": 10,
        "himachal": 10,
    }
    matched = [label for label, points in signals.items() if label in text]
    score = min(98, 35 + sum(signals[label] for label in matched))
    reason = "Strong match on " + ", ".join(matched[:3]) if matched else "Potential regional or education sponsor"
    return score, reason


def find_leads() -> int:
    # Preserve the demo workspace and append the supplied contacts when the
    # finder is explicitly run.
    seed_supplied_leads()
    changed = 0
    with connect() as db:
        rows = db.execute(
            "SELECT company, industry, location, fit_reason, email, contact FROM leads WHERE status = 'new'"
        ).fetchall()
        for row in rows:
            score, reason = score_lead(tuple(row))
            db.execute(
                "UPDATE leads SET fit_score = ?, fit_reason = ? WHERE company = ?",
                (score, reason, row["company"]),
            )
            changed += 1
        add_activity(db, None, "agent", f"Lead finder scored {changed} candidates against the event brief.")
    return changed


def make_drafts(lead_ids: list[int]) -> int:
    if not isinstance(lead_ids, list) or any(isinstance(lead_id, bool) or not isinstance(lead_id, int) for lead_id in lead_ids):
        raise ValueError("lead_ids must be a list of integer IDs")
    created = 0
    with connect() as db:
        if not lead_ids:
            lead_ids = [row["id"] for row in db.execute(
                "SELECT id FROM leads WHERE fit_score > 0 AND status != 'contacted' ORDER BY id"
            ).fetchall()]
        for lead_id in lead_ids:
            lead = db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if not lead or lead["fit_score"] < 1:
                continue
            existing = db.execute("SELECT 1 FROM drafts WHERE lead_id = ? AND status = 'pending'", (lead_id,)).fetchone()
            if existing:
                continue
            context = (
                "We are hosting Hacktoberfest Hack Day × ISTE-NITH on 11th October 2026 "
                "at NIT Hamirpur, as part of MLH Fall 2026, with 400+ student developers expected."
            )
            contact_role = CONTACT_ROLES.get(lead["contact"], "community-minded professional")
            outreach_body = (
                f"Hi {lead['contact']}! I’m Ayush from the ISTE-NITH Chapter at NIT Hamirpur.\n\n"
                f"I came across your profile and saw that you’re a {contact_role} at {lead['company']}. "
                f"We’re hosting {context}\n\n"
                f"We’d love to explore if {lead['company']} could support the event through products/peripherals as prizes, "
                "developer-focused challenges, mentorship/judging, or other support for the participants. It would also be "
                f"great to have you or someone from {lead['company']} join us as a speaker, mentor, or judge and interact "
                "with the student builders.\n\n"
                "We’re now in the final phase of planning with the event next Sunday, so if this is something you could help "
                "us explore internally, I’d really appreciate it. If there’s someone else on your team who could help me with "
                "this, I’d be grateful if you could connect me with them.\n\n"
                "Even a small contribution would genuinely help us make the event better for the participants. Happy to share "
                "the event deck and discuss this further.\n\nBest,\nAyush\nISTE-NITH Chapter, NIT Hamirpur"
            )
            drafts = [
                ("email", f"Partner with {lead['company']} for Hacktoberfest Hack Day × ISTE-NITH", outreach_body),
                ("linkedin", "", outreach_body),
                ("call", "Call briefing", f"Goal: ask {lead['contact']} at {lead['company']} for a 15-minute sponsorship conversation.\n\n{outreach_body}"),
            ]
            if AI_DRAFTS_ENABLED and os.getenv("OPENAI_API_KEY"):
                for index, (channel, subject, body) in enumerate(drafts):
                    try:
                        generated = generate_ai_draft(lead, channel)
                        drafts[index] = (channel, generated["subject"], generated["body"])
                    except (OSError, ValueError, KeyError, urllib.error.URLError) as error:
                        add_activity(db, lead_id, "agent", f"AI draft fallback used for {lead['company']} ({channel}): {error}")
            for channel, subject, body in drafts:
                db.execute(
                    "INSERT INTO drafts (lead_id, channel, subject, body, created_at) VALUES (?, ?, ?, ?, ?)",
                    (lead_id, channel, subject, body, now()),
                )
            db.execute("UPDATE leads SET status = 'drafted' WHERE id = ?", (lead_id,))
            add_activity(db, lead_id, "agent", f"Outreach agent prepared email, LinkedIn, and call drafts for {lead['company']}.")
            created += 1
    return created


def generate_ai_draft(lead: sqlite3.Row, channel: str) -> dict[str, str]:
    """Generate one draft with the OpenAI Responses API, without requiring an SDK."""
    prompt = (
        "Create a concise, respectful sponsorship outreach draft for a university open-source event. "
        "Personalize it using the recipient and company context. Do not invent facts. "
        "Return JSON only with string fields subject and body. For LinkedIn and call drafts, subject may be empty.\n\n"
        f"Channel: {channel}\nRecipient: {lead['contact']}\nCompany: {lead['company']}\n"
        f"Industry: {lead['industry']}\nLocation: {lead['location']}\nFit signals: {lead['fit_reason']}\n"
        f"Event: {EVENT_BRIEF}"
    )
    request_body = json.dumps({"model": OPENAI_MODEL, "store": False, "input": prompt}).encode()
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=request_body,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.loads(response.read().decode())
    output_text = result.get("output_text", "").strip()
    if not output_text:
        for item in result.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    output_text += content.get("text", "")
    generated = json.loads(output_text)
    if not isinstance(generated.get("subject"), str) or not isinstance(generated.get("body"), str):
        raise ValueError("AI response did not include subject and body")
    return {"subject": generated["subject"].strip(), "body": generated["body"].strip()}


def send_email(draft: sqlite3.Row) -> None:
    """Deliver an approved email through SMTP when explicitly configured."""
    required = {name: os.getenv(name) for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD")}
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("SMTP is enabled but missing: " + ", ".join(missing))
    recipient = draft["email"] if "email" in draft.keys() else None
    if not recipient:
        raise RuntimeError("The selected lead has no email address")
    message = EmailMessage()
    message["From"] = os.getenv("SMTP_FROM", required["SMTP_USERNAME"])
    message["To"] = recipient
    message["Subject"] = draft["subject"] or "Sponsorship opportunity"
    message.set_content(draft["body"])
    host = required["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context()) as server:
            server.login(required["SMTP_USERNAME"], required["SMTP_PASSWORD"])
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(required["SMTP_USERNAME"], required["SMTP_PASSWORD"])
            server.send_message(message)


def approve_draft(draft_id: int) -> dict[str, Any] | None:
    with connect() as db:
        draft = db.execute(
            "SELECT drafts.*, leads.company, leads.contact, leads.email FROM drafts JOIN leads ON leads.id = drafts.lead_id WHERE drafts.id = ?",
            (draft_id,),
        ).fetchone()
        if not draft:
            return None
        if draft["status"] == "approved":
            return dict(draft)
        if draft["channel"] == "email" and EMAIL_PROVIDER == "smtp":
            send_email(draft)
        elif draft["channel"] == "linkedin" and EMAIL_PROVIDER == "smtp":
            raise RuntimeError("LinkedIn one-to-one messages require an approved LinkedIn API product; use the draft for manual sending.")
        db.execute("UPDATE drafts SET status = 'approved', approved_at = ? WHERE id = ?", (now(), draft_id))
        db.execute("UPDATE leads SET status = 'contacted' WHERE id = ?", (draft["lead_id"],))
        channel_label = {"email": "email", "linkedin": "LinkedIn message", "call": "call briefing"}[draft["channel"]]
        add_activity(
            db,
            draft["lead_id"],
            "sent",
            f"{'Sent' if draft['channel'] == 'email' and EMAIL_PROVIDER == 'smtp' else 'Simulated'} {channel_label} approved for {draft['company']} ({draft['contact']}).",
            draft["body"],
        )
        approved = dict(draft)
        approved["status"] = "approved"
        approved["approved_at"] = now()
        return approved


def dashboard() -> dict[str, Any]:
    with connect() as db:
        leads = [dict(row) for row in db.execute(
            "SELECT * FROM leads ORDER BY CASE WHEN email NOT LIKE '%%.example' THEN 0 ELSE 1 END, fit_score DESC, id"
        ).fetchall()]
        drafts = [
            dict(row)
            for row in db.execute(
                "SELECT drafts.*, leads.company, leads.contact FROM drafts JOIN leads ON leads.id = drafts.lead_id ORDER BY drafts.id DESC"
            ).fetchall()
        ]
        activities = [
            dict(row)
            for row in db.execute(
                "SELECT activities.*, leads.company FROM activities LEFT JOIN leads ON leads.id = activities.lead_id ORDER BY activities.id DESC LIMIT 20"
            ).fetchall()
        ]
    return {
        "event_brief": EVENT_BRIEF,
        "mode": os.getenv("OUTREACH_MODE", "RUNNING"),
        "stats": {
            "leads": len(leads),
            "qualified": sum(lead["fit_score"] >= 60 for lead in leads),
            "drafts": sum(draft["status"] == "pending" for draft in drafts),
            "contacted": sum(lead["status"] == "contacted" for lead in leads),
        },
        "leads": leads,
        "drafts": drafts,
        "activities": activities,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(size) or b"{}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/dashboard":
            self.send_json(dashboard())
            return
        if path == "/" or path == "/index.html":
            content = (STATIC_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if path in ("/app.js", "/styles.css"):
            file_path = STATIC_DIR / path.lstrip("/")
            content = file_path.read_bytes()
            content_type = "application/javascript" if path.endswith("js") else "text/css"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/reset":
                reset_demo()
                self.send_json(dashboard())
            elif path == "/api/agents/find-leads":
                self.send_json({"count": find_leads(), "dashboard": dashboard()})
            elif path == "/api/outreach/drafts":
                self.send_json({"count": make_drafts(payload.get("lead_ids", [])), "dashboard": dashboard()})
            elif path == "/api/outreach/approve":
                draft_id = payload["draft_id"]
                if isinstance(draft_id, bool) or not isinstance(draft_id, int) or draft_id < 1:
                    raise ValueError("draft_id must be a positive integer")
                result = approve_draft(draft_id)
                self.send_json({"draft": result, "dashboard": dashboard()}, 200 if result else 404)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.send_json({"error": f"Invalid request: {error}"}, 400)
        except Exception as error:
            self.send_json({"error": str(error)}, 500)


if __name__ == "__main__":
    init_db()
    with connect() as db:
        has_leads = db.execute("SELECT 1 FROM leads LIMIT 1").fetchone() is not None
    if not has_leads:
        reset_demo()
    print("SponsorFlow running at http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
