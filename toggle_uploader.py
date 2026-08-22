#!/usr/bin/env python3
"""
=============================================================================
  Toggl Track Bulk Time Entry Uploader
  ─────────────────────────────────────
  Pushes Kumva IoT / analytics time entries (May 5 – Aug 20, 2026)
  to your Toggl account. All entries sit under client "Kumva" and
  project "tickets". Working days only: weekends and Rwandan public
  holidays are skipped (weekend holidays move to the next Monday).

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
PROJECT_NAME             = "tickets"
DELAY_BETWEEN_REQUESTS   = 1.5    # seconds between each API call
BATCH_SIZE               = 50     # entries per batch
DELAY_BETWEEN_BATCHES    = 10     # seconds pause between batches
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

def _ticket_by_id():
    return {tid: desc for tid, desc in tickets}


def _ids_for_day(d):
    for start, end, ids in PHASES:
        if start <= d <= end:
            return ids
    return [t[0] for t in tickets]


def generate_all_entries():
    work_days = []
    d = START_DATE
    while d <= END_DATE:
        if is_rwanda_workday(d):
            work_days.append(d)
        d += timedelta(days=1)

    by_id = _ticket_by_id()
    rng = random.Random(42)

    def make_durations_for_day(day_rng, target):
        durations = []
        remaining = target
        while remaining > 0:
            if remaining >= 60:
                dur = day_rng.choice([30, 45, 60])
            elif remaining >= 45:
                dur = day_rng.choice([30, 45])
            elif remaining >= 30:
                dur = 30
            else:
                if durations:
                    durations[-1] += remaining
                return durations
            durations.append(dur)
            remaining -= dur
        return durations

    def place_entries(durations, target):
        # Morning 09:00–12:00, afternoon 13:00 until 15:00 / 15:30 / 16:00
        morning = (540, 720)
        if target <= 300:
            afternoon = (780, 900)
        elif target <= 330:
            afternoon = (780, 930)
        else:
            afternoon = (780, 960)
        blocks = [morning, afternoon]

        entries = []
        block_idx = 0
        cursor = blocks[0][0]
        for dur in durations:
            placed = False
            while block_idx < len(blocks):
                bstart, bend = blocks[block_idx]
                if cursor < bstart:
                    cursor = bstart
                if cursor + dur <= bend:
                    sh, sm = divmod(cursor, 60)
                    eh, em = divmod(cursor + dur, 60)
                    entries.append((f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}", dur))
                    cursor += dur
                    placed = True
                    break
                block_idx += 1
                if block_idx < len(blocks):
                    cursor = blocks[block_idx][0]
            if not placed:
                sh, sm = divmod(cursor, 60)
                eh, em = divmod(cursor + dur, 60)
                entries.append((f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}", dur))
                cursor += dur
        return entries

    all_rows = []
    for d in work_days:
        target = rng.choice([300, 300, 330, 360, 360])  # 5h, 5.5h, 6h
        durations = make_durations_for_day(rng, target)
        time_slots = place_entries(durations, target)

        phase_ids = _ids_for_day(d)
        day_ids = [rng.choice(phase_ids) for _ in time_slots]

        for (start_t, end_t, dur), tid in zip(time_slots, day_ids):
            all_rows.append({
                'date':         d.isoformat(),
                'ticket':       tid,
                'description':  by_id[tid],
                'start':        start_t,
                'end':          end_t,
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
    """Drop cached ids if they belong to a previous client (e.g. GrantHive)."""
    if cache.get('client_name') != CLIENT_NAME or cache.get('project_name') != PROJECT_NAME:
        return {'client_name': CLIENT_NAME, 'project_name': PROJECT_NAME}
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


def get_or_create_project(cache, client_id):
    """Return the single 'tickets' project ID under the Kumva client."""
    if 'project_id' in cache:
        return cache['project_id']

    r = api_get(f"{API_BASE}/workspaces/{WORKSPACE_ID}/projects")
    if r.status_code == 200:
        for p in r.json():
            name_ok = p.get('name', '').lower() == PROJECT_NAME.lower()
            client_ok = p.get('client_id') == client_id
            if name_ok and client_ok:
                print(f"   Found existing project: {PROJECT_NAME} (id={p['id']})")
                cache['project_id'] = p['id']
                cache['project_name'] = PROJECT_NAME
                save_projects_cache(cache)
                return p['id']

    if DRY_RUN:
        print(f"   [DRY RUN] Would create project: {PROJECT_NAME}")
        cache['project_id'] = 0
        cache['project_name'] = PROJECT_NAME
        return 0

    print(f"   Creating project: {PROJECT_NAME} under '{CLIENT_NAME}'...")
    r = api_post(
        f"{API_BASE}/workspaces/{WORKSPACE_ID}/projects",
        {
            "name":         PROJECT_NAME,
            "workspace_id": int(WORKSPACE_ID),
            "client_id":    client_id,
            "active":       True,
        },
    )
    if r.status_code in (200, 201):
        pid = r.json()['id']
        print(f"   Created project: {PROJECT_NAME} (id={pid})")
        cache['project_id'] = pid
        cache['project_name'] = PROJECT_NAME
        save_projects_cache(cache)
        time.sleep(DELAY_BETWEEN_REQUESTS)
        return pid

    print(f"   Failed to create project '{PROJECT_NAME}': {r.status_code} {r.text[:200]}")
    sys.exit(1)


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
    if 'bug' in desc_lower or 'fix' in desc_lower:
        payload["tags"] = ["bugfix"]
    elif 'review' in desc_lower:
        payload["tags"] = ["review"]
    elif 'mental model' in desc_lower or 'standup' in desc_lower or 'session' in desc_lower:
        payload["tags"] = ["meeting"]
    elif 'architecture' in desc_lower or 'flowchart' in desc_lower or 'mermaid' in desc_lower:
        payload["tags"] = ["design"]
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
        if data.get("client_name") != CLIENT_NAME:
            return -1
        return data.get("last_completed_index", -1)
    except (FileNotFoundError, json.JSONDecodeError):
        return -1


def save_progress(index):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({
            "last_completed_index": index,
            "client_name": CLIENT_NAME,
            "project_name": PROJECT_NAME,
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
    print(f"  Kumva / tickets | {START_DATE.strftime('%b %-d')} – {END_DATE.strftime('%b %-d, %Y')} | 5–6h/day")
    print("  Skips weekends and Rwandan public holidays")
    print("=" * 65)
    print()

    if not test_connection():
        print("\nConnection failed. Please check your credentials and try again.")
        sys.exit(1)

    print(f"\nSetting up {CLIENT_NAME} client and '{PROJECT_NAME}' project...")
    cache     = _fresh_cache_if_client_changed(load_projects_cache())
    client_id = get_or_create_client(cache)
    project_id = get_or_create_project(cache, client_id)
    print(f"   Client '{CLIENT_NAME}' and project '{PROJECT_NAME}' ready.\n")

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
