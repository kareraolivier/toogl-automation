#!/usr/bin/env python3
"""
=============================================================================
  Toggl 2.0 Bulk Time Entry Uploader
  ───────────────────────────────────
  Pushes KumvaIoT time entries from 29 Sep 2026 (the day after the last
  report) through 29 Oct 2026 to Toggl 2.0 (focus.toggl.com).
  Client "KumvaIoT". Each GitHub-style ticket is its own Toggl project;
  time-entry descriptions are the actual work notes. Work blocks sit in
  09:00–17:00 and only fill time not already tracked (calendar meetings,
  standups, earlier uploads), so re-runs never double-book a slot.
  Weekends and Rwandan public holidays are skipped.

  RUN:
    python toggle_uploader.py            # reads TOGGL_API_TOKEN from .env
    DRY_RUN=1 python toggle_uploader.py  # show the plan, write nothing

  RESUME:
    Just re-run the same command — it picks up after the last uploaded day.
=============================================================================
"""

import requests
import time
import json
import random
import sys
import os
from collections import Counter, defaultdict
from datetime import date, timedelta, datetime, timezone


def _load_dotenv(filename=".env"):
    """Fill os.environ from KEY=VALUE lines without overriding real env vars."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    except FileNotFoundError:
        pass


_load_dotenv()

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CREDENTIALS — toggl_sk_ key from Toggl 2.0 profile settings             ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
API_TOKEN       = os.environ.get("TOGGL_API_TOKEN", "")
ORGANIZATION_ID = os.environ.get("TOGGL_ORGANIZATION_ID", "21633027")
WORKSPACE_ID    = os.environ.get("TOGGL_WORKSPACE_ID", "21632264")

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CONFIGURATION                                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
CLIENT_NAME              = "KumvaIoT"
UPLOAD_LAYOUT            = "focus-per-ticket"
DELAY_BETWEEN_REQUESTS   = 1.0    # seconds between each API call
MAX_RETRIES              = 3      # max retries on transient errors
DRY_RUN                  = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
LOCAL_TZ                 = timezone(timedelta(hours=2))  # Kigali = CAT = UTC+2
MIN_BLOCK_MIN            = 15     # shorter gaps between meetings are left empty
MAX_BLOCKS_PER_DAY       = 5      # generated work blocks per day
PROGRESS_FILE            = "toggl_progress.json"
PROJECTS_CACHE_FILE      = "toggl_projects_cache.json"
COMPLETE_FILE            = "toggl_complete.json"
START_DATE               = date(2026, 9, 29)   # day after the last sent report
END_DATE                 = date(2026, 10, 29)  # today

# ═══════════════════════════════════════════════════════════════════════════
#  TICKET DATA  —  Kumva IoT / Analytic_service work
#  Descriptions follow the Discord timeline and GitHub issues you owned
#  or reviewed. Weighted later so weather-API work dominates Jul–Aug.
# ═══════════════════════════════════════════════════════════════════════════

tickets = [
    # ── Kickoff, architecture, domain (May) ──────────────────────────────
    (1,  "Review Kumva proposed system architecture ahead of kickoff"),
    (2,  "Study Kumva Insights backend tech stack and Notion notes"),
    (3,  "Kumva intro session with Sagamba, Alexandra and the Kumva team"),
    (4,  "Daily standup and garden sync with the Kumva delivery team"),
    (5,  "Mental model session: poultry, farms and irrigation domain"),
    (6,  "Work through mental model questions and practical exercises"),
    (7,  "Python and FastAPI groundwork for the analytics service"),
    (8,  "Read backend timeplan and align on analytics service milestones"),

    # ── Architecture, agents, LLM flow (June – mid July) ─────────────────
    (9,  "Map analytics architecture from data ingestion through output"),
    (10, "Define analytics agent types, roles and how they collaborate"),
    (11, "Write functional requirements for each analytics component"),
    (12, "Compare function-based vs gateway-based LLM service designs"),
    (13, "Draft analytics mermaid flow (RabbitMQ, LLM agents, notifications)"),
    (14, "Revise LLM service flowchart after Kumva and Yannick feedback"),
    (15, "Document knowledge ingestion and recommendation agent steps"),
    (16, "Prepare analytics proposal and share with the Kumva team"),
    (17, "DevOps deployment discussion based on the analytics proposal"),
    (18, "Analytics GitHub board setup and sprint planning with Thierry"),

    # ── Implementation: setup, weather API (your ticket), reviews ────────
    (19, "Analytics Service project setup, README and local tooling"),
    (20, "Add tests folder layout (unit, integrations, fixtures) on project-setup"),
    (21, "Review farm context fetch from Entity Services (PR)"),
    (22, "Review last-7-days InfluxDB telemetry fetch at assessment time"),
    (23, "Integrate Weather Forecast API for 7-day forecast data"),
    (24, "Map AgroMonitoring forecast fields and 7-day rainfall totals"),
    (25, "Convert weather forecast temperatures from Kelvin to Celsius"),
    (26, "Use OpenWeather One Call via AgroMonitoring key for full 7-day rain"),
    (27, "Add OpenMeteo weather provider and env-based provider switching"),
    (28, "Review crop coefficient (Kc) lookup seeding by crop and growth stage"),
    (29, "Review soil moisture threshold lookup table seeding"),
    (30, "Review soil type maximum water per irrigation event lookup"),
    (31, "Review Calculation 1: soil moisture status assessment"),
    (32, "Review Calculation 2: crop water requirement estimation"),
    (33, "Review Calculation 3: soil water balance and moisture projection"),
    (34, "Review Calculation 4: irrigation requirement estimation"),
    (35, "Review Calculation 5 and 6: trend analysis and anomaly detection"),
    (36, "Review storing computed aggregates in Analytics PostgreSQL"),
    (37, "Review analytical context JSON assembly and RabbitMQ publish"),
    (38, "Code review and PR feedback on Analytic_service"),
    (39, "Review weekly scheduled assessment and 24h rolling moisture trigger"),
    (40, "Address PR review comments on the weather forecast integration"),

    # ── Irrigation spec v2 and T-series tickets (mid–late August) ────────
    (41, "Study second version of the AI advisory irrigation specification"),
    (42, "T-00 — Review reference data and lookup tables"),
    (43, "T-01 — Review fetching readings and storing them raw"),
    (44, "T-03 — Review missing-water calculation in millimetres"),
    (45, "T-04 — Review subtracting expected rainfall from irrigation need"),
    (46, "T-05 — Review lost-water accountability (water that never reaches roots)"),
    (47, "T-06 — Review converting millimetres into litres"),
    (48, "T-07 — Review splitting irrigation volume into watering sessions"),
    (49, "T-08 — Review equipment run-time calculation"),
    (50, "T-09a — Review reading the soil's condition"),
    (51, "T-09b — Review decide-whether-to-water-and-when logic"),
    (52, "T-09c — Review confidence score and permission gates"),
    (53, "End-to-end analytics walkthrough and ticket refinement"),

    # ── Aug 21 – Sep 15: irrigation T-09 and related PRs ─────────────────
    (54, "T-09a — Implement reading the soil's condition"),
    (55, "T-09b — Decide whether to water, and when"),
    (56, "Add gross irrigation requirement"),
    (57, "Review T-10 store the assessment and publish it"),
    (58, "Review T-11 make it run (celery-beat scheduler)"),
    (69, "Review irrigation kernel pack refactoring"),

    # ── Sep 16 – Sep 28: LLM-service tickets you opened / owned ──────────
    (59, "L-00 — LLM service scaffolding (FastAPI, Ollama, health check)"),
    (60, "L-01 — LLM project setup and RabbitMQ consumer connection"),
    (61, "L-03 — Qdrant retrieval by domain collection"),
    (62, "L-04 — Load domain knowledge from the repo"),
    (63, "L-05 — Gateway: consume analytics, validate, build state"),
    (64, "L-06 — Context Agent: parse, analyse, retrieval topics"),
    (65, "L-07 — Knowledge Agent: query, search, evaluate evidence"),
    (66, "L-08 — Recommendation message for text, USSD, IVR and email"),
    (67, "L-09 — LangGraph workflow wiring and advisory handoff"),
    (68, "L-10 — Agent 4: confidence gate, delivery and human-in-the-loop"),

    # ── Sep 29 – Oct 10: L-06 message refiner (your commits) ─────────────
    (70, "L-06 — Message refiner: SMS, USSD, IVR, and email"),
    (71, "Address review comments on the LLM message refiner"),

    # ── Oct 13 – Oct 29: Communication service preparation ───────────────
    (72, "Communication service architecture and approach"),
    (73, "Communication service sprint tickets on the Advisory board"),
    (74, "Communication retry and channel delivery design"),
]

# Ticket ids that belong to each delivery phase (so May does not log August work).
PHASES = [
    (date(2026, 5, 5),  date(2026, 5, 31),  [1, 2, 3, 4, 5, 6, 7, 8]),
    (date(2026, 6, 1),  date(2026, 7, 13),  [9, 10, 11, 12, 13, 14, 15, 16, 4, 8]),
    (date(2026, 7, 14), date(2026, 7, 22),  [17, 18, 19, 20, 13, 14]),
    (date(2026, 7, 23), date(2026, 8, 10),  [
        23, 23, 23, 24, 24, 25, 25, 26, 27, 40,   # weather API — your issue
        19, 20, 21, 21, 22, 38, 38, 38,
        28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 39, 39,
    ]),
    (date(2026, 8, 11), date(2026, 8, 20),  [
        41, 41, 41, 53, 53, 38,
        42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52,
    ]),
    (date(2026, 8, 21), date(2026, 9, 4),  [
        42, 43, 50, 51, 54, 54, 38, 4,
    ]),
    (date(2026, 9, 5), date(2026, 9, 15),  [
        54, 55, 55, 55, 56, 56, 51, 57, 38, 69, 4,
    ]),
    (date(2026, 9, 16), date(2026, 9, 28),  [
        59, 59, 60, 66, 66, 63, 64, 65, 67, 68, 61, 62, 58, 38, 4,
    ]),
    # Olivier: L-06 refiner 30 Sep + review fixes 2 Oct; merged L-05 PR #7.
    (date(2026, 9, 29), date(2026, 10, 12),  [
        70, 70, 70, 71, 71, 38, 4,
    ]),
    # Local comm-prep docs from 14 Oct; sprint issues on Advisory board.
    (date(2026, 10, 13), date(2026, 10, 21),  [
        72, 72, 72, 73, 73, 4,
    ]),
    # Approach PDFs 22–26 Oct; retry diagram 28 Oct.
    (date(2026, 10, 22), date(2026, 10, 29),  [
        72, 73, 74, 74, 4,
    ]),
]

STANDUP_TICKET_ID = 4

# Time-entry descriptions (Toggl project name is the ticket title above).
DESCRIPTIONS = {
    1: [
        "Reading Yannick's architecture doc and listing questions for kickoff",
        "Going through the proposed system architecture with the rest of the stack in mind",
        "Notes on how analytics would plug into the ingestion and output flow",
    ],
    2: [
        "Reading the Kumva Insights Notion page on the backend stack",
        "Skimming FastAPI / Influx / RabbitMQ notes and jotting what we actually need",
        "Checking which services already exist vs what analytics still has to own",
    ],
    3: [
        "Intro call with Sagamba, Alexandra and the Kumva team",
        "Kickoff notes — what Kumva wants from the advisory system",
        "Follow-up after the intro session, catching points I missed live",
    ],
    4: [
        "Daily standup",
        "Standup — shared what I am on and blockers",
        "Morning standup with the analytics team",
    ],
    5: [
        "Mental model session on poultry, farms and irrigation",
        "Working through today's domain questions with the group",
        "Writing up what we agreed about how a farm actually waters crops",
    ],
    6: [
        "Doing the mental model exercises from today's session",
        "Going back over yesterday's questions so they stick",
        "Filling in the practical exercises Alexandra posted",
    ],
    7: [
        "Setting up a small FastAPI service locally to get used to the stack",
        "Python practice for the analytics service — routes, settings, tests",
        "Reading FastAPI bits we will need for the assessment pipeline",
    ],
    8: [
        "Reading the backend timeplan and marking what lands on analytics",
        "Checking milestone dates against what we can realistically finish",
        "Aligning my week with the Notion timeplan",
    ],
    9: [
        "Sketching ingestion → processing → output on paper then in the doc",
        "Walking the architecture from telemetry in to a recommendation out",
        "Cleaning up the written flow so Kumva can review it",
    ],
    10: [
        "Listing agent types and who talks to who",
        "Notes on context / retrieval / recommendation agents",
        "Clarifying how the three agents hand state between them",
    ],
    11: [
        "Writing functional requirements per analytics component",
        "Matching each box in the diagram to what it must actually do",
        "Tightening the requirements before we share them",
    ],
    12: [
        "Comparing function-based vs gateway LLM setups — pros/cons",
        "Notes on routing, flexibility and observability for the two options",
        "Drafting the architecture choice so we can discuss it Monday",
    ],
    13: [
        "Building the analytics mermaid flow in mermaid.live",
        "RabbitMQ in, LLM agents, notification out — getting the arrows right",
        "Fixing the diagram after Yannick said evaluate should not fork three ways",
    ],
    14: [
        "Revising the LLM flowchart from the feedback on the call",
        "Moving the evaluate-document arrow to the top of the condition",
        "Checking Thierry's Notion revision against the original sketch",
    ],
    15: [
        "Writing the knowledge ingestion steps for the LLM service",
        "Documenting how the recommendation agent attaches sources",
        "Filling in the structured output: message, confidence, references",
    ],
    16: [
        "Packaging the analytics proposal for the Kumva team to read",
        "Cleaning the Google doc before we send it over",
        "Double-checking the proposal matches what we said on the call",
    ],
    17: [
        "DevOps catch-up on how we would deploy the analytics proposal",
        "Notes from the deployment discussion — what they need from us",
        "Following up on repo access and where the service will live",
    ],
    18: [
        "Sprint planning with Thierry and setting up the GitHub board",
        "Going through tickets we can actually take this sprint",
        "Checking I have access to the analytics repo and project board",
    ],
    19: [
        "Cloning Analytic_service and running the project-setup README locally",
        "Getting env, dependencies and the sample app running",
        "Checking the chore/project-setup branch so I can start from the same baseline",
    ],
    20: [
        "Adding the tests folder layout Thierry asked for",
        "Putting unit / integrations / fixtures in place on project-setup",
        "Pulling the merged tests directory on dev and making sure pytest sees it",
    ],
    21: [
        "Reviewing Noella's PR for farm context from Entity Services",
        "Leaving comments on the farm context fetch",
        "Checking the entity JSON shape against what analytics expects",
    ],
    22: [
        "Reviewing the InfluxDB last-7-days telemetry fetch",
        "Reading through how assessment time pulls the moisture series",
        "Notes on the telemetry query window and tags",
    ],
    23: [
        "Wiring the 7-day weather forecast client into analytics",
        "Hitting AgroMonitoring and mapping the forecast payload",
        "Testing the weather integration with a Kigali lat/lon",
    ],
    24: [
        "Mapping AgroMonitoring fields we need for rainfall totals",
        "Checking we actually get 7 days of rain, not 6",
        "Writing the rainfall sum from the daily forecast blocks",
    ],
    25: [
        "Converting forecast temperatures from Kelvin to Celsius",
        "Fixing units on the weather response after Thierry's comment",
        "Re-testing the forecast after the Kelvin change",
    ],
    26: [
        "Trying OpenWeather One Call through the AgroMonitoring key",
        "Checking the undocumented onecall path for the 7th day of rain",
        "Comparing One Call daily rain vs the old 6-day sum",
    ],
    27: [
        "Adding OpenMeteo as a weather provider behind env flags",
        "Switching WEATHER_PROVIDER locally and confirming the 7-day series",
        "Cleaning the weather client so AgroMonitoring / OpenWeather / OpenMeteo share one shape",
    ],
    28: [
        "Reviewing the crop coefficient (Kc) lookup seed data",
        "Checking Kc rows by crop type and growth stage",
        "Comments on the Kc table PR",
    ],
    29: [
        "Reviewing the soil moisture threshold lookup seed",
        "Checking thresholds per crop and growth stage",
        "Going through Charlotte's lookup table changes",
    ],
    30: [
        "Reviewing max water per irrigation event by soil type",
        "Checking the soil-type lookup against the irrigation spec",
        "Notes on the lookup PR before we merge",
    ],
    31: [
        "Reading Calculation 1 — soil moisture status assessment",
        "Review comments on how we classify too-dry / ok / too-wet",
        "Walking the moisture status logic with the spec open",
    ],
    32: [
        "Reviewing crop water requirement (Calculation 2)",
        "Checking ETc / Kc usage against the irrigation write-up",
        "Comments on the crop water PR",
    ],
    33: [
        "Reviewing soil water balance and moisture projection",
        "Checking the balance formula vs rainfall and irrigation in",
        "Notes on Calculation 3 before standup",
    ],
    34: [
        "Reviewing irrigation requirement estimation",
        "Checking mm-needed against the soil deficit",
        "Comments on Calculation 4",
    ],
    35: [
        "Reviewing trend analysis and the anomaly detection calc",
        "Checking outlier rules so we do not flag normal noise",
        "Notes on Calculations 5 and 6",
    ],
    36: [
        "Reviewing how aggregates land in Analytics Postgres after a run",
        "Checking the write path so we do not lose a failed assessment",
        "Comments on the store-aggregates PR",
    ],
    37: [
        "Reviewing the analytical context JSON we publish to RabbitMQ",
        "Checking domain_tag and payload shape for the LLM service",
        "Notes on the assemble-and-publish PR",
    ],
    38: [
        "PR review on Analytic_service",
        "Going through files changed and leaving comments",
        "Re-reading a PR after the author pushed fixes",
    ],
    39: [
        "Reviewing the weekly assessment trigger",
        "Checking the 24h rolling moisture average for the intermediate run",
        "Notes on when we fire a full vs intermediate assessment",
    ],
    40: [
        "Addressing review comments on the weather forecast PR",
        "Pushing the Kelvin fix and the 7-day rain follow-up",
        "Re-testing after Thierry's last comment on the weather PR",
    ],
    41: [
        "Reading the new irrigation spec (the version at the top of the Google doc)",
        "Comparing spec v2 against what we already built",
        "Highlighting steps that still need tickets",
    ],
    42: [
        "Reviewing T-00 — reference / lookup data",
        "Checking seed tables still match spec v2",
        "Notes on missing lookup rows",
    ],
    43: [
        "Reviewing T-01 — fetch readings and store them raw",
        "Checking we are not transforming telemetry too early",
        "Comments on the raw readings ticket",
    ],
    44: [
        "Reviewing T-03 — missing water in millimetres",
        "Walking the deficit calc with the spec beside it",
        "Notes on units so we stay in mm until the later step",
    ],
    45: [
        "Reviewing T-04 — subtract expected rain",
        "Checking the 7-day rain input from the weather client",
        "Comments on what we do when day 7 is missing",
    ],
    46: [
        "Reviewing T-05 — water that never reaches the roots",
        "Checking efficiency / lost-water accounting against the spec",
        "Notes on T-05 before we estimate litres",
    ],
    47: [
        "Reviewing T-06 — mm to litres",
        "Checking the area conversion so litres are not off by a factor",
        "Comments on the litres ticket",
    ],
    48: [
        "Reviewing T-07 — split into watering sessions",
        "Checking we respect max water per event from the soil table",
        "Notes on session count vs equipment limits",
    ],
    49: [
        "Reviewing T-08 — how long to run the equipment",
        "Checking flow rate vs litres per session",
        "Comments on run-time rounding",
    ],
    50: [
        "Reviewing T-09a — reading the soil's condition",
        "Checking we use the latest moisture plus the 7-day context",
        "Notes on T-09a before the watering decision",
    ],
    51: [
        "Reviewing T-09b — decide whether to water, and when",
        "Walking the decision gates with spec v2",
        "Comments on timing vs rain in the forecast",
    ],
    52: [
        "Reviewing T-09c — confidence and permission gates",
        "Checking we do not recommend irrigation when confidence is low",
        "Notes on who is allowed to act on the recommendation",
    ],
    53: [
        "Going through the end-to-end walkthrough Thierry posted",
        "Listing gaps between the walkthrough and the open tickets",
        "Tidying ticket wording after the walkthrough",
    ],
    54: [
        "Implementing T-09a — reading the soil's condition from the latest moisture",
        "Putting the soil condition logic back on after the revert",
        "Checking T-09a against spec v2 before we decide whether to water",
    ],
    55: [
        "Working on T-09b — decide whether to water, and when",
        "Walking the watering decision gates with the forecast beside the spec",
        "Addressing review comments on the decide-whether-to-water PR",
    ],
    56: [
        "Adding gross irrigation so lost water is in the litres we actually apply",
        "Checking gross vs net irrigation after the efficiency factor",
        "Re-testing the gross irrigation path after the PR comments",
    ],
    57: [
        "Reviewing T-10 — store the assessment and publish it",
        "Checking Charlotte's store-and-publish PR against the RabbitMQ payload",
        "Notes on what we persist vs what we send to the LLM service",
    ],
    58: [
        "Reviewing T-11 — make it run with celery-beat",
        "Checking the weekly and 24h triggers still fire an assessment",
        "Notes on the scheduler PR before it lands on dev",
    ],
    59: [
        "Scaffolding the LLM service — FastAPI, Ollama and a health check",
        "Getting the LLM project to boot locally with the health endpoint green",
        "Closing out L-00 project scaffolding",
    ],
    60: [
        "LLM project setup — connecting as a RabbitMQ consumer of analytics messages",
        "Checking the consume path from analytics into the LLM gateway",
        "Notes on L-01 project setup vs the consumer ticket",
    ],
    61: [
        "Working through Qdrant retrieval by domain collection",
        "Checking we query the right collection for irrigation vs poultry",
        "Notes on L-03 before the knowledge agent search loop",
    ],
    62: [
        "Loading domain knowledge from the repo for the MVP ingest",
        "Checking the markdown/docs we seed into Qdrant",
        "Notes on L-04 ingest so Agent 2 has something to retrieve",
    ],
    63: [
        "Gateway work — consume analytics JSON, validate it, build initial state",
        "Checking the analytics payload still matches what the gateway expects",
        "Notes on L-05 before we hand state to the context agent",
    ],
    64: [
        "Context agent — parse telemetry, detect domain, generate retrieval topics",
        "Checking the topics we send to the knowledge agent",
        "Notes on L-06 after a dry run of the parse step",
    ],
    65: [
        "Knowledge agent — build the query, search, evaluate whether we need more",
        "Checking the refine-query loop does not spin forever",
        "Notes on L-07 evaluate-documents vs the mermaid feedback",
    ],
    66: [
        "Formatting the recommendation for text, USSD, IVR and email",
        "Working on L-08 channel formats so comms can send without rewriting copy",
        "Checking each channel stays inside its length limits",
    ],
    67: [
        "Wiring the LangGraph workflow and the advisory handoff",
        "Checking Agent 1 → 2 → 3 still match the mermaid flow",
        "Notes on L-09 before the confidence gate",
    ],
    68: [
        "Confidence gate, delivery and human-in-the-loop (L-10 / Agent 4)",
        "Checking we do not send a recommendation when confidence is low",
        "Notes on who has to approve before comms delivers it",
    ],
    69: [
        "Reviewing the kernel pack refactor — entity metrics and irrigation pack",
        "Reading the DomainPack contract and registry PRs",
        "Notes on K-1 to K-4 so LLM work sits on a stable analytics kernel",
    ],
    70: [
        "Building L-06 — wording accepted assessments for SMS, USSD, IVR and email",
        "Wiring the message refiner after the gateway hands over a valid assessment",
        "Checking the refiner stays English-only and the channel texts still fit",
    ],
    71: [
        "Addressing review comments on the LLM message refiner",
        "Tightening the refiner tests after the PR notes",
        "Re-checking schemas and the worker handoff after the review",
    ],
    72: [
        "Writing the Communication service approach against the Octan architecture",
        "Drawing context, alert sequence and delivery-state diagrams for Communication",
        "Updating the Google Doc replies from the approach we locked",
    ],
    73: [
        "Opening Sprint 1 and Sprint 2 Communication tickets on the Advisory board",
        "Splitting consume-and-queue from send-and-retry so each issue is one slice",
        "Checking the Sprint Backlog cards still match the approach",
    ],
    74: [
        "Working through SMS, IVR, WhatsApp and email retry versus one-shot send",
        "Writing the retry diagram so Africa's Talking callbacks are not a second SMS",
        "Notes on quiet hours and what failed vs suppressed vs retrying means",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
#  RWANDA WORKING DAYS
#  Presidential Order N° 54/01: except 7 April (Genocide Memorial), a holiday
#  that falls on a weekend is observed on the next working day (Monday).
#  Two consecutive weekend holidays are compensated with one following weekday.
#  Two holidays on the same weekday: the next weekday compensates the second.
# ═══════════════════════════════════════════════════════════════════════════

# (month, day) — Genocide Memorial is flagged so it is never moved.
_RW_FIXED_HOLIDAYS = (
    (1, 1),   # New Year's Day
    (1, 2),   # Day after New Year's Day
    (2, 1),   # National Heroes' Day
    (4, 7),   # Genocide Memorial Day — never substituted
    (5, 1),   # Labour Day
    (7, 1),   # Independence Day
    (8, 15),  # Assumption Day
    (7, 4),   # Liberation Day
    (12, 25), # Christmas Day
    (12, 26), # Boxing Day
)
_RW_GENOCIDE_MEMORIAL = (4, 7)

# Announced each year by the Rwanda Muslims' Association.
_RW_ISLAMIC_HOLIDAYS = {
    2026: (
        date(2026, 3, 20),  # Eid al-Fitr
        date(2026, 5, 27),  # Eid al-Adha
    ),
}

_holiday_cache = {}


def _easter_sunday(year):
    """Anonymous Gregorian computus."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _umuganura(year):
    """Friday of the first week of August (1–7 Aug)."""
    first = date(year, 8, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7)


