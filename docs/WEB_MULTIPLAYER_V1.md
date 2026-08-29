# Web Multiplayer V1

## Scope

The first Web release is a small hosted multiplayer game for an internal network
or a limited-access server. Players connect from separate browsers to one Web
server, join an invite-code room, claim one club, mark ready, and play turns
under host control. Room creation supports both a traditional host-player mode
and a dedicated-host mode where the host never controls a club.

The game rules and simulation remain in `apps/api`. `apps/web` is a role-aware
console over the API. `apps/cli` remains available for regression checks and
operator debugging during migration.

Out of scope for V1:

- Public account registration and external auth providers
- Dedicated single-device hot-seat mode
- WebSocket or SSE delivery
- Large-room scaling, high availability, and full abuse prevention

## Roles And Data

| Capability | Dedicated host | Host-player | Club player | Viewer |
| --- | --- | --- | --- | --- |
| Create room and invite code | yes | yes | no | no |
| Join room with browser session | yes | yes | yes | later |
| Claim a club slot | no | yes | yes | no |
| Ready claimed club | no | yes | yes | no |
| Start room after every club is ready | yes | yes | no | no |
| Read public play state and standings | yes | yes | yes | later |
| Read and edit claimed club draft | no | only own club | only own club | no |
| Commit claimed club input | no | only own club | only own club | no |
| See other club private input and finance | no | no | no | no |
| Open, lock, resolve, advance turns | yes | yes | no | no |
| Ack resolved claimed club turn | no | only own club | only own club | no |
| Read all club reviews after completion | yes | yes | no | no |
| Resume own joined room from saved browser session | yes | yes | yes | no |
| Archive a game | yes | yes | no | no |
| Permanently delete an archived game | yes | yes | no | no |

V1 browser identity is a guest display name bound to an opaque session token in
an HttpOnly cookie. The database stores only the token hash, expiry, last-seen
time, user relation, room membership, club claim, ready status, and Web drafts.
CLI `X-User-Email` identity is intentionally separate from this browser flow.
The same player can resume only while that browser cookie remains valid. A
different browser/device or a deleted/expired cookie cannot prove the same guest
identity in V1.

## Web Flow

1. Host creates a room and club slots from the Web entry screen, choosing
   host-player or dedicated-host mode. The choice is fixed for that room.
2. Other browsers join with the invite code.
3. Each club player claims a club and marks it ready in the lobby. In
   dedicated-host mode, the host remains unassigned and does not mark ready.
4. Host starts the room. The API creates the season, turns, decisions, and
   fixtures using the existing game model.
5. Every browser enters the same game console. Public progress is polled.
6. Players edit only fields enabled for the current turn. Drafts autosave.
7. Players commit. Host locks and resolves after all clubs commit.
8. Players acknowledge resolved results. Host advances after all clubs ack.
9. Returning users choose a saved active/lobby room from the resume list.
10. Hosts can archive games, then permanently delete archived game data after
    confirming the invite code.

## CLI To Web Input Mapping

| CLI concept | Web V1 behavior |
| --- | --- |
| Inspect current input schema | API returns current `available_inputs`; UI renders only those fields |
| Set monthly decision values | Numeric controls for sales, promo, and hometown spending |
| Set next home promo | Conditional field when the API exposes it |
| Set December additional reinforcement | Conditional field in December |
| Set June or July next-season reinforcement | Conditional field in off-season input months |
| Set quarterly sales allocation | Conditional ratio input at quarter start |
| Staff planning in May | May section inside the turn console |
| Academy budget in May | May section inside the turn console |
| Commit | One `入力を確定` action after draft save |
| GM turn lifecycle commands | Host control bar: `open`, `lock`, `resolve`, `advance` |

The browser UI does not embed a CLI parser. Simplification is a context-aware
form replacement, not a change to simulation rules.

## Console Wireframes

Lobby host view:

```text
+ room status / invite code --------------------------------------------+
| club slots and claim state                         participant state   |
| club A  host      ready                            HOST READY          |
| club B  player 2  waiting                          PLAYER WAIT         |
| club C  open      waiting                          [start when ready]  |
+-----------------------------------------------------------------------+
```

Shared console:

```text
+ room / season / turn / polling ---------------------------------------+
| views | turn input and event sections       | public club progress    |
|       | simplified current fields only      | host controls if GM     |
|       | draft save state and commit / ack   | public state            |
+-----------------------------------------------------------------------+
| finance summary | next fixtures | standings | event/result summary    |
+-----------------------------------------------------------------------+
```

GM and GM-player combinations use the same console. The host control pane is
active only for the host. A GM who claimed a club receives that club's private
input pane in the center column as well.

## Environments

Local:

- Web calls relative `/api` URLs.
- Next rewrites `/api` to `API_PROXY_ORIGIN` for development.
- PostgreSQL and API migrations must be running before browser turn flow tests.
- Preserve the PostgreSQL volume to preserve game progress. `docker compose down`
  keeps the named volume, while `docker compose down -v` deletes saved game data.

Limited shared server:

- Prefer one same-origin entry point.
- Route `/api` to FastAPI and all other paths to Next.js through the gateway or
  reverse proxy.
- Set secure cookie policy according to TLS termination.
- Persist PostgreSQL data; do not depend on app process memory for room state.
- Back up PostgreSQL before destructive migrations or bulk deletion.

Future public environment:

- Replace guest-only entry with an account or external-auth identity binding.
- Add operational monitoring, backup policy, rate limiting, recovery playbooks,
  and real-time delivery only after the API contract is stable.

## Playtest Checklist

- Host-player mode completes lobby creation, join, claim, ready, and start with
  the existing browser arrangement.
- Dedicated-host mode completes the same flow with one host browser plus one
  separate player browser for every club.
- Maximum configured club count completes the same flow.
- Dedicated-host and host-player modes both enter the shared console correctly.
- A dedicated host has no club input pane and cannot call club-private APIs.
- Reload during draft entry restores draft state.
- Reconnect from the same browser session returns to the room.
- A player cannot read another club console, draft, or private finance.
- A non-host cannot use turn lifecycle endpoints.
- A turn reaches commit, lock, resolve, ack, and advance.
- One season can be played through before hosted hardening work starts.
