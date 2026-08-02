# Roadmap

Built iteratively, one phase at a time. Full spec context lives in the
original project brief; this file tracks phase-by-phase status.

## Phase 0 — Scaffolding (done)

Repo layout, Django settings split, ASGI/Celery skeleton, Postgres dev/test
databases, Vite React app skeleton.

## Phase 1 — Auth + roles (done)

Custom `User` model (email required, phone optional, `role` field),
`RiderProfile` / `DriverProfile`, JWT login (email-or-phone) with httpOnly
refresh cookie, DRF role permissions (`IsRider`/`IsDriver`/`IsAdminRole`/
`IsOwnerOrAdmin`), minimal audit logging on profile view/edit, password
reset, React auth context + protected routes + role-based landing pages.

## Phase 2 — Trip booking & lifecycle (done)

`apps/trips`: `Trip` and `RecurringTripSeries` models, status state machine
(Requested → Confirmed → Completed/Cancelled/No-Show), Google Maps geocoding
and mileage at booking time, 24h cancellation-cutoff validation, first Celery
task (rolling-window recurring series generation), rider booking UI and trip
timeline. Service-area validation deferred to a later phase (no restriction
enforced yet).

## Phase 3 — Driver assignment & dispatch (done)

Admin driver-approval queue with license expiry flags (on top of Phase 1's
`DriverProfile`), manual + simple auto trip assignment (approval + vehicle
capability + double-booking checks, no location data yet), driver accept/
decline and step-by-step status updates (Assigned → EnRoute → PickedUp →
Completed), odometer + typed attestation capture at completion, driver
no-show reporting, polling-based admin dispatch board. Document/insurance
expiry is admin-visible only (no email/SMS yet — that's Phase 5).

## Phase 4 — Billing & reports (done)

`apps/billing`: `RateSchedule` (effective-dated, per-mobility-tier base
fare + per-mile rate) and `Invoice` (one per completed trip, snapshotted
rider/rate details, DRAFT → FINALIZED → PAID / VOID lifecycle with
void-then-reissue support). ND Medicaid NEMT reimbursement export
(CSV + WeasyPrint PDF, admin-only, riders with a `medicaid_id` on file) --
a generic reimbursement export, not a certified ND DHS claim form.
`apps/reports`: admin KPI dashboard (trip volume, cancellation/no-show
rate, avg cycle time, revenue summary, revenue-by-month) with no
persisted state of its own. `apps/audit` gained a read-only API
(`AuditLogViewSet`) plus an `EXPORT` action, exposing the existing
`AuditLog` model for the first time. Rider-facing read-only invoice
history included; driver payouts/commissions explicitly out of scope.

## Phase 5 — Realtime & notifications (done)

`apps/notifications`: a `notify()` fan-out that writes a durable in-app
`Notification`, then best-effort delivers over the live WebSocket, email, and
Twilio SMS (SMS a logged no-op without creds), gated by per-user
`NotificationPreference`. Three Django Channels consumers on the Phase 0 ASGI
skeleton — per-user notification bell, admin dispatch board, and per-trip live
tracking — authenticated by a `JWTAuthMiddleware` that reads the access token
from the WebSocket query string. Trip status transitions (`apps/trips`) fan out
notifications and broadcast to the dispatch + trip groups via a one-way
`trips.notifications` bridge; driver approval notifies the driver. Live GPS
tracking: the driver's browser streams `geolocation` over the trip socket while
en route/picked up (only the assigned driver may publish), and the rider's trip
page shows the moving driver on a Google Map plus a live status timeline.
Celery `send_trip_reminders` / `check_document_expiry` tasks (static beat
schedule for prod) with `manage.py` equivalents for Redis-free dev. Dev uses the
in-memory channel layer (no Redis); `CHANNELS_BACKEND=redis` switches prod to
`channels_redis`. The browser Maps key is served via `/api/public-config/`.

## Dashboard redesign (done)

A mockup-driven rebuild of all three role dashboards on top of the finished
phases — no new domain concepts, no model changes.

- **Shell**: patient and admin portals moved to a left **sidebar**
  (`renderNav` adds `body.has-sidebar`, CSS grid re-lays the existing
  `nav | main | footer` markup); the driver portal keeps a top bar so its
  operations view can use the full width.
- **Patient hub** (`rider/index.html`): "Your next ride" card (driver name,
  ★ rating, plate, live-tracking + cancel), "Book again" cards derived from the
  rider's own past destinations (prefilling the booking form), and a compact
  upcoming/past trips table.
- **Driver operations view** (`driver/index.html`): top bar (`Driver:` name,
  vehicle, an ON/OFF DUTY pill that toggles `is_available`, and an SOS dispatch
  call), today's manifest with a state glyph per row, an active-trip panel
  headed `Active trip: <passenger>` with labelled rows (passenger · needs ·
  pickup · dropoff · scheduled time), a highlighted note, the live map with GPS
  streaming, a full-width navigation hand-off, and a **three-step workflow** —
  *En route to pickup → Passenger boarded → Complete drop-off* — where done
  steps read as done, the step the trip is waiting on is the only one enabled,
  and later steps stay greyed out. An unaccepted assignment gates the whole
  stepper behind Accept/Decline; step 3 reveals the odometer + attestation form;
  no-show sits beside the stepper while en route. Bottom bar: DVIR · trips ·
  miles · earnings · vehicle.
  Step 1 is labelled for the transition it actually performs (`EN_ROUTE`) rather
  than the mockup's "Arrived at Pickup" — the system records no arrival event.
- **Driver completeness pass**: the board is day-scoped, so it grew a **day
  stepper** (‹ / date picker / › / Today) over the `?date=` filter, and
  `driver/schedule.html` lists every trip ever assigned, filterable by state and
  paginated. `driver/trip-detail.html` became a real **trip record** — passenger,
  needs, route, milestone timestamps, odometer + attestation, and the rider's
  rating and review — while keeping the transitions, since notification links
  land there. **Decline and no-show now capture a reason** (the API always
  accepted one; the UI discarded it): it's stored on the trip, quoted in the
  admin notification, and shown on the dispatch queue row so the next assignment
  is informed. `labelledRow`/`labelledRows` and `reasonAction` are shared UI.
- **Dispatch overview** (`admin/index.html`): today's stat tiles, the unassigned
  queue (assign / auto-assign, live over the dispatch socket), and a **live fleet
  map** — one marker per in-flight trip plus a moving dot per driver streaming
  location, built once so refreshes never reset the dispatcher's viewport.
- **Live driver board**: the notification bell exposes `onNotification`, so the
  driver's manifest follows the socket it already opens instead of a second one.
  A trip-related notification refreshes the board — repainting only the manifest
  and metrics while a trip is streaming GPS, so a change the driver didn't make
  never restarts their location watch or rebuilds the map.
- **Supporting API additions** (no migration): `TripDetailSerializer` gained
  `rider_name` / `rider_phone` / `rider_mobility_needs` and
  `assigned_driver_rating` / `_vehicle_plate` / `_vehicle_type`;
  `TripListSerializer` gained pickup/drop-off coordinates and `mobility_need`;
  the trip list accepts `?date=YYYY-MM-DD` (project timezone) for daily
  manifests and today's counts.
- **Honest gaps**: driver earnings/payouts stay out of scope (shown as "—"),
  vehicle inspection reports have no model yet (the button says so), and saved
  locations are derived from real trip history rather than invented.

## Reachability pass (done)

Several finished backend capabilities had no way in from the UI. No new domain
concepts — this closed the gap between what the API supports and what a signed-in
user can actually do.

- **`/account.html`** (all roles): edit your own name / email / phone
  (`PATCH /auth/me/`); riders get date of birth, address, emergency contact,
  mobility needs and **Medicaid ID** — the field that decides whether their
  completed trips appear on the NEMT reimbursement export; drivers get license
  number/expiry, vehicle type/plate/capacity and insurance-document upload
  (multipart), with approval and background-check status shown read-only.
  Everyone gets **notification preferences** (`email_enabled` / `sms_enabled`),
  which had a serializer, an endpoint and a frontend API module but no screen.
  DRF field errors are surfaced per field rather than as a generic failure.
- **`/rider/recurring.html`**: riders could create a recurring series from the
  booking form but never see or stop one. The page lists each series (weekdays,
  pickup time, date window, route, needs, notes) and ends it via `deactivate`,
  which until now had no test either.
- **The booking lifecycle now closes in the UI.** A rider's booking lands in
  `REQUESTED`, and `confirm` — the only transition out of it — had no caller:
  requests could never reach the assignment queue except through the API or
  Django admin. The dispatch board grew a **"New requests — awaiting
  confirmation"** section (Confirm, or Decline with a reason the rider is
  notified about), so the "awaiting confirmation" tile is now actionable.