def _first_weekday_on_or_after(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def rwanda_observed_holidays(year):
    """Observed public-holiday dates for Rwanda in `year` (includes substitutes)."""
    if year in _holiday_cache:
        return _holiday_cache[year]

    genocide = date(year, *_RW_GENOCIDE_MEMORIAL)
    nominal = []
    for month, day in _RW_FIXED_HOLIDAYS:
        if (month, day) != _RW_GENOCIDE_MEMORIAL:
            nominal.append(date(year, month, day))

    easter = _easter_sunday(year)
    nominal.append(easter - timedelta(days=2))  # Good Friday
    nominal.append(easter + timedelta(days=1))  # Easter Monday
    nominal.append(_umuganura(year))
    nominal.extend(_RW_ISLAMIC_HOLIDAYS.get(year, ()))

    counts = Counter(nominal)
    counts[genocide] += 1

    # 7 April stays on 7 April even if it is a weekend — no substitute.
    observed = {genocide}

    def take_weekday(d):
        d = _first_weekday_on_or_after(d)
        while d in observed:
            d = _first_weekday_on_or_after(d + timedelta(days=1))
        observed.add(d)

    for d, n in counts.items():
        if d == genocide:
            if n >= 2 and d.weekday() < 5:
                take_weekday(d + timedelta(days=1))
            continue
        if d.weekday() < 5:
            take_weekday(d)
            if n >= 2:
                take_weekday(d + timedelta(days=1))

    weekend_dates = sorted(d for d in counts if d.weekday() >= 5 and d != genocide)
    clusters = []
    for d in weekend_dates:
        if clusters and d == clusters[-1][-1] + timedelta(days=1):
            clusters[-1].append(d)
        else:
            clusters.append([d])
    for cluster in clusters:
        take_weekday(cluster[-1] + timedelta(days=1))

    _holiday_cache[year] = observed
    return observed


def is_rwanda_workday(d):
    """True for Mon–Fri that is not an observed Rwandan public holiday."""
    if d.weekday() >= 5:
        return False
    return d not in rwanda_observed_holidays(d.year)


# ═══════════════════════════════════════════════════════════════════════════
#  GENERATE TIME ENTRIES
# ═══════════════════════════════════════════════════════════════════════════

def _ids_for_day(d):
    for start, end, ids in PHASES:
        if start <= d <= end:
            return ids
    return [t[0] for t in tickets]


def _fmt_mins(total):
    h, m = divmod(int(total), 60)
    return f"{h:02d}:{m:02d}"


def _pick_description(rng, tid):
    pool = DESCRIPTIONS.get(tid)
    if not pool:
        return next(name for i, name in tickets if i == tid)
    return rng.choice(pool)


def _split_window(start, end, n, rng):
    """Split [start, end) into exactly n uneven chunks (or fewer if the window is short)."""
    total = end - start
    if n <= 0 or total < 18:
        return []
    n = min(n, max(1, total // 22))

    slots = []
    cursor = start
    leftover = total
    for i in range(n):
        pieces_left = n - i
        if pieces_left == 1:
            gap_end = rng.randint(0, min(4, max(0, leftover - 18)))
            dur = leftover - gap_end
        else:
            avg = leftover / pieces_left
            dur = int(round(avg + rng.randint(-12, 12)))
            min_rest = 18 * (pieces_left - 1)
            dur = max(18, min(dur, leftover - min_rest))
            if dur % 5 == 0 and rng.random() < 0.45:
                dur += rng.choice([-2, -1, 1, 2])
                dur = max(18, min(dur, leftover - min_rest))
        if dur < 15:
            break
        slots.append((cursor, cursor + dur, dur))
        cursor += dur
        leftover = end - cursor
        if i < n - 1 and leftover > 22 and rng.random() < 0.35:
            pause = rng.randint(1, 3)
            cursor += pause
            leftover = end - cursor
    return slots


def generate_all_entries():
    """
    Working day ~09:00–17:00 with lunch and standup ~10:30–11:00.
    Each day has 3, 4 or 5 Toggl blocks (standup counts as one). Never more than 5.
    """
    work_days = []
    d = START_DATE
    while d <= END_DATE:
        if is_rwanda_workday(d):
            work_days.append(d)
        d += timedelta(days=1)

    all_rows = []

    for d in work_days:
        day_rng = random.Random(42 + d.toordinal())

        arrive = 9 * 60 + day_rng.randint(0, 14)
        standup_start = 10 * 60 + 30 + day_rng.randint(-6, 6)
        standup_len = day_rng.choice([25, 27, 28, 30, 32, 33, 35])
        lunch_start = 12 * 60 + day_rng.randint(-10, 18)
        lunch_len = day_rng.randint(48, 72)
        leave = 17 * 60 + day_rng.randint(-18, 10)

        standup_start = max(standup_start, arrive + 50)
        standup_end = standup_start + standup_len
        lunch_start = max(lunch_start, standup_end + 25)
        lunch_end = lunch_start + lunch_len
        leave = max(leave, lunch_end + 90)

        # 3 / 4 / 5 blocks for the whole day, including standup.
        n_total = day_rng.choice([3, 3, 4, 4, 4, 5, 5])
        n_work = n_total - 1
        if n_work == 2:
            pre, mid, aft = 1, 0, 1
        elif n_work == 3:
            pre, mid, aft = day_rng.choice([(1, 0, 2), (1, 1, 1)])
        else:
            pre, mid, aft = day_rng.choice([(1, 1, 2), (1, 0, 3), (2, 1, 1)])

        phase_ids = _ids_for_day(d)
        work_ids = [i for i in phase_ids if i != STANDUP_TICKET_ID] or phase_ids

        blocks = [
            _split_window(arrive, standup_start, pre, day_rng),
            [(standup_start, standup_end, standup_len)],
            _split_window(standup_end, lunch_start, mid, day_rng),
            _split_window(lunch_end, leave, aft, day_rng),
        ]

        for b_idx, slots in enumerate(blocks):
            is_standup = b_idx == 1
            for start_m, end_m, dur in slots:
                tid = STANDUP_TICKET_ID if is_standup else day_rng.choice(work_ids)
                all_rows.append({
                    'date':         d.isoformat(),
                    'ticket':       tid,
                    'description':  _pick_description(day_rng, tid),
                    'start':        _fmt_mins(start_m),
                    'end':          _fmt_mins(end_m),
                    'duration_min': dur,
                })

    all_rows.sort(key=lambda r: (r['date'], r['start']))
    return all_rows

# ═══════════════════════════════════════════════════════════════════════════
#  TOGGL 2.0 (FOCUS) API HELPERS
# ═══════════════════════════════════════════════════════════════════════════

API_ROOT = "https://focus.toggl.com/api"
ORG_BASE = f"{API_ROOT}/organizations/{ORGANIZATION_ID}/workspaces/{WORKSPACE_ID}"
WS_BASE  = f"{API_ROOT}/workspaces/{WORKSPACE_ID}"


def _headers():
    return {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}


def _retry_after(r, retry):
    try:
        return int(r.headers.get("Retry-After", ""))
    except ValueError:
        return (2 ** retry) * 5


def _request(method, url, retry=0, **kwargs):
    """HTTP call with backoff on 429/5xx. In CI a long rate-limit wait exits cleanly."""
    try:
        r = requests.request(method, url, headers=_headers(), timeout=30, **kwargs)
    except requests.exceptions.RequestException as e:
        if retry < MAX_RETRIES:
            print(f"   Network error: {e}. Retrying...")
            time.sleep(5 * (retry + 1))
            return _request(method, url, retry + 1, **kwargs)
        raise
    if r.status_code == 429 or r.status_code >= 500:
        wait = _retry_after(r, retry)
        if r.status_code == 429 and os.environ.get("CI") and wait > 120:
            print(f"\n   Toggl rate limit reached. Retry in ~{wait // 60} min; progress is saved.")
            sys.exit(0)
        if retry < MAX_RETRIES:
            print(f"   {r.status_code} from Toggl. Waiting {wait}s...")
            time.sleep(wait)
            return _request(method, url, retry + 1, **kwargs)
    return r


def _json(r):
    body = r.json() if r.content else {}
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _list_all(url, **params):
    """Follow `page` until an empty page (Toggl 2.0 lists have no total count)."""
    items = []
    for page in range(1, 500):
        r = _request("GET", url, params={**params, "page": page, "per_page": 100})
        if r.status_code != 200:
            print(f"   GET {url} failed: {r.status_code} {r.text[:200]}")
            sys.exit(1)
        batch = _json(r)
        if not batch:
            break
        items.extend(batch)
    return items


def test_connection():
    print("Testing connection...")
    if not API_TOKEN:
        print("   TOGGL_API_TOKEN is not set (.env locally, repository secret in Actions).")
        return False
    try:
        r = _request("GET", f"{API_ROOT}/users/me/settings")
    except requests.exceptions.RequestException as e:
        print(f"   Connection error: {e}")
        return False
    if r.status_code == 200:
        current = r.json().get("current_workspace_id")
        print(f"   Authenticated with Toggl 2.0 (current workspace {current}, "
              f"uploading to {WORKSPACE_ID})")
        return True
    if r.status_code in (401, 403):
        print(f"   Authentication failed ({r.status_code}). TOGGL_API_TOKEN must be a "
              f"toggl_sk_ key from Toggl 2.0 profile settings.")
        return False
    print(f"   Unexpected response: {r.status_code} - {r.text[:200]}")
    return False


# ═══════════════════════════════════════════════════════════════════════════
#  EXISTING TIME — generated blocks only fill gaps around it
# ═══════════════════════════════════════════════════════════════════════════

def _mins(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def fetch_busy_minutes(first_day, last_day):
    """Tracked entries per local date as (start_min, end_min); includes earlier uploads."""
    date_from = datetime.combine(first_day, datetime.min.time(), LOCAL_TZ)
    date_to   = datetime.combine(last_day + timedelta(days=1), datetime.min.time(), LOCAL_TZ)
    entries = _list_all(
        f"{ORG_BASE}/time-entries",
        date_from=date_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        date_to=date_to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        include_taskless="true",
    )
    busy = defaultdict(list)
    for e in entries:
        if not e.get("start") or not e.get("duration"):
            continue
        start = datetime.fromisoformat(e["start"].replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        start_m = start.hour * 60 + start.minute
        busy[start.date().isoformat()].append((start_m, start_m + -(-e["duration"] // 60)))
    return busy


def fit_around_busy(day_entries, busy):
    """Drop generated standups and cut work blocks around already-tracked time."""
    pieces = []
    for e in day_entries:
        if e["ticket"] == STANDUP_TICKET_ID:
            continue
        segs = [(_mins(e["start"]), _mins(e["end"]))]
        for b_start, b_end in busy:
            segs = [p for s, en in segs
                    for p in ((s, min(en, b_start)), (max(s, b_end), en))
                    if p[1] > p[0]]
        for s, en in segs:
            if en - s >= MIN_BLOCK_MIN:
                pieces.append({**e, "start": _fmt_mins(s), "end": _fmt_mins(en),
                               "duration_min": en - s})
    while len(pieces) > MAX_BLOCKS_PER_DAY:
        pieces.remove(min(pieces, key=lambda p: p["duration_min"]))
    return sorted(pieces, key=lambda p: p["start"])


# ═══════════════════════════════════════════════════════════════════════════
#  CLIENT, PROJECT & TAG SETUP
# ═══════════════════════════════════════════════════════════════════════════

def load_projects_cache():
    try:
        with open(PROJECTS_CACHE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_projects_cache(cache):
    if DRY_RUN:
        return
    with open(PROJECTS_CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


def _fresh_cache_if_changed(cache):
    """Drop cached ids that belong to another client, layout or workspace."""
    if (cache.get('client_name') != CLIENT_NAME or cache.get('layout') != UPLOAD_LAYOUT
            or str(cache.get('workspace_id')) != str(WORKSPACE_ID)):
        cache = {'client_name': CLIENT_NAME, 'layout': UPLOAD_LAYOUT,
                 'workspace_id': WORKSPACE_ID}
    cache.setdefault('projects', {})
    cache.setdefault('tags', {})
    return cache


def _created_id(r, what):
    if r.status_code in (200, 201):
        return _json(r)['id']
    print(f"   Failed to create {what}: {r.status_code} {r.text[:200]}")
    sys.exit(1)


def get_client_id(cache):
    if cache.get('client_id'):
        return cache['client_id']

    for c in _list_all(f"{WS_BASE}/clients", name=CLIENT_NAME):
        if c.get('name', '').lower() == CLIENT_NAME.lower():
            print(f"   Found existing client: {c['name']} (id={c['id']})")
            cache['client_id'] = c['id']
            save_projects_cache(cache)
            return c['id']

    if DRY_RUN:
        print(f"   [DRY RUN] Would create client: {CLIENT_NAME}")
        return 0
    client_id = _created_id(_request("POST", f"{WS_BASE}/clients", json={"name": CLIENT_NAME}),
                            f"client {CLIENT_NAME}")
    print(f"   Created client: {CLIENT_NAME} (id={client_id})")
    cache['client_id'] = client_id
    save_projects_cache(cache)
    return client_id


def setup_projects(cache, client_id, ticket_ids):
    """One Toggl project per ticket title under the client, only for tickets in use."""
    projects = cache['projects']
    todo = [tid for tid in sorted(ticket_ids) if str(tid) not in projects]
    if not todo:
        print(f"   All {len(ticket_ids)} projects already exist (cached).")
        return projects

    existing = {}
    if client_id:
        for p in _list_all(f"{ORG_BASE}/projects", client_id=client_id):
            if p.get('client_id') == client_id and p.get('name'):
                existing[p['name'].strip().lower()] = p['id']

    names = dict(tickets)
    for tid in todo:
        name = names[tid]
        if name.lower() in existing:
            projects[str(tid)] = existing[name.lower()]
            print(f"   Found [{tid:3d}] {name[:60]}")
        elif DRY_RUN:
            print(f"   [DRY RUN] Would create project [{tid:3d}] {name[:60]}")
            projects[str(tid)] = 0
            continue
        else:
            r = _request("POST", f"{ORG_BASE}/projects",
                         json={"name": name, "client_id": client_id})
            projects[str(tid)] = _created_id(r, f"project '{name}'")
            print(f"   + [{tid:3d}] {name[:60]}")
            time.sleep(DELAY_BETWEEN_REQUESTS)
        save_projects_cache(cache)
    return projects


def get_tag_id(cache, name):
    tags = cache['tags']
    if name in tags:
        return tags[name]
    for t in _list_all(f"{WS_BASE}/tags", name=name):
        if t.get('name', '').lower() == name:
            tags[name] = t['id']
            save_projects_cache(cache)
            return t['id']
    if DRY_RUN:
        print(f"   [DRY RUN] Would create tag: {name}")
        return 0
    tags[name] = _created_id(_request("POST", f"{WS_BASE}/tags", json={"name": name}),
                             f"tag {name}")
    save_projects_cache(cache)
    return tags[name]


def _tag_name(entry):
    desc = entry['description'].lower()
    return "review" if 'review' in desc or 'comment' in desc else "feature"


# ═══════════════════════════════════════════════════════════════════════════
#  TIME ENTRY CREATION
# ═══════════════════════════════════════════════════════════════════════════

def _entry_payload(entry, project_id, tag_id):
    local = datetime.fromisoformat(f"{entry['date']}T{entry['start']}").replace(tzinfo=LOCAL_TZ)
    return {
        "description": entry['description'],
        "start":       local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration":    entry['duration_min'] * 60,
        "project_id":  int(project_id),
        "tag_ids":     [int(tag_id)],
        "type":        "activity",
    }


def upload_day(payloads):
    """Create one day's entries in a single bulk call (taskless, scoped to projects)."""
    url = f"{ORG_BASE}/time-entries/bulk"
    r = _request("POST", url, json=payloads)
    if r.status_code == 400:
        r = _request("POST", url, json={"items": payloads})
    if r.status_code in (200, 201, 204):
        return True
    print(f"\n   Error {r.status_code}: {r.text[:300]}")
    return False


# ═══════════════════════════════════════════════════════════════════════════
#  PROGRESS TRACKING
# ═══════════════════════════════════════════════════════════════════════════

def load_progress():
    try:
        with open(PROGRESS_FILE, 'r') as f:
            data = json.load(f)
        # Ignore progress left by the Toggl Track uploader.
        if data.get("client_name") != CLIENT_NAME or data.get("layout") != UPLOAD_LAYOUT:
            return {}
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_progress(day, day_entries):
    if DRY_RUN:
        return
    payload = {
        "last_completed_date": day,
        "last_completed_end": day_entries[-1]["end"] if day_entries else None,
        "client_name": CLIENT_NAME,
        "layout": UPLOAD_LAYOUT,
    }
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(payload, f)


def is_upload_complete():
    try:
        with open(COMPLETE_FILE, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return (data.get("complete") is True and data.get("client_name") == CLIENT_NAME
            and data.get("layout") == UPLOAD_LAYOUT
            and data.get("end_date") == END_DATE.isoformat())


def mark_upload_complete(total):
    if DRY_RUN:
        return
    with open(COMPLETE_FILE, 'w') as f:
        json.dump({
            "complete": True,
            "client_name": CLIENT_NAME,
            "layout": UPLOAD_LAYOUT,
            "end_date": END_DATE.isoformat(),
            "total_entries": total,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }, f, indent=2)


def _confirm(prompt):
    if os.environ.get("CI"):
        return True
    answer = input(prompt).strip().lower()
    return answer != 'n'


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  TOGGL 2.0 — BULK TIME ENTRY UPLOADER")
    print(f"  {CLIENT_NAME} | {START_DATE.strftime('%b %-d')} – {END_DATE.strftime('%b %-d, %Y')}")
    print("  One project per ticket | fills gaps around tracked meetings")
    print("=" * 65)
    print()

    if is_upload_complete():
        print(f"  Upload through {END_DATE} already complete. Nothing to do.")
        return

    if not test_connection():
        print("\nConnection failed. Please check your credentials and try again.")
        sys.exit(1)

    print("\nGenerating time entries...")
    by_day = defaultdict(list)
    for e in generate_all_entries():
        by_day[e['date']].append(e)
    skipped_holidays = []
    d = START_DATE
    while d <= END_DATE:
        if d.weekday() < 5 and not is_rwanda_workday(d):
            skipped_holidays.append(d)
        d += timedelta(days=1)
    if skipped_holidays:
        print("   Skipped Rwandan holidays: " +
              ", ".join(h.strftime("%a %d %b") for h in skipped_holidays))

    done_through = load_progress().get("last_completed_date", "")
    pending = [day for day in sorted(by_day) if day > done_through]
    if not pending:
        print("\n  Nothing left to upload.")
        mark_upload_complete(0)
        return
    if done_through:
        print(f"   Resuming after {done_through}")

    print("\nReading time already tracked in Toggl...")
    busy = fetch_busy_minutes(date.fromisoformat(pending[0]), date.fromisoformat(pending[-1]))
    plan = {day: fit_around_busy(by_day[day], busy.get(day, [])) for day in pending}
    total = sum(len(v) for v in plan.values())
    total_min = sum(e['duration_min'] for v in plan.values() for e in v)
    existing_min = sum(end - start for day in pending for start, end in busy.get(day, []))
    print(f"   {sum(len(busy.get(day, [])) for day in pending)} tracked entries "
          f"({existing_min / 60:.1f}h) already in Toggl across {len(pending)} working days")
    print(f"   {total} new work blocks ({total_min / 60:.1f}h) fit into the free time")

    print(f"\nSetting up {CLIENT_NAME} client, projects and tags...")
    cache     = _fresh_cache_if_changed(load_projects_cache())
    client_id = get_client_id(cache)
    projects  = setup_projects(cache, client_id, {e['ticket'] for v in plan.values() for e in v})
    tag_ids   = {name: get_tag_id(cache, name)
                 for name in sorted({_tag_name(e) for v in plan.values() for e in v})}

    if DRY_RUN:
        print("\n   DRY RUN MODE — no entries will actually be created.")
    elif not _confirm(f"\n   Upload {total} entries to Toggl? [Y/n]: "):
        print("   Aborted.")
        sys.exit(0)

    uploaded = 0
    for day in pending:
        day_entries = plan[day]
        print(f"\n  {datetime.fromisoformat(day).strftime('%A, %B %d, %Y')}")
        if not day_entries:
            print("   (no free time left — already tracked)")
        for e in day_entries:
            print(f"   #{e['ticket']:3d} | {e['start']}-{e['end']} | {e['description'][:55]}")
        if day_entries and not DRY_RUN:
            payloads = [_entry_payload(e, projects[str(e['ticket'])], tag_ids[_tag_name(e)])
                        for e in day_entries]
            if not upload_day(payloads):
                print(f"\n  Stopped at {day}. Re-run to retry from this day.")
                sys.exit(1)
            uploaded += len(day_entries)
            time.sleep(DELAY_BETWEEN_REQUESTS)
        save_progress(day, day_entries)

    print("\n" + "=" * 65)
    print("  DRY RUN COMPLETE" if DRY_RUN else "  UPLOAD COMPLETE")
    print("=" * 65)
    print(f"  Entries: {total if DRY_RUN else uploaded} across {len(pending)} days "
          f"({total_min / 60:.1f}h)")
    print()
    mark_upload_complete(uploaded)


if __name__ == "__main__":
    main()
