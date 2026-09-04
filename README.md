IncidentPilot

Real-Time AI Co-Commander for High-Stakes Incidents

IncidentPilot is an enterprise-minded incident response assistant designed to help engineering and operations teams build a shared, evidence-first view of an incident while keeping consequential actions under human control.

AI recommends. Humans authorize. System enforces.

What Problem Does It Solve?




hypotheses

conflicts

unknown or missing information

decisions

recommended actions

ownership

incident timeline

approval and audit history

The goal is not to replace the incident commander. The goal is to help the team understand what is known, what is uncertain, what should be verified next, and what action requires human authorization.

Core Capabilities

Evidence-First Incident Intelligence

Incident information is classified instead of being treated as one undifferentiated summary.

Fact — supported by available evidence

Hypothesis — possible explanation that still needs verification

Conflict — contradictory claims or signals that need investigation

Unknown — important information that is still missing

The system is designed to avoid presenting an unverified hypothesis as a confirmed root cause.

Real-Time Incident Room

IncidentPilot uses Agora RTC as the real-time communication layer for an incident room, allowing responders and the IncidentPilot agent to participate in the same voice environment.

The project also contains the foundation for Agora Conversational AI integration and server-side agent lifecycle management. Actual Conversational AI availability depends on valid Agora project configuration and credentials.

Human-Controlled Actions

Consequential actions are intentionally constrained by:

AI recommendation
        ↓
Policy check
        ↓
Permission / RBAC check
        ↓
Human approval
        ↓
Authorized execution
        ↓
Audit event

The AI should not receive unrestricted production-write privileges.

Conflict and Missing-Information Detection

The incident state can surface contradictions such as:

Engineer: “Database is healthy.”
Monitoring: “Latency is 4.8 seconds.”

IncidentPilot should surface:

🔴 CONFLICT DETECTED
Human report: Database healthy
Telemetry: 4.8s latency

Next step:
Verify current DB latency and saturation before treating DB health as confirmed.

It does not invent a root cause or silently choose one side.

🎙️ Real-Time Conversational AI

Agora Conversational AI is a core part of the intended runtime voice experience.

┌──────────────────────┐
│   Responder Mic      │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│      Agora RTC       │
└──────────┬───────────┘
           ↓
┌──────────────────────────────┐
│ Agora Conversational AI Agent│
└──────────┬───────────────────┘
           ↓
      STT / ASR
           ↓
    Managed LLM
           ↓
┌──────────────────────────────┐
│  IncidentPilot Reasoning     │
│  Facts / Hypotheses / Risk    │
│  Conflicts / Next Step        │
└──────────┬───────────────────┘
           ↓
          TTS
           ↓
┌──────────────────────┐
│      Agora RTC       │
└──────────┬───────────┘
           ↓
      Incident Room

Intended managed model stack

STT: Deepgram

LLM: OpenAI

TTS: MiniMax

Actual Conversational AI availability depends on valid Agora project configuration, credentials, and successful runtime verification.

🔄 How IncidentPilot Works

OBSERVE
   ↓
UNDERSTAND
   ↓
COORDINATE
   ↓
RECOMMEND
   ↓
VERIFY
   ↓
CONTROL
   ↓
LEARN

01 — Observe

Capture approved voice, chat, alerts, telemetry, and incident context.

02 — Understand

Structure incoming information into facts, hypotheses, conflicts, unknowns, decisions, and actions.

03 — Coordinate

Track responders, ownership, decisions, next steps, and an incident timeline.

04 — Recommend

Suggest the next useful question, verification step, or safe mitigation.

05 — Verify

Require evidence before promoting hypotheses into confirmed outcomes.

06 — Control

Apply RBAC, policies, allowlists, and human approval before consequential actions.

07 — Learn

Use only verified outcomes to improve future incident context.

🛡️ Human-Controlled Automation

IncidentPilot follows a policy-bounded execution model:

AI Recommendation
       ↓
Evidence + Risk
       ↓
Policy Check
       ↓
RBAC / Permission Check
       ↓
Human Approval
       ↓
Authorized Execution
       ↓
Audit Event

Critical actions should never receive unrestricted AI access.