- **Reassignment is reachable**: the in-flight table offers *Reassign* (a named
  driver or "next available") on trips still awaiting driver acceptance —
  matching the API's own rule. `TripListSerializer` gained `accepted_at` so the
  board can tell "assigned, waiting on the driver" from "accepted".
- **Pending drivers can act**: the under-review screen listed no way to supply
  the documents it says are being verified. It now names what's still missing
  (license, expiry, vehicle, insurance) and links to the account page.
- **Upstream Maps failures return 400, not 500**: `geocode_address` let the
  googlemaps client's own exceptions (denied key, billing disabled, quota,
  timeout) escape, so a misconfigured Maps project produced a 500 HTML page from
  booking. They're translated to `GeocodingError` now, which both booking
  serializers already turn into a readable 400.

Still deliberately unbuilt: service-area validation, and the Privacy/Terms/Contact
pages the footer links to.

## Driver pay & vehicle inspections (done)

The two gaps that needed a schema rather than a screen. Both are new apps, so
neither complicates the rider-billing path they sit beside.

**`apps.payroll` — what the driver earns.** Chosen model: a flat amount per
completed trip plus a per-mile rate.
- `DriverPayRate` is the deliberate mirror of `billing.RateSchedule`:
  effective-dated, `is_active`, and optionally scoped to one driver — a
  negotiated rate overrides the house default (blank `driver`) without touching
  anyone else's pay. The two rate tables move independently: what the rider is
  charged and what the driver is paid are different questions.
