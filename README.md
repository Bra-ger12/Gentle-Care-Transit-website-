# Gentle Care Transit

Non-Emergency Medical Transportation (NEMT) web system for North Dakota.
Django REST Framework backend + plain HTML/CSS/JS frontend + PostgreSQL, JWT auth.

All roadmap phases are complete: auth and roles, trip booking and lifecycle,
driver assignment and dispatch, billing and reports, realtime tracking and
notifications, and the operations layer (service area, policy, driver calendar,
claim exports). See `docs/roadmap.md` for the per-phase summary.

**The system runs with no third-party API keys.** Without a Google Maps key it
resolves addresses against a built-in North Dakota gazetteer and estimates
mileage by haversine; trips priced that way are stored with
`distance_estimated=True` so a computed distance is never mistaken for a
measured one. Add a key and it upgrades to measured routes automatically.

## Prerequisites

- Python 3.12 (a dedicated interpreter — do not use a newer/older system Python)
- Node.js 18+ and npm
- PostgreSQL 18 running locally
- Redis — optional in dev (WebSockets use an in-process channel layer and the
  scheduled sweeps run via management commands); required in production for the
  Redis channel layer, the Celery worker, and Celery beat

## Backend setup

```bash
cd backend
"C:\path\to\Python312\python.exe" -m venv venv
venv\Scripts\activate
pip install -r requirements/dev.txt
```

Create the database role and databases once (via `psql`, as a superuser):

```sql
CREATE ROLE gentlecare WITH LOGIN PASSWORD 'gentlecare_dev_pw' CREATEDB;
CREATE DATABASE gentlecare_dev  OWNER gentlecare;
CREATE DATABASE gentlecare_test OWNER gentlecare;
```

Copy `.env.example` to `.env` and fill in `SECRET_KEY` (generate one with
`python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` —
avoid `#` in the value, or quote it, since some `.env` parsers treat `#` as a
comment marker) and `DATABASE_URL`.

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

That one process serves **the whole system on Django's default port**:

| URL | What |
| --- | --- |
| `http://localhost:8000/` | the app (landing page, login, all three portals) |
| `http://localhost:8000/api/` | REST API |
| `http://localhost:8000/api/docs/` | interactive API docs |
| `http://localhost:8000/django-admin/` | Django's own admin |

While `DEBUG` is on, the backend serves the `frontend/` directory at the site root
(`FRONTEND_DIR`, overridable in `.env`), so there's one origin: no CORS preflights
and no cross-port refresh cookie in dev. Django's admin sits at `/django-admin/`
rather than `/admin/`, which belongs to the operator portal's pages. In production
`frontend/` is served by a real web server or CDN instead — the catch-all route is
registered only under `DEBUG`.

### Seed the demo data

```bash
python manage.py seed_demo
```

Creates 1 admin, 5 riders, 3 drivers and 23 trips covering **every** status the
UI renders, plus invoices across the billing lifecycle, driver earnings, vehicle
inspections, a recurring series, and one round trip with a will-call return.

Every account it creates lives on the `@demo.gentlecaretransit.org` domain and
nothing outside that domain is ever touched, so `--flush` is safe to run against
a database that also holds real accounts:

```bash
python manage.py seed_demo --flush   # delete the demo data and rebuild it
```

#### Seed credentials

All three sign in with the password **`GentleCare!2026`**:

| Role | Email |
| --- | --- |
| Admin | `dispatch@demo.gentlecaretransit.org` |
| Rider | `m.thorson@demo.gentlecaretransit.org` |
| Driver | `t.nguyen@demo.gentlecaretransit.org` |

The other seeded riders are `h.iverson`, `d.littlebear`, `f.schmitt` and
`e.rodriguez`; the other drivers are `s.okafor` and `j.beaulieu`, all on the same
domain and password.

### PDF export

The Medicaid claim export produces both CSV and PDF. The PDF is drawn with
ReportLab, which is pure Python — **no native libraries, no extra setup on any
platform.** (An earlier version used WeasyPrint and silently failed on Windows
and slim Linux images, which is not much use for a claim export.)