Examples include:

deployment rollback

production service restart

routing changes

feature disablement

infrastructure changes

privileged remediation

external operational notifications

The AI can recommend an action. A named human authorizes it.

🔐 Security by Design

Security is treated as part of the architecture, not as a separate add-on.

Role-Based Access Control (RBAC)

Least-privilege execution

Organization / tenant isolation

Incident-scope authorization

Allowlisted tools and actions

Strict action parameter validation

Human approval for consequential actions

Audit logging and decision history

Secret redaction

Safe handling of untrusted transcript/chat content

Prompt-injection-aware boundaries

Replay and expiry protection for sensitive workflows

The AI is not an administrator.

📊 What the Operator Sees

The IncidentPilot command center is designed around one shared operational state:

┌────────────────────────────────────────────────────────┐
│ LIVE INCIDENT                                          │
│ Status • Severity • Responders • Agora / AI status     │
├────────────────────────────────────────────────────────┤
│ EVIDENCE                                               │
│ ✅ Facts   ⚠️ Hypotheses   🔴 Conflicts   ❓ Unknowns  │
├────────────────────────────────────────────────────────┤
│ NEXT BEST STEP                                         │
│ Recommendation • Evidence • Risk • Approval required  │
├────────────────────────────────────────────────────────┤
│ ACTIONS                                                │
│ Owner • Status • Approval • Execution result           │
├────────────────────────────────────────────────────────┤
│ INCIDENT TIMELINE                                      │
│ Signal → Fact → Hypothesis → Conflict → Approval →     │
│ Verified Recovery                                      │
└────────────────────────────────────────────────────────┘

🧪 Example Incident Flow

Payment outage demonstration

10:02  SIGNAL       Payment failures spike
10:06  FACT         Customer impact confirmed
10:08  HYPOTHESIS   DB latency may contribute
10:12  ACTION       Investigation assigned
10:15  CONFLICT     “DB healthy” vs 4.8s latency
10:18  AI UPDATE    Next verification step suggested
10:21  APPROVAL     Human authorizes mitigation
10:26  VERIFIED     Recovery confirmed and logged

The same reasoning model is intended for incidents such as:

API outages · database failures · deployment regressions · authentication failures · network issues · cache/queue failures · service crashes · storage/dependency failures · security incidents · unknown technical incidents

🏗️ Architecture

                           INCIDENTPILOT
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
   LIVE ENGAGEMENT          INCIDENT INTELLIGENCE      CONTROL PLANE
        │                         │                         │
   Agora RTC                 STT / ASR                 RBAC
   Agora Chat                Evidence model            Policy engine
   Conversational AI         Conflict detection        Human approval
   Voice events              Runbook context            Allowlisted tools
        │                         │                         │
        └─────────────────────────┼─────────────────────────┘
                                  │
                           TRUSTED MEMORY
                                  │
                  Timeline • Audit • Knowledge
                                  │
                         Verified Learning

Repository structure

IncidentPilot/
├── apps/
│   └── api/
│       ├── app/
│       │   ├── actions/
│       │   ├── ai/
│       │   ├── api/
│       │   ├── auth/
│       │   ├── core/
│       │   ├── db/
│       │   ├── integrations/
│       │   ├── learning/
│       │   ├── services/
│       │   └── static/
│       ├── alembic/
│       └── tests/
├── .agents/
│   └── skills/
│       └── agora/
├── Dockerfile
├── docker-compose.yml
├── DEPLOYMENT.md
├── pyproject.toml
└── README.md

⚙️ Technology Stack

Layer

Technology

Backend

Python, FastAPI

Database

SQLAlchemy, SQLite (local), PostgreSQL (production)

Migrations

Alembic

Validation / Config

Pydantic Settings

Authentication

JWT-based auth

Real-Time

Agora RTC

Voice AI

Agora Conversational AI

AI Pipeline

STT → LLM → TTS

Frontend

HTML, CSS, JavaScript

Testing

Pytest, HTTPX

Deployment

Docker / Docker Compose

🚀 Run Locally

1. Create a virtual environment

Windows PowerShell

python -m venv .venv
.\.venv\Scripts\Activate.ps1