- `TripEarning` is one row per completed trip, snapshotting base, per-mile rate,
  mileage and total for the same reason invoices snapshot: editing a rate later
  must never restate what a driver was already told they earned. Generation is
  idempotent, refuses a trip that isn't completed/driven, and refuses to guess
  when no rate covers the date.
- Admins set rates, generate earnings and mark them paid (with a reference) at
  `/admin/payroll.html`; drivers see their own total on the board's **Earn**
  tile and a per-trip breakdown on their report.

**`apps.fleet` — the daily vehicle check.** `VehicleInspection` is a DVIR: type
(pre/post-trip), odometer, a defect checklist that includes the NEMT-specific
items (wheelchair lift, securements, oxygen mount), notes, a safe-to-operate
declaration and a typed signature. The plate is snapshotted, since a driver can
be moved to another vehicle later.
- A flagged defect must carry a description, and a report must be signed.
- One pre-trip and one post-trip per driver per day (DB constraint); re-filing
  corrects that day's report instead of stacking duplicates, and re-opens it for
  review.
- Anything flagged sits in the admin queue at `/admin/inspections.html` until
  someone records what was done about it. The driver's board button reports
  what's still outstanding ("Pre-trip check due", "⚠️ Defects reported").
- The checklist is served from the model (`/api/fleet/inspection-checklist/`) so
  the form never hard-codes it.

