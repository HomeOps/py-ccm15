# Improvement analysis — py-ccm15

A review of the codebase as of `v1.1.2` (commit `4dc5c8d`), 2026-10-19. Findings
are ranked by impact: **1–3 are correctness bugs**, **4–6 are robustness gaps**,
**7 is a design decision worth revisiting**, **8 is a readability nit**.

Each finding notes the suggested PR type under this repo's
[release-please](.github/workflows/release-please.yml) policy (see CLAUDE.md).

---

## 1. `@dataclass` on `CCM15SlaveDevice` generates a broken `__eq__`

**File:** `ccm15/CCM15SlaveDevice.py:7`
**Severity:** correctness (latent)
**Suggested PR type:** `fix`

`CCM15SlaveDevice` is decorated with `@dataclass` but declares **no fields** —
all state is assigned in a hand-written `__init__`/`update`. With zero fields,
the `__eq__` that `dataclass` generates compares empty tuples:

```python
def __eq__(self, other):
    if other.__class__ is self.__class__:
        return () == ()   # always True
    return NotImplemented
```

So `CCM15SlaveDevice(a) == CCM15SlaveDevice(b)` is **always `True`** for any two
instances, regardless of their decoded state. The decorator also generates a
`__repr__` that shows nothing (`CCM15SlaveDevice()`), hiding the actual fields
during debugging.

Nothing in the current codebase or the Home Assistant integration appears to
rely on `==`, which is why this has not bitten anyone — but it is a landmine
for any consumer that compares, deduplicates, or asserts on device objects.

**Fix:** remove the `@dataclass` decorator and the `dataclass` import. The
class already defines its own `__init__`; Python's default identity-based
`__eq__` and a (optionally added) informative `__repr__` are the correct
semantics.

Note: `CCM15DeviceState` *does* have a real field (`devices`), so its
dataclass-generated `__eq__` is sound and can stay.

---

## 2. `async_send_state` lets transport errors escape instead of returning `CONNECTION_ERROR`

**File:** `ccm15/CCM15Device.py:218-228`
**Severity:** correctness (contract inconsistency)
**Suggested PR type:** `fix`

`async_send_state` performs the HTTP request without catching
`httpx.RequestError`:

```python
async def async_send_state(self, url: str) -> CCM15ReturnCode:
    response = await self._get_client().get(url, timeout=self.timeout)
    if response.status_code not in (httpx.codes.OK, httpx.codes.FOUND):
        return CCM15ReturnCode.CONNECTION_ERROR
    return self._parse_return_code(response.text)
```

A timeout or connection reset during a **write** therefore raises a raw
`httpx.ConnectTimeout` / `httpx.ConnectError` to the caller. But the library's
own contract says otherwise:

- `CCM15ReturnCode.CONNECTION_ERROR` is documented as *"The request failed or
  returned a non-OK HTTP status"* (`ccm15/CCM15ReturnCode.py:21-23`) — "the
  request failed" covers transport errors.
- The sibling method `async_test_connection` (`CCM15Device.py:209-216`)
  **does** catch `httpx.RequestError` and converts it to a return value
  (`False`).

So the two HTTP entry points handle the same failure class differently, and
`async_send_state` violates the semantics its return type advertises. A caller
branching on `CCM15ReturnCode` (as the enum is designed for) will not expect a
raised exception from the "connection error" path.

**Fix:**

```python
try:
    response = await self._get_client().get(url, timeout=self.timeout)
except httpx.RequestError:
    return CCM15ReturnCode.CONNECTION_ERROR
```

This is behavior-compatible for callers that already catch broad exceptions,
and strictly more predictable for callers that branch on the return code.

---

## 3. A short slot payload aborts the entire poll

**File:** `ccm15/CCM15Device.py:106-118`, `ccm15/CCM15SlaveDevice.py:35-84`
**Severity:** correctness (robustness against a flaky device)
**Suggested PR type:** `fix`

`_fetch_data` guards against non-hex payloads (`bytes.fromhex` → `ValueError`
→ `continue`) but not against **short** payloads. `CCM15SlaveDevice.update()`
indexes `bytesarr[0]` through `bytesarr[6]` unconditionally. If a slot ever
reports fewer than 7 bytes (a truncated or degraded frame from the controller —
plausible, given the documented flakiness that motivated the per-slot cache),
`update()` raises `IndexError`, which propagates out of `_fetch_data` into
`get_status_async`'s broad `except Exception`:

