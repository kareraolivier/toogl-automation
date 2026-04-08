#!/usr/bin/env python3
"""
=============================================================================
  Toggl Track Bulk Time Entry Uploader
  ─────────────────────────────────────
  Pushes all 600 time entries (Jan 5 – Mar 20, 2026) to your Toggl account.
  Each entry is linked to a per-ticket project under the "GrantHive" client.

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
from datetime import date, timedelta, datetime, timezone

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CREDENTIALS                                                             ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
API_TOKEN    = os.environ.get("TOGGL_API_TOKEN", "2f51e545b6e888bb1a14aa62a05185a0")
WORKSPACE_ID = "21314015"

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CONFIGURATION                                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
GRANTHIVE_CLIENT_NAME    = "GrantHive"
DELAY_BETWEEN_REQUESTS   = 1.5    # seconds between each API call
BATCH_SIZE               = 50     # entries per batch
DELAY_BETWEEN_BATCHES    = 10     # seconds pause between batches
MAX_RETRIES              = 3      # max retries on transient errors
DRY_RUN                  = False  # set True to test without creating entries
TIMEZONE_OFFSET          = "+02:00"  # Kigali = CAT = UTC+2
PROGRESS_FILE            = "toggl_progress.json"
PROJECTS_CACHE_FILE      = "toggl_projects_cache.json"

# ═══════════════════════════════════════════════════════════════════════════
#  TICKET DATA
# ═══════════════════════════════════════════════════════════════════════════

tickets = [
    (1,   "Enhance create request form"),
    (2,   "Verify if the user has paid before allowing them to create a project"),
    (3,   "Contact information revealing for Seeker"),
    (4,   "Contact information revealing for Expert"),
    (5,   "Seeker gets notified when expert makes payment"),
    (6,   "Expert pay contact fee"),
    (7,   "Limit projects for free users"),
    (8,   "Open and edit a project"),
    (9,   "View existing projects"),
    (10,  "Restrict only grants CTAs ('Save' and 'Create Request') to only seeker accounts"),
    (11,  "BUG: Expert details (expertise, location, experience) not specified on expert dashboard"),
    (12,  "Seeker should be able to accept or reject the expert"),
    (13,  "Confirm 'application withdrawal' button is not visible"),
    (14,  "Creating Request Bug"),
    (15,  "Fixing Expert Rejection Error"),
    (16,  "The admin can't change the roles"),
    (17,  "Find Grants with GrantGPT fetching issue"),
    (18,  "Email Notification for Upcoming Grant Deadline"),
    (19,  "Missing 'Submit Offer' Button in Expert Requests Detail View"),
    (20,  "Grant and Project Field Inconsistencies"),
    (21,  "Grant and Project Field Inconsistencies (cont.)"),
    (22,  "(Expert) View NDA"),
    (23,  "(Seeker) Filter requests"),
    (24,  "(All) Show pop up after updating seekers, experts or admin's profile"),
    (25,  "(Seeker) Refactor the side bar"),
    (26,  "Missing 'Apply' button on the detailed request page"),
    (27,  "(Seeker) Save grants to specific projects"),
    (28,  "Seeker view NDA page"),
    (29,  "Close request #64"),
    (30,  "Deactivate projects when seeker subscription ended #82"),
    (31,  "Pricing and subscriptions not displaying on billing page for Free users #84"),
    (32,  "Displaying the number of matched grants on project card #86"),
    (33,  "Access more actions via the 3-dots menu #44"),
    (34,  "Remove .env file from git tracking system #14"),
    (35,  "Matched Grants based on Project Info #57"),
    (36,  "Bug: pricing modal not working for unauthenticated user #75"),
    (37,  "Creating a payment webhook listener #59"),
    (38,  "Creating a payment webhook listener #59 (cont.)"),
    (39,  "Create a Project #56"),
    (40,  "Frontend integration of project subscription #71"),
    (41,  "Pop up remain open after successful submission #68"),
    (42,  "Project Subscription checkout endpoint #70"),
    (43,  "Getting Available Products (plans) from stripe #69"),
    (44,  "Correct Spinner Behavior on Accept/Reject Actions #67"),
    (45,  "Update seekers dashboard to avoid displaying stale data after profile update #31"),
    (46,  "Matched Grants not showing in The Matched Tab #3"),
    (47,  "Integrate Payment with frontend #60 / Grant Supabase access #21"),
    (48,  "Quick actions cards have to appear clickable #10"),
    (49,  "Profile API endpoint Check only authenticated, not permissions #18"),
    (50,  "Privacy page overflow issue #13"),
    (51,  "Reset Password Bug #7"),
    (52,  "Creating Expert Account Bug #6"),
    (53,  "Remove left filters on experts active requests #33"),
    (54,  "Admin metrics cards contain no information #11"),
    (55,  "User should not access log in page when already logged in #8"),
    (56,  "BUG: Settings page shows profile page instead #9"),
    (57,  "Creating Checkout endpoint on stripe #58"),
    (58,  "View request's details button directs to not found page #20"),
    (59,  "Feat: Add ESLint and Prettier and set up CI/CD #38"),
    (60,  "Create an .env.example file #37"),
    (61,  "In-App Alert Notification for Upcoming Grant Deadline #25"),
    (62,  "(All) Create specific request - Add and Pre-fill Grant Title and Link #149"),
    (63,  "(All) Refactor specific request creation form #157"),
    (64,  "(All) Refactor design of the project page #136"),
    (65,  "Refactoring columns with different languages #160"),
    (66,  "(All) Edit request #146"),
    (67,  "(Seeker) Refactor sign up journey incl. personal info, project info, matched grants #130"),
    (68,  "Connect grants_wide_v2 to the granthive.app frontend"),
    (69,  "(Expert) Fetch matched grants #122"),
    (70,  "(All) Direct user to matched grants when clicking 'View grants' on project overview #131"),
    (71,  "(All) Add Hamburger (Edit and Delete) Menu to Project Overview #142"),
    (72,  "(All) View all grants by clicking 'Grants' button in top navigation #126"),
    (73,  "(All) Add loaders for pages and actions #134"),
    (74,  "(All) Display updated number of matched grants on project overview #132"),
    (75,  "(Seeker) Display updated number of matched grants on dashboard #143"),
    (76,  "(Expert) Hide expert's own support requests from available requests #147"),
    (77,  "(All) Update sidebar #141"),
    (78,  "Update location taxonomy #168"),
    (79,  "Creating constants for all table names #158"),
    (80,  "Admin Panel - Document Processing Branding Update #177"),
    (81,  "Admin Panel - API Keys Branding Update #179"),
    (82,  "Admin UI Changes #191"),
    (83,  "Admin Panel - Document Sets Branding Update #174"),
    (84,  "Centralizing supabase fetching #159"),
    (85,  "Sign Up & Sign In page's Brand Update #170"),
    (86,  "Consistent font Update #183"),
    (87,  "Changing filtering location logic #166"),
    (88,  "SSO implementation to onyx #184"),
    (89,  "Side bar branding Update #172"),
    (90,  "Centralized authentication #155"),
    (91,  "Fixing React critical vulnerability #164"),
    (92,  "Fixing signup popup when clicking grants #165"),
    (93,  "Supabase Branching (Split Environments) #167"),
    (94,  "Interactive Elements Branding Update #181"),
    (95,  "Admin Panel - Slack Bots Branding Update #175"),
    (96,  "Admin Panel - Slack Bots Branding Update #175 (cont.)"),
    (97,  "Admin blue Background bug #189"),
    (98,  "Automatic Upstream synchronization #154"),
    (99,  "Navigation Menus Branding Update #180"),
    (100, "Update Onyx #190"),
    (101, "Implement CI/CD Workflow for Automated VPS Deployment #200"),
]

# ═══════════════════════════════════════════════════════════════════════════
#  GENERATE TIME ENTRIES
# ═══════════════════════════════════════════════════════════════════════════

def generate_all_entries():
    start_date = date(2026, 1, 5)
    end_date   = date(2026, 3, 20)
    work_days  = []
    d = start_date
    while d <= end_date:
        if d.weekday() < 5:
            work_days.append(d)
        d += timedelta(days=1)

    random.seed(42)

    def make_durations_for_day(rng, target=480):
        durations = []
        remaining = target
        while remaining > 0:
            if remaining >= 60:
                dur = rng.choice([30, 45, 60])
            elif remaining >= 45:
                dur = rng.choice([30, 45])
            elif remaining >= 30:
                dur = 30
            elif remaining >= 15:
                if durations:
                    durations[-1] += remaining
                return durations
            else:
                if durations:
                    durations[-1] += remaining
                return durations
            durations.append(dur)
            remaining -= dur
        return durations

    def place_entries(durations, overtime=False):
        if overtime:
            blocks = [(540, 780), (840, 1200)]
        else:
            blocks = [(540, 780), (840, 1080)]
        entries  = []
        block_idx = 0
        cursor    = blocks[0][0]
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
                else:
                    block_idx += 1
                    if block_idx < len(blocks):
                        cursor = blocks[block_idx][0]
            if not placed:
                sh, sm = divmod(cursor, 60)
                eh, em = divmod(cursor + dur, 60)
                entries.append((f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}", dur))
                cursor += dur
        return entries

    entries_pool = []
    for tid, desc in tickets:
        repeats = random.choice([1, 2, 2, 3])
        for _ in range(repeats):
            entries_pool.append((tid, desc))
    random.shuffle(entries_pool)

    day_tickets = {d: [] for d in work_days}
    idx = 0
    for d in work_days:
        n = random.randint(4, 6)
        for _ in range(n):
            if idx < len(entries_pool):
                day_tickets[d].append(entries_pool[idx])
                idx += 1
            else:
                day_tickets[d].append(random.choice(tickets))
    while idx < len(entries_pool):
        d = random.choice(work_days)
        day_tickets[d].append(entries_pool[idx])
        idx += 1

    rng      = random.Random(99)
    all_rows = []

    for d in work_days:
        overtime  = rng.random() < 0.12
        target    = random.choice([480, 480, 480, 510, 540]) if overtime else 480
        durations = make_durations_for_day(rng, target)
        time_slots = place_entries(durations, overtime)
        tix = day_tickets[d]
        for i, (start_t, end_t, dur) in enumerate(time_slots):
            ticket = tix[i % len(tix)]
            all_rows.append({
                'date':         d.isoformat(),
                'ticket':       ticket[0],
                'description':  ticket[1],
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


def get_or_create_client(cache):
    """Return the GrantHive client ID, creating it if needed."""
    if 'client_id' in cache:
        return cache['client_id']

    # Check if client already exists
    r = api_get(f"{API_BASE}/workspaces/{WORKSPACE_ID}/clients")
    if r.status_code == 200:
        for c in r.json():
            if c.get('name', '').lower() == GRANTHIVE_CLIENT_NAME.lower():
                print(f"   Found existing client: {GRANTHIVE_CLIENT_NAME} (id={c['id']})")
                cache['client_id'] = c['id']
                save_projects_cache(cache)
                return c['id']

    # Create client
    print(f"   Creating client: {GRANTHIVE_CLIENT_NAME}...")
    r = api_post(
        f"{API_BASE}/workspaces/{WORKSPACE_ID}/clients",
        {"name": GRANTHIVE_CLIENT_NAME, "workspace_id": int(WORKSPACE_ID)},
    )
    if r.status_code in (200, 201):
        client_id = r.json()['id']
        print(f"   Created client: {GRANTHIVE_CLIENT_NAME} (id={client_id})")
        cache['client_id'] = client_id
        save_projects_cache(cache)
        time.sleep(DELAY_BETWEEN_REQUESTS)
        return client_id
    else:
        print(f"   Failed to create client: {r.status_code} {r.text[:200]}")
        sys.exit(1)


def setup_projects(cache, client_id):
    """Create one Toggl project per unique ticket, return {ticket_id: project_id}."""
    projects = cache.get('projects', {})
    todo = [(tid, desc) for tid, desc in tickets if str(tid) not in projects]

    if not todo:
        print(f"   All {len(tickets)} projects already exist (cached).")
        return projects

    print(f"   Creating {len(todo)} missing projects under '{GRANTHIVE_CLIENT_NAME}'...")
    for tid, desc in todo:
        project_name = f"#{desc}"
        if DRY_RUN:
            print(f"   [DRY RUN] Would create project: {project_name}")
            projects[str(tid)] = 0
            continue

        r = api_post(
            f"{API_BASE}/workspaces/{WORKSPACE_ID}/projects",
            {
                "name":         project_name,
                "workspace_id": int(WORKSPACE_ID),
                "client_id":    client_id,
                "active":       True,
            },
        )
        if r.status_code in (200, 201):
            pid = r.json()['id']
            projects[str(tid)] = pid
            cache['projects'] = projects
            save_projects_cache(cache)
            print(f"   + [{tid:3d}] {project_name[:60]}")
        else:
            print(f"   Failed to create project '{project_name}': {r.status_code} {r.text[:200]}")
            # Save progress and exit so resume works
            cache['projects'] = projects
            save_projects_cache(cache)
            sys.exit(1)

        time.sleep(DELAY_BETWEEN_REQUESTS)

    cache['projects'] = projects
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

    # Tags based on ticket type
    desc_lower = description.lower()
    if 'bug' in desc_lower or 'fix' in desc_lower:
        payload["tags"] = ["bugfix"]
    elif 'refactor' in desc_lower:
        payload["tags"] = ["refactor"]
    elif 'branding' in desc_lower or 'update' in desc_lower:
        payload["tags"] = ["ui-update"]
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
            return json.load(f).get("last_completed_index", -1)
    except (FileNotFoundError, json.JSONDecodeError):
        return -1


def save_progress(index):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({"last_completed_index": index}, f)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  TOGGL TRACK — BULK TIME ENTRY UPLOADER")
    print("  600 entries | Jan 5 – Mar 20, 2026 | 8h/day")
    print("  Projects linked to GrantHive client")
    print("=" * 65)
    print()

    if not test_connection():
        print("\nConnection failed. Please check your credentials and try again.")
        sys.exit(1)

    # ── Set up client & projects ──
    print("\nSetting up GrantHive client and projects...")
    cache     = load_projects_cache()
    client_id = get_or_create_client(cache)
    projects  = setup_projects(cache, client_id)
    print(f"   {len(projects)} projects ready.\n")

    # ── Generate entries ──
    print("Generating time entries...")
    entries = generate_all_entries()
    print(f"   {len(entries)} entries across {len(set(e['date'] for e in entries))} working days")

    # ── Check for resume ──
    last_done  = load_progress()
    start_from = last_done + 1

    if start_from > 0:
        print(f"\nResuming from entry {start_from + 1}/{len(entries)} "
              f"(previously completed {start_from})")
        confirm = input("   Continue? [Y/n]: ").strip().lower()
        if confirm == 'n':
            start_from = 0
            save_progress(-1)
    else:
        print(f"\nReady to upload {len(entries)} time entries to Toggl.")
        if DRY_RUN:
            print("   DRY RUN MODE — no entries will actually be created.")
        confirm = input("   Proceed? [Y/n]: ").strip().lower()
        if confirm == 'n':
            print("   Aborted.")
            sys.exit(0)

    # ── Upload loop ──
    print()
    success_count = 0
    fail_count    = 0
    current_date  = ""

    for i in range(start_from, len(entries)):
        entry      = entries[i]
        project_id = projects.get(str(entry['ticket']))
        batch_num  = (i // BATCH_SIZE) + 1

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

    # ── Summary ──
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
            import os
            os.remove(PROGRESS_FILE)
        except OSError:
            pass
        print("  All entries uploaded successfully!")
    print()


if __name__ == "__main__":
    main()
