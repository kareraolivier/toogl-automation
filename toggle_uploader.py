#!/usr/bin/env python3
"""
=============================================================================
  Toggl Track Bulk Time Entry Uploader
  ─────────────────────────────────────
  Pushes Kumva time entries (May 5 – Aug 20, 2026) to Toggl.
  Client "Kumva". Each GitHub-style ticket is its own Toggl project;
  time-entry descriptions are the actual work notes. Days run
  09:00–17:00 with standup around 10:30–11:00. Weekends and Rwandan
  public holidays are skipped.

  RUN:
    python toggle_uploader.py

  RESUME:
    Just re-run the same command — it picks up where it left off.
    If the hourly API limit is hit, it waits automatically and resumes.
=============================================================================
"""

import requests
import time
import json
import random
import sys
import re
import os
from collections import Counter
from datetime import date, timedelta, datetime

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CREDENTIALS                                                             ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
API_TOKEN    = os.environ.get("TOGGL_API_TOKEN", "dd9925ef2f345b6e423d143a24ee183e")
WORKSPACE_ID = "7421598"

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CONFIGURATION                                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
CLIENT_NAME              = "Kumva"
DELAY_BETWEEN_REQUESTS   = 1.0    # seconds between each API call
BATCH_SIZE               = 50     # entries per batch
DELAY_BETWEEN_BATCHES    = 5      # seconds pause between batches
MAX_RETRIES              = 3      # max retries on transient errors
DRY_RUN                  = False  # set True to test without creating entries
TIMEZONE_OFFSET          = "+02:00"  # Kigali = CAT = UTC+2
PROGRESS_FILE            = "toggl_progress.json"
PROJECTS_CACHE_FILE      = "toggl_projects_cache.json"
START_DATE               = date(2026, 5, 5)
END_DATE                 = date(2026, 8, 20)

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


def _fill_block(start, end, rng):
    """Fill a time window with a few uneven chunks so the day does not look generated."""
    total = end - start
    if total < 18:
        return []

    if total < 45:
        n = 1
    elif total < 90:
        n = rng.choice([1, 2, 2])
    elif total < 150:
        n = rng.choice([2, 2, 3])
    else:
        n = rng.choice([2, 3, 3, 4])

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
            dur = int(round(avg + rng.randint(-10, 10)))
            min_rest = 18 * (pieces_left - 1)
            dur = max(18, min(dur, leftover - min_rest))
            # Prefer times that are not always :00 / :30
            if dur % 5 == 0 and rng.random() < 0.45:
                dur += rng.choice([-2, -1, 1, 2])
                dur = max(18, min(dur, leftover - min_rest))
        if dur < 15:
            break
        slots.append((cursor, cursor + dur, dur))
        cursor += dur
        leftover = end - cursor
        if i < n - 1 and leftover > 20 and rng.random() < 0.4:
            pause = rng.randint(1, 3)
            cursor += pause
            leftover = end - cursor
    return slots