```python
try:
    state = await self._fetch_data()
except Exception:
    cached = self._cached_state(now)
    ...
```

The result: **one malformed slot discards the whole response**, and every other
slot that decoded fine is replaced by cached (stale) values — or the exception
surfaces if the cache is empty. The per-slot `try/except` structure in
`_fetch_data` was clearly intended to make slot-level malformation
non-fatal; the `IndexError` path defeats that intent.

**Fix:** in `_fetch_data`, skip payloads that are not exactly 7 bytes:

```python
bytesarr = bytes.fromhex(str(ac_binary).strip(","))
if len(bytesarr) < 7:
    continue
```

(Use `< 7` rather than `!= 7` so a longer-than-expected frame still decodes
its first 7 bytes instead of being dropped.)

---

## 4. `requires-python = ">=3.7"` is below the tested floor

**File:** `pyproject.toml:18`
**Severity:** housekeeping
**Suggested PR type:** `build` (no release)

The declared minimum (3.7) is older than anything this project actually
supports or tests:

- CI matrix: Python **3.9**–3.12 (`.github/workflows/test.yml:40`)
- mypy target: **3.10** (`pyproject.toml:37`)
- README: "Python 3.7+" (stale)

Python 3.7 and 3.8 are EOL. Declaring support for them implies a test and
compatibility burden the project does not carry.

**Fix:** set `requires-python = ">=3.9"`, update the README's Requirements
section, and (optionally) drop the `from __future__ import annotations`
imports, which are no longer needed for the `X | None` annotations on 3.9+…
in fact `X | None` in *runtime* positions needs 3.10, but all such uses here
are annotation-only, so 3.9 is fine either way. Keep or drop the future
imports per taste; they are harmless.

---

## 5. `async_set_state` does not validate `ac_index`

**File:** `ccm15/CCM15Device.py:266-285`
**Severity:** robustness
**Suggested PR type:** `fix`

The controller addresses 64 slaves via the `ac0`/`ac1` mask pair. The current
code handles `ac_index < 32` and everything else as `ac1 = 2 ** (ac_index - 32)`:

```python
if ac_index < 32:
    ac0 = 2 ** ac_index
    ac1 = 0
else:
    ac0 = 0
    ac1 = 2 ** (ac_index - 32)
```

Two silent-failure cases:

- `ac_index >= 64` builds a mask bit the controller cannot interpret (bit ≥ 32
  of `ac1`), targeting nothing — the command "succeeds" (`<ret>` OK) and the
  caller believes a unit was commanded.
- `ac_index < 0` (e.g. `-1`) falls into the `ac0` branch and computes
  `2 ** -1 = 0.5`, producing `ac0=0.5` in the URL — a malformed command that
  depends on the controller's error handling to be noticed.

**Fix:** validate up front:

```python
if not 0 <= ac_index < 64:
    raise ValueError(f"ac_index must be 0-63, got {ac_index}")
```

Failing loudly at the API boundary is strictly better than a silently
ineffective command, and it cannot break the HA integration, which only ever
passes indices parsed from `status.xml` slot names (0–63).

---

## 6. Non-numeric password raises at command time, not construction time

**File:** `ccm15/CCM15Device.py:246-257`
**Severity:** robustness
**Suggested PR type:** `fix`

`_password_query()` does `int(self.password)` inside the command path:

```python
def _password_query(self) -> str:
    if not self.password:
        return ""
    pwd = (int(self.password) ^ PASSWORD_XOR_KEY) & PASSWORD_MASK
```

If a caller passes a non-numeric password (a typo, a string from a config
file with whitespace, a non-numeric firmware password), the `ValueError`
surfaces **mid-`async_set_state`**, after the URL has been partially built —
and only on the first write, not at construction. Configuration errors are
best reported at configuration time.

**Fix:** validate in `__init__`:

```python
if password is not None:
    try:
        self._password_int = int(password)
    except ValueError as e:
        raise ValueError(f"password must be numeric, got {password!r}") from e
else:
    self._password_int = None
```

and have `_password_query()` use `self._password_int`. (Keep the public
`password` attribute for compatibility; HA does not currently pass one.)

---

## 7. `update()` resets `desired_swing`/`desired_heater` — a race with the caller