### Realtime & background jobs (Phase 5)

WebSockets are served on the same ASGI app as HTTP. `daphne` is installed, so
`python manage.py runserver` already serves both — you don't need a separate
process in dev. In dev the channel layer is in-memory (no Redis), which works
because a single process serves both HTTP and WebSocket. Endpoints:
`ws/notifications/` (bell), `ws/dispatch/` (admin board), and
`ws/trips/<id>/track/` (live GPS tracking). Each connection authenticates with
the access token passed as `?token=<jwt>` (browsers can't set a WebSocket auth
header).

The scheduled sweeps — trip reminders and license-expiry alerts — are idempotent
and run on demand in dev:

```bash
python manage.py send_trip_reminders
python manage.py check_document_expiry
```

Live tracking needs a browser Google Maps key; set `GOOGLE_MAPS_BROWSER_KEY`
(or leave blank to reuse `GOOGLE_MAPS_API_KEY`) — it's served to the frontend at
`/api/public-config/`. SMS is optional: without `TWILIO_*` credentials, SMS is a
logged no-op and everything else still works.

In **production**, set `CHANNELS_BACKEND=redis` (uses `channels_redis` +
`CHANNELS_REDIS_URL`) and run the async server plus Celery:

```bash
daphne config.asgi:application         # ASGI server (HTTP + WebSocket)
celery -A config worker -l info        # runs reminder/alert tasks
celery -A config beat   -l info        # schedules them (static CELERY_BEAT_SCHEDULE)
```

### Run backend tests

```bash
pytest        # 449 tests
ruff check .  # lint
```

Tests never touch the network: `config/settings/test.py` blanks the Maps key so
the geocoder goes straight to its offline path instead of spending a timeout per
call discovering that CI has no internet.

## Frontend setup

The frontend is plain HTML/CSS/JS — no framework, no build step, no
`node_modules`. **In dev it needs no server of its own**: `manage.py runserver`
already serves it at `http://localhost:8000/` (see above).

If you'd rather run it standalone — to serve it the way production will, or to
edit it without the backend running — any static server works, on one of the
ports the API client recognises as standalone (5173, 3000 or 8080), which is
also what the backend's CORS config allows:

```bash
cd frontend
python -m http.server 5173
```

`js/api/client.js` picks its `API_BASE` from the page's own origin, falling back
to `http://localhost:8000/api` on those standalone ports — so the same files work
either way. Must be accessed via `http://`, not `file://` — cookies and CORS
require a real HTTP origin.

(The previous React/Vite implementation is preserved for reference in
`frontend-react-legacy/`.)

## Architecture notes

- **Auth**: JWT via `djangorestframework-simplejwt`. Access token is returned in
  the login response body and held in memory on the frontend; the refresh
  token is set as an httpOnly cookie by the backend (never touched by
  frontend JS) and rotated/blacklisted on every refresh.
- **Roles**: a single `User` model (`apps.accounts.models.User`) with a
  `role` field (`RIDER` / `DRIVER` / `ADMIN`), plus one-to-one `RiderProfile`
  and `DriverProfile` tables holding role-specific fields.
- **Audit logging**: `apps.audit.AuditLog` + the `AuditedRetrieveUpdateMixin`
  record who viewed/edited PHI-adjacent records (starting with rider
  profiles), per the HIPAA-conscious design goal.
- **Settings**: split into `config/settings/{base,dev,test,prod}.py`, all
  configuration driven by environment variables (`backend/.env`).
- **Driver pay**: `apps.payroll` mirrors billing's shape — `DriverPayRate`
  (effective-dated per-trip base + per-mile, optionally per driver) and
  `TripEarning` (one snapshotted row per completed trip, marked paid with a
  reference). Kept separate from `apps.billing` because what the rider is
  charged and what the driver is paid are independent.
- **Vehicle inspections**: `apps.fleet.VehicleInspection` is the daily DVIR —
  pre/post-trip, odometer, NEMT-aware defect checklist, safe-to-operate
  declaration and signature. Flagged reports queue for an admin to clear.