**Vans** (`/admin/vehicles.html`) became a fleet view rather than a list of form
fields: one card per van showing plate, type, capacity, the driver who operates
it with their duty state and current load, the licence badge, and the latest
inspection — a van whose driver marked it unsafe reads as **grounded**. It also
names the two things that silently break dispatch: a missing/duplicated plate
(two vans dispatch can't tell apart) and a missing vehicle type (auto-assignment
can't match it to a wheelchair or stretcher trip).

A van is still a set of fields on `DriverProfile`, so it's one van per driver.
A standalone `Vehicle` model — vans that exist independently, get reassigned
between drivers, and go out of service on their own — would need a migration
through `trips.services.assignment` and the inspection snapshot; it hasn't been
done.

## One-origin dev serving (done)

`manage.py runserver` now serves the whole system on Django's default port:
under `DEBUG`, a catch-all route hands `frontend/` (`FRONTEND_DIR`) to
`django.views.static.serve`, mapping `/` and `/rider/` to their `index.html` and
404ing anything that resolves outside the directory. Registered last, so every
`/api/`, `/django-admin/` and `/media/` route still wins.

Two consequences worth knowing:

- **Django's admin moved to `/django-admin/`.** At `/admin/` it shadowed the
  operator portal's own `/admin/*.html` pages, which 302'd to the Django login.
- **`API_BASE` is derived from the page's origin** (`js/api/client.js`), falling
  back to `http://localhost:8000/api` only on the standalone static-server ports
  (5173/3000/8080). Same-origin dev means no CORS preflight and no cross-port
  refresh cookie — the failure mode behind `gotcha_dev_cross_port_session_reload`.

Production is unchanged: the catch-all exists only under `DEBUG`, and a real web
server or CDN serves `frontend/`.

## Phase 6 — Production completion (done)

The audit that opened this phase found the system substantially built but with
one blocker and a set of half-built or missing capabilities. All are closed.

### The blocker: running without third-party keys

`services/maps.py` hard-failed when Google Maps was unconfigured or refusing, and
`TripCreateSerializer` turned that into a 400 — so with billing disabled on the
Maps project, **no trip could be booked at all**.

`services/geo.py` is the answer: a gazetteer of 119 North Dakota communities plus
the border towns riders are referred into, haversine distance, and a road-circuity
model banded by trip length (1.35 in town, 1.22 mid-range, 1.10 on the trunk
highways). An address resolves to its town centre plus a deterministic offset
hashed from the address text — two addresses in one town never collapse to a
zero-mile trip, and the same address always lands on the same point.

The circuity model is banded rather than flat because a single 1.25 factor billed
Bismarck→Fargo at 236 miles against a true 193. It is an estimate either way,
which is why every record built from it carries `distance_estimated=True` and the
flag is surfaced on the trip, the invoice, the mileage CSV and the claim export.

### Schema

- **`ARRIVED`** joins the state machine between `EN_ROUTE` and `PICKED_UP`.
  `NO_SHOW` is now reachable *only* from `ARRIVED`: the wait clock that justifies
  the claim runs from a recorded arrival, and a no-show filed before the required
  wait is refused with the minutes remaining.
- **Round trips** are two `Trip` rows linked by `outbound_trip`, not one row with
  two times — each leg is separately dispatched, driven and billed, and the
  return routinely gets a different driver. A **will-call** return sits idle until
  the rider asks for it.
- **Escorts** (`escort_count`) feed vehicle selection: assignment now excludes
  vans without enough seats, while treating an unrecorded capacity as a missing
  record rather than a small vehicle.
- **Signatures** are captured on a canvas and stored as PNG, validated on magic
  bytes rather than the declared type. The typed attestation remains as a
  fallback, and the claim export says which of the two it is.

### Pricing

`RateSchedule` gained wheelchair and stretcher surcharges plus a wait-time rate
with a free allowance. Billable wait is measured from `arrived_at` to
`picked_up_at`, so the driver's arrival timestamp is what makes the charge
defensible. All four components are snapshotted onto the invoice.

### `apps.operations`

The two things an administrator changes without a deploy:

- **`ServiceArea`** — a named town, or a radius around a point. Both ends of a
  trip must satisfy at least one active rule. With no rules configured the
  service area is unrestricted, which is what a fresh install starts as.
- **`SystemSetting`** — a singleton holding the cancellation cutoff, booking lead
  time, no-show wait, the email-verification requirement, and the wording of
  rider-facing messages. A typo in a template placeholder renders as literal text
  rather than stopping a notification.

### Everything else

Email verification (own token salt, so a reset link can never verify an address;
existing accounts grandfathered by data migration); admin phone-booking on a
rider's behalf; reschedule, which releases an assigned driver because whoever
accepted a 09:00 pickup did not agree to a 15:00 one; a driver shift calendar and
time off that gate auto-assignment; stored driver positions (one row per driver,
overwritten — dispatch needs where people are, not a history of where they have
been) feeding nearest-driver ranking; on-time performance, fleet activity and
today's tiles on the KPI dashboard; four report CSVs, all audited on download;
Medicaid claims carrying prior-auth, pickup and drop-off times and a signature
reference, with the PDF redrawn in ReportLab so it works on every platform;
content-checked document uploads; and a `seed_demo` command whose data covers
every status a screen renders.

Frontend: a four-step driver workflow with a live wait clock, canvas signature
capture, the shared booking form behind both the rider and phone-booking flows,
an admin settings screen, driver availability, email confirmation, a shared
`form-errors` helper that puts the server's own message against the field it
belongs to, an SVG logo used as mark and favicon, Privacy/Terms/Contact pages,
a responsive pass to 360px, and reduced-motion guards on the animations that
lacked them.

**Verified:** 449 backend tests, ruff clean, and an 84-check end-to-end walk of
all three roles over HTTP against the running server.