**File:** `ccm15/CCM15SlaveDevice.py:70-73`, `ccm15/CCM15Device.py:120-135`
**Severity:** design (concurrency)
**Suggested PR type:** `refactor` or `fix` (behavior change — needs an HA
compatibility check)

Since the per-slot instance reuse (`perf: reuse slave device instances across
polls`, #65), the `CCM15SlaveDevice` a caller holds is the **same object** the
coordinator updates on every poll. `update()` deliberately resets the opt-in
intents:

```python
self._desired_swing: TriState = TriState.UNSET
self._desired_heater: TriState = TriState.UNSET
```

The intended caller flow is:

```python
ac.desired_swing = TriState.ON      # 1. set intent
await device.async_set_state(i, ac) # 2. send command
```

If a poll lands **between steps 1 and 2**, `update()` resets
`desired_swing` to `UNSET`, and the command goes out **without** `sw=` —
silently dropping the user's swing request. The window is small but real, and
it is wider than it looks: the coordinator and the service call are separate
coroutines, and nothing in this library serializes them.

The reset exists so that "a poll can never cause an opt-in parameter to start
being sent" — but that invariant is already guaranteed by the *default* being
`UNSET` and by the fact that only the caller ever sets a desired value. The
reset in `update()` protects against a different (and rarer) scenario: a
caller sets `desired_swing`, the command fails, and a later *unrelated*
command re-sends the stale intent. That scenario is better handled by the
caller clearing the intent after a successful write, or by the library
clearing it **inside `async_set_state` after a successful send** — which is
race-free because it happens in the same coroutine as the send.

**Options:**

1. **Clear the intent in `async_set_state` after a successful send** (and
   remove the reset from `update()`). Race-free, and the "poll never sends an
   opt-in param" invariant is preserved because the intent only exists between
   an explicit set and its own send.
2. **Keep the reset in `update()`** and document that callers must set the
   intent and send atomically (e.g. under the same lock as the coordinator).
   This pushes concurrency discipline onto every consumer.
3. **Move the intent out of the shared object entirely** — take
   `swing: TriState = TriState.UNSET` / `heater: TriState = TriState.UNSET`
   as parameters to `async_set_state`. Cleanest, but a **breaking API change**
   (`feat!`) that requires a paired homeassistant/core PR.

Option 1 is the smallest change that removes the race without breaking the
HA contract.

---

## 8. `_parse_return_code` maps unknown `<ret>` codes to `OK` via an accidental `ValueError`

**File:** `ccm15/CCM15Device.py:230-244`
**Severity:** readability
**Suggested PR type:** `refactor` (no behavior change)

```python
try:
    return CCM15ReturnCode(int(match.group(1)))
except ValueError:
    return CCM15ReturnCode.OK
```

The intent — "the web UI only treats 250 as an error; anything else is
accepted" — is correct and documented. But the mechanism is an enum
construction failure being caught as a control-flow device:
`CCM15ReturnCode(251)` raises `ValueError` because 251 is not a member. That
works today, but it couples the "unknown code → OK" policy to the *absence* of
an enum member, and it would silently change behavior if someone added, say,
`CCM15ReturnCode(251)` for a newly discovered code.

**Fix:** make the policy explicit:

```python
code = int(match.group(1))
return CCM15ReturnCode(code) if code in CCM15ReturnCode._value2member_map_ else CCM15ReturnCode.OK
```

or, more readably, a small lookup:

```python
_KNOWN = {0: CCM15ReturnCode.OK, 250: CCM15ReturnCode.WRONG_PASSWORD}
return _KNOWN.get(code, CCM15ReturnCode.OK)
```

---

## Suggested PR plan

| PR | Title (Conventional Commit) | Findings | Bump |
|----|------------------------------|----------|------|
| 1 | `fix: harden status decode and control write error paths` | 1, 2, 3, 5, 6 | patch |
| 2 | `build: raise minimum Python to 3.9` | 4 | none |
| 3 | `fix: clear desired swing/heater after send, not on poll` | 7 (option 1) | patch — **check HA compatibility first** |
| 4 | `refactor: make unknown <ret> handling explicit` | 8 | patch |

PR 3 is the only one that changes observable behavior a consumer can depend
on; it should be reviewed against how `homeassistant/components/ccm15/` sets
and sends `desired_swing`/`desired_heater` before merging, and if the
integration relies on the current reset semantics it should be paired with a
core PR per the policy in CLAUDE.md.
