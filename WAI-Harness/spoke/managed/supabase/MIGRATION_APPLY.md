# Applying the activity_events Migration

No Supabase credentials were found in the environment at migration creation time.
Run one of the commands below when credentials are available.

## Project ref

`mnpcnizbwbfhkjcgiwxa`  (read from `supabase/.temp/project-ref`)

## Option A — Supabase CLI (recommended)

```bash
# From repo root. Requires SUPABASE_ACCESS_TOKEN in env or ~/.config/supabase/access-token.
cd /home/mario/projects/wheelwright/framework
supabase db push
```

## Option B — psql direct

```bash
psql "$DATABASE_URL" -f supabase/migrations/20260529000000_create_activity_events.sql
```

## Option C — REST API (manual, no CLI)

Set SUPABASE_REST and SUPABASE_KEY, then:

```bash
python3 - <<'EOF'
import os, json, urllib.request
url = os.environ["SUPABASE_REST"].rstrip("/") + "/rpc/exec_sql"
sql = open("supabase/migrations/20260529000000_create_activity_events.sql").read()
req = urllib.request.Request(
    url,
    data=json.dumps({"query": sql}).encode(),
    headers={
        "apikey": os.environ["SUPABASE_KEY"],
        "Authorization": f"Bearer {os.environ['SUPABASE_KEY']}",
        "Content-Type": "application/json",
    },
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    print(r.status, r.read().decode()[:200])
EOF
```

## After applying

Run `python3 tools/emit_activity_event.py --flush` to drain the 19 queued events
from `WAI-Spoke/runtime/activity-events-queue.jsonl` into the new table.