Linux / macOS

python3 -m venv .venv
source .venv/bin/activate

2. Install dependencies

python -m pip install --upgrade pip
pip install -e ".[dev]"

3. Configure environment

Windows PowerShell

Copy-Item .env.example .env

Linux / macOS

cp .env.example .env

Never commit .env or real credentials.

4. Run database migrations

alembic upgrade head

5. Start the application

uvicorn app.main:app --app-dir apps/api --reload

Open:

http://127.0.0.1:8000/

Important: open the application through FastAPI. Do not open index.html directly with file://.

❤️ Health Checks

GET /health/live
GET /health/ready
GET /health

🧪 Testing

Run the test suite:

pytest -v

The project contains tests around authentication, incidents, actions, intelligence, learning, integrations, room APIs, Agora-related services, and multilingual behavior.

Automated tests are not a substitute for a real voice-room validation. For a live Agora deployment, verify the complete voice path with valid Agora configuration.

🎙️ Agora Configuration

Create and configure an Agora project, then provide the required server-side configuration through environment variables.

Example:

AGORA_APP_ID=your_app_id
AGORA_APP_CERTIFICATE=your_app_certificate
AGORA_TOKEN_EXPIRE_SECONDS=3600

Keep credentials server-side and never commit them.

Agora reference material used by the project is available under:

.agents/skills/agora/

For real deployment, validate the Agora project configuration and run the official diagnostic tooling available for the installed project/CLI setup.

🔌 Real vs Simulation

IncidentPilot may include demo/simulation behavior for environments where external credentials are unavailable.

Status

Meaning

🟢 REAL

Actual configured external service

🟡 SIMULATION

Controlled demonstration behavior

⚪ NOT CONFIGURED

Credentials/service configuration is missing

🔵 PLANNED

Architecture defined, implementation not active

A failed external operation must never be represented as a successful production action.

📚 Verified Learning Loop

IncidentPilot is designed to learn from verified outcomes without turning historical assumptions into current facts.

Incident
   ↓
Investigation
   ↓
Verified Outcome
   ↓
Validation
   ↓
Knowledge Base
   ↓
Future Incident Context

Historical patterns can inform an investigation, but they do not automatically become current incident facts.

📦 Deployment

For containerized local deployment:

docker compose up -d --build

See DEPLOYMENT.md for the deployment configuration and production checklist.

For production, use:

strong secrets

explicit CORS origins

PostgreSQL or another supported production database

secure networking

real Agora credentials

appropriate observability

retention/privacy controls

🎬 Demo Flow

A simple judge/demo flow:

Create Incident
      ↓
Join Agora Incident Room
      ↓
Start AI Co‑Commander
      ↓
Speak the Incident
      ↓
Facts / Hypotheses / Conflicts / Unknowns
      ↓
Next Best Verification Step
      ↓
Recommended Mitigation
      ↓
Human Approval
      ↓
Controlled Action
      ↓
Audit Event
      ↓
Verified Recovery

The strongest demonstration is not a long summary. It is showing that the AI understands the changing incident state, asks useful questions, detects conflicting evidence, and recommends the next step without taking uncontrolled production actions.

👥 Team DataDynamos

Member

Focus

Bharat Shishodia

Team Lead · Product & Security

Madan Mohan Mishra

Problem & Solution · Engineering

Preetam Gupta

Architecture

Prince Raj

AI · Presentation & Delivery

🏆 Why IncidentPilot?

Evidence-first

Facts, hypotheses, conflicts, and unknowns are explicitly separated.

Voice-native

The co-commander is designed to participate in the same real-time incident room as responders.

Human-controlled

Consequential actions remain behind policy, permissions, and explicit approval.

Enterprise-minded

Tenant isolation, auditability, runbook grounding, controlled integrations, and verified learning are part of the design.

Built for the room, not after the incident

IncidentPilot is designed to help responders make sense of an incident while it is happening, not only summarize it afterward.

📌 Current Project Status

IncidentPilot is an active hackathon project with a strong incident-intelligence and control-plane foundation. The final runtime status of external services, including Agora Conversational AI, depends on valid project configuration and successful end-to-end verification in the deployment environment.