- **Account settings**: `/account.html` is the one self-service screen for every
  role — own user record (`/auth/me/`), role profile (`/auth/me/rider-profile/`
  or `/auth/me/driver-profile/`, the latter accepting a multipart insurance
  document), and notification preferences.
- **Realtime & notifications**: `apps.notifications` centralizes delivery through
  one `notify()` fan-out (durable in-app row + live socket + email + Twilio SMS,
  gated by `NotificationPreference`). Django Channels consumers back the
  notification bell, dispatch board, and per-trip live GPS tracking; a
  `JWTAuthMiddleware` authenticates WebSockets from the `?token=` query string.
  Trip lifecycle events reach it one-way through `apps.trips.notifications`.
- **Geocoding without a key**: `apps.trips.services.geo` holds a gazetteer of 119
  North Dakota communities plus the border towns riders are referred into, a
  haversine distance, and a road-circuity model banded by trip length. An address
  resolves to its town centre plus a deterministic offset hashed from the address
  text, so two addresses in one town never collapse to a zero-mile trip and the
  same address always lands on the same point. `maps.py` prefers Google and
  degrades to this when the key is missing or the API refuses.
- **Operations policy**: `apps.operations` holds the two things an administrator
  changes without a deploy — `ServiceArea` (a town, or a radius around a point;
  both ends of a trip must satisfy one) and a singleton `SystemSetting`
  (cancellation cutoff, booking lead time, no-show wait, email-verification
  requirement, and the wording of rider-facing messages).
- **Trip state machine**: `REQUESTED → CONFIRMED → ASSIGNED → EN_ROUTE → ARRIVED
  → PICKED_UP → COMPLETED`, with `CANCELLED` and `NO_SHOW` as exits. Enforced in
  one place (`TripViewSet._apply_transition` against `STATUS_TRANSITIONS`), so no
  route can skip a step. `NO_SHOW` is only reachable from `ARRIVED`, because the
  wait clock that justifies the claim runs from the recorded arrival.
- **Round trips**: booked as two `Trip` rows linked by `outbound_trip`, not one
  row with two times — each leg is separately dispatched, driven and billed, and
  the return routinely gets a different driver. A will-call return sits idle
  until the rider asks for it.

## What each role can do

**Rider** — register and confirm their email; book one-way or round trips
(scheduled return or will-call) with mobility needs, escorts and notes; set up a
weekly recurring series; see a status timeline and track the driver live; cancel
or reschedule inside the configured cutoff; call in a will-call return; rate the
driver; read invoices; manage contact details, care needs and alert preferences.

**Driver** — apply and wait on approval; record licence, vehicle and an insurance
document (checked on its actual bytes, not its filename); go on and off duty;
work a daily manifest; accept or decline with a reason; run the four-step
workflow (en route → arrived → boarded → drop-off) with odometer readings and a
drawn signature; file a no-show only after the required wait has elapsed; file
pre- and post-trip DVIRs; keep a weekly shift calendar and book time off; see
trips, miles and earnings.

**Admin** — a dispatch board with a live fleet map and nearest-driver
suggestions; take bookings over the phone on a rider's behalf; confirm, assign,
reassign and auto-assign; approve, reject and suspend accounts; manage vans and
review flagged inspections; generate, finalise, pay and void invoices; export ND
Medicaid claims as CSV or PDF; download trip, revenue, driver-performance and
mileage CSVs; read the audit log; and set the service area, the cutoffs and the
message wording from one settings screen.

## Roadmap

1. ~~Auth + roles~~ (done)
2. ~~Trip booking & lifecycle~~ (done)
3. ~~Driver assignment & dispatch~~ (done)
4. ~~Billing & reports (incl. ND Medicaid NEMT export)~~ (done)
5. ~~Realtime tracking & notifications (Channels, Celery, Twilio)~~ (done)
6. ~~Operations: service area, runtime policy, driver calendar, claim exports~~ (done)