def generate_all_entries():
    """
    Working day ~09:00–17:00 with lunch and standup ~10:30–11:00.
    Start, lunch, end and chunk lengths jitter so it reads as a person, not a script.
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

        arrive = 9 * 60 + day_rng.randint(0, 14)                 # 09:00–09:14
        standup_start = 10 * 60 + 30 + day_rng.randint(-6, 6)    # 10:24–10:36
        standup_len = day_rng.choice([25, 27, 28, 30, 32, 33, 35])
        standup_end = standup_start + standup_len
        lunch_start = 12 * 60 + day_rng.randint(-10, 18)         # 11:50–12:18
        lunch_end = lunch_start + day_rng.randint(48, 72)        # 48–72 min
        leave = 17 * 60 + day_rng.randint(-18, 10)               # 16:42–17:10

        # Keep the day in a sensible order.
        standup_start = max(standup_start, arrive + 50)
        standup_end = standup_start + standup_len
        lunch_start = max(lunch_start, standup_end + 25)
        lunch_end = lunch_start + (lunch_end - lunch_start)
        leave = max(leave, lunch_end + 90)

        phase_ids = _ids_for_day(d)
        work_ids = [i for i in phase_ids if i != STANDUP_TICKET_ID] or phase_ids

        blocks = [
            _fill_block(arrive, standup_start, day_rng),
            [(standup_start, standup_end, standup_len)],
            _fill_block(standup_end, lunch_start, day_rng),
            _fill_block(lunch_end, leave, day_rng),
        ]

        for b_idx, slots in enumerate(blocks):
            is_standup = b_idx == 1
            for start_m, end_m, dur in slots:
                if is_standup:
                    tid = STANDUP_TICKET_ID
                else:
                    tid = day_rng.choice(work_ids)
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
#  TOGGL API HELPERS
# ═══════════════════════════════════════════════════════════════════════════

API_BASE = "https://api.track.toggl.com/api/v9"


def get_auth():
    return (API_TOKEN, "api_token")


def wait_for_quota(response_text):
    """Parse reset seconds from a 402 response. In CI: exit cleanly. Locally: sleep."""
    match = re.search(r'reset in (\d+) seconds', response_text)
    wait  = int(match.group(1)) + 5 if match else 3600

    if os.environ.get("CI"):
        print(f"\n   Hourly API limit reached. Quota resets in ~{wait}s. "
              f"Exiting — next scheduled run will resume automatically.")
        sys.exit(0)

    resume_at = datetime.now() + timedelta(seconds=wait)
    print(f"\n   ⏳ Hourly API limit reached. Waiting {wait}s "
          f"(until ~{resume_at.strftime('%H:%M:%S')})...")
    time.sleep(wait)
    print("   ▶️  Quota reset — resuming.\n")


def api_get(url, **kwargs):
    """GET with auto-wait on 402."""
    while True:
        r = requests.get(url, auth=get_auth(), timeout=15, **kwargs)
        if r.status_code == 402:
            wait_for_quota(r.text)
            continue
        return r


def api_post(url, payload):
    """POST with auto-wait on 402."""
    while True:
        r = requests.post(url, json=payload, auth=get_auth(), timeout=15)
        if r.status_code == 402:
            wait_for_quota(r.text)
            continue
        return r


def test_connection():
    print("Testing connection...")
    try:
        r = api_get(f"{API_BASE}/me")
        if r.status_code == 200:
            user = r.json()
            print(f"   Authenticated as: {user.get('fullname', user.get('email', 'Unknown'))}")
            print(f"   Email: {user.get('email', 'N/A')}")
            return True
        elif r.status_code == 403:
            print("   Authentication failed. Check your API token.")
            return False
        else:
            print(f"   Unexpected response: {r.status_code} - {r.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"   Connection error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  CLIENT & PROJECT SETUP
# ═══════════════════════════════════════════════════════════════════════════

def load_projects_cache():
    try:
        with open(PROJECTS_CACHE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_projects_cache(cache):
    with open(PROJECTS_CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


def _fresh_cache_if_client_changed(cache):
    """Drop cached ids unless they are Kumva + one Toggl project per ticket."""
    if cache.get('client_name') != CLIENT_NAME or cache.get('layout') != 'per-ticket':
        fresh = {'client_name': CLIENT_NAME, 'layout': 'per-ticket', 'projects': {}}
        if cache.get('client_name') == CLIENT_NAME and 'client_id' in cache:
            fresh['client_id'] = cache['client_id']
        return fresh
    cache.setdefault('projects', {})
    return cache


def get_or_create_client(cache):
    """Return the Kumva client ID, creating it if needed."""
    if 'client_id' in cache:
        return cache['client_id']

    r = api_get(f"{API_BASE}/workspaces/{WORKSPACE_ID}/clients")
    if r.status_code == 200:
        for c in r.json():
            if c.get('name', '').lower() == CLIENT_NAME.lower():
                print(f"   Found existing client: {CLIENT_NAME} (id={c['id']})")
                cache['client_id'] = c['id']
                cache['client_name'] = CLIENT_NAME
                save_projects_cache(cache)
                return c['id']

    print(f"   Creating client: {CLIENT_NAME}...")
    r = api_post(
        f"{API_BASE}/workspaces/{WORKSPACE_ID}/clients",
        {"name": CLIENT_NAME, "workspace_id": int(WORKSPACE_ID)},
    )
    if r.status_code in (200, 201):
        client_id = r.json()['id']
        print(f"   Created client: {CLIENT_NAME} (id={client_id})")
        cache['client_id'] = client_id
        cache['client_name'] = CLIENT_NAME
        save_projects_cache(cache)
        time.sleep(DELAY_BETWEEN_REQUESTS)
        return client_id

    print(f"   Failed to create client: {r.status_code} {r.text[:200]}")
    sys.exit(1)


def setup_projects(cache, client_id):
    """Create one Toggl project per ticket title under the Kumva client."""
    projects = cache.get('projects', {})
    existing_by_name = {}
    r = api_get(f"{API_BASE}/workspaces/{WORKSPACE_ID}/projects")
    if r.status_code == 200:
        for p in r.json():
            if p.get('client_id') == client_id and p.get('name'):
                existing_by_name[p['name'].lower()] = p['id']

    todo = [(tid, name) for tid, name in tickets if str(tid) not in projects]
    if not todo:
        print(f"   All {len(tickets)} projects already exist (cached).")
        return projects

    print(f"   Creating {len(todo)} missing projects under '{CLIENT_NAME}'...")
    for tid, name in todo:
        if name.lower() in existing_by_name:
            projects[str(tid)] = existing_by_name[name.lower()]
            cache['projects'] = projects
            cache['layout'] = 'per-ticket'
            save_projects_cache(cache)
            print(f"   Found [{tid:3d}] {name[:60]}")
            continue

        if DRY_RUN:
            print(f"   [DRY RUN] Would create project: {name}")
            projects[str(tid)] = 0
            continue

        r = api_post(
            f"{API_BASE}/workspaces/{WORKSPACE_ID}/projects",
            {
                "name":         name,
                "workspace_id": int(WORKSPACE_ID),
                "client_id":    client_id,
                "active":       True,
            },
        )
        if r.status_code in (200, 201):
            pid = r.json()['id']
            projects[str(tid)] = pid
            cache['projects'] = projects
            cache['layout'] = 'per-ticket'
            save_projects_cache(cache)
            print(f"   + [{tid:3d}] {name[:60]}")
        else:
            print(f"   Failed to create project '{name}': {r.status_code} {r.text[:200]}")
            cache['projects'] = projects
            save_projects_cache(cache)
            sys.exit(1)

        time.sleep(DELAY_BETWEEN_REQUESTS)

    cache['projects'] = projects
    cache['layout'] = 'per-ticket'
    save_projects_cache(cache)
    return projects


# ═══════════════════════════════════════════════════════════════════════════
#  TIME ENTRY CREATION
# ═══════════════════════════════════════════════════════════════════════════

def create_time_entry(entry, project_id, retry_count=0):
    start_dt         = f"{entry['date']}T{entry['start']}:00{TIMEZONE_OFFSET}"
    duration_seconds = entry['duration_min'] * 60
    description      = entry['description']

    payload = {
        "description":   description,
        "start":         start_dt,
        "duration":      duration_seconds,
        "created_with":  "toggl_bulk_uploader",
        "workspace_id":  int(WORKSPACE_ID),
        "project_id":    int(project_id),
    }

    desc_lower = description.lower()
    if entry.get('ticket') == STANDUP_TICKET_ID or 'standup' in desc_lower:
        payload["tags"] = ["meeting"]
    elif 'review' in desc_lower or 'comment' in desc_lower:
        payload["tags"] = ["review"]
    else:
        payload["tags"] = ["feature"]

    if DRY_RUN:
        print(f"   [DRY RUN] {description[:50]} | {entry['date']} {entry['start']}-{entry['end']}")
        return True

    try:
        r = api_post(f"{API_BASE}/workspaces/{WORKSPACE_ID}/time_entries", payload)

        if r.status_code in (200, 201):
            return True
        elif r.status_code == 429:
            if retry_count < MAX_RETRIES:
                wait = (2 ** retry_count) * 2 + random.uniform(0, 1)
                print(f"   Rate limited (429). Waiting {wait:.0f}s...")
                time.sleep(wait)
                return create_time_entry(entry, project_id, retry_count + 1)
            return False
        elif r.status_code == 403:
            print(f"   Forbidden (403). Check workspace ID and permissions.")
            print(f"   Response: {r.text[:200]}")
            return False
        else:
            print(f"   Error {r.status_code}: {r.text[:200]}")
            if retry_count < MAX_RETRIES:
                time.sleep((2 ** retry_count) + random.uniform(0, 1))
                return create_time_entry(entry, project_id, retry_count + 1)
            return False

    except requests.exceptions.RequestException as e:
        print(f"   Network error: {e}")
        if retry_count < MAX_RETRIES:
            time.sleep(5)
            return create_time_entry(entry, project_id, retry_count + 1)
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  PROGRESS TRACKING
# ═══════════════════════════════════════════════════════════════════════════

def load_progress():
    try:
        with open(PROGRESS_FILE, 'r') as f:
            data = json.load(f)
        # Ignore leftover GrantHive progress.
        if data.get("client_name") != CLIENT_NAME or data.get("layout") != "per-ticket":
            return -1
        return data.get("last_completed_index", -1)
    except (FileNotFoundError, json.JSONDecodeError):
        return -1


def save_progress(index):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({
            "last_completed_index": index,
            "client_name": CLIENT_NAME,
            "layout": "per-ticket",
        }, f)


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
    print("  TOGGL TRACK — BULK TIME ENTRY UPLOADER")
    print(f"  Kumva | {START_DATE.strftime('%b %-d')} – {END_DATE.strftime('%b %-d, %Y')} | ~09:00–17:00")
    print("  One Toggl project per ticket | standup ~10:30 | skips weekends/holidays")
    print("=" * 65)
    print()

    if not test_connection():
        print("\nConnection failed. Please check your credentials and try again.")
        sys.exit(1)

    print(f"\nSetting up {CLIENT_NAME} client and per-ticket projects...")
    cache     = _fresh_cache_if_client_changed(load_projects_cache())
    client_id = get_or_create_client(cache)
    projects  = setup_projects(cache, client_id)
    print(f"   {len(projects)} projects ready.\n")

    print("Generating time entries...")
    entries = generate_all_entries()
    days = len(set(e['date'] for e in entries))
    total_min = sum(e['duration_min'] for e in entries)
    skipped_holidays = []
    d = START_DATE
    while d <= END_DATE:
        if d.weekday() < 5 and not is_rwanda_workday(d):
            skipped_holidays.append(d)
        d += timedelta(days=1)
    print(f"   {len(entries)} entries across {days} working days "
          f"({total_min / 60:.1f} hours total, ~{total_min / 60 / days:.1f}h/day)")
    if skipped_holidays:
        print("   Skipped Rwandan holidays: " +
              ", ".join(h.strftime("%a %d %b") for h in skipped_holidays))

    last_done  = load_progress()
    start_from = last_done + 1

    if start_from > 0:
        print(f"\nResuming from entry {start_from + 1}/{len(entries)} "
              f"(previously completed {start_from})")
        if not _confirm("   Continue? [Y/n]: "):
            start_from = 0
            save_progress(-1)
    else:
        print(f"\nReady to upload {len(entries)} time entries to Toggl.")
        if DRY_RUN:
            print("   DRY RUN MODE — no entries will actually be created.")
        if not _confirm("   Proceed? [Y/n]: "):
            print("   Aborted.")
            sys.exit(0)

    print()
    success_count = 0
    fail_count    = 0
    current_date  = ""

    for i in range(start_from, len(entries)):
        entry     = entries[i]
        batch_num = (i // BATCH_SIZE) + 1

        if entry['date'] != current_date:
            current_date = entry['date']
            dt = datetime.fromisoformat(current_date)
            print(f"\n  {dt.strftime('%A, %B %d, %Y')}")

        pct        = ((i + 1) / len(entries)) * 100
        desc_short = entry['description'][:45] + "..." \
                     if len(entry['description']) > 45 else entry['description']
        print(f"   [{i+1:3d}/{len(entries)}] ({pct:5.1f}%) #{entry['ticket']:3d} | "
              f"{entry['start']}-{entry['end']} | {desc_short}", end="", flush=True)

        project_id = projects.get(str(entry['ticket']))
        if not project_id:
            print(" FAIL (missing project)")
            fail_count += 1
            continue

        ok = create_time_entry(entry, project_id)

        if ok:
            success_count += 1
            print(" OK")
            save_progress(i)
        else:
            fail_count += 1
            print(" FAIL")

        time.sleep(DELAY_BETWEEN_REQUESTS)

        if (i + 1) % BATCH_SIZE == 0 and i + 1 < len(entries):
            print(f"\n   Batch {batch_num} complete. Pausing {DELAY_BETWEEN_BATCHES}s...")
            time.sleep(DELAY_BETWEEN_BATCHES)

    print("\n" + "=" * 65)
    print("  UPLOAD COMPLETE")
    print("=" * 65)
    print(f"  Successful: {success_count}")
    print(f"  Failed:     {fail_count}")
    print(f"  Total:      {success_count + fail_count}/{len(entries)}")
    print()

    if fail_count > 0:
        print("  Some entries failed. Re-run to retry from where it stopped.")
    else:
        try:
            os.remove(PROGRESS_FILE)
        except OSError:
            pass
        print("  All entries uploaded successfully!")
    print()


if __name__ == "__main__":
    main()
