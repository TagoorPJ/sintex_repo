# Changes — QR upload + Create Claim flow fix

This document describes everything that changed in the Sintex agent
codebase to make the QR Upload and Create Claim flows reliable and
language-aware.

If you only read one section, read **"Why the LLM is no longer
involved"** below — that's the headline change.

---

## TL;DR

- The QR Upload flow and the Create Claim flow are now run by a small
  deterministic Python state machine (`app/upload_flow/`), not by the
  LLM agent.
- This guarantees the `dealer_code` the user picked from the fuzzy-match
  list is the **exact** code that goes into the QR scanner URL or into
  the `claim/create` API payload — no paraphrasing, no hallucination.
- All four supported languages (English, Hindi, Marathi, Hinglish) have
  hard-coded message templates for every step of the flow.
- Three pre-existing tools had hardcoded test values (`user_id=127329`,
  `retailerMerchantId="8182"`). Those are removed.
- The Claim Status flow (option 3 of the Upload Purchase sub-menu) is
  unchanged — it's still handled by the LLM agent, exactly as before.
- All other flows (registration, rewards, main menu, language change,
  language detection) are untouched.

A standalone smoke test (`test_upload_flow.py`) walks both flows end to
end with mocked HTTP. Run it with `python3 test_upload_flow.py`.

---

## File-by-file changes

### Tools — hardcoded test values removed

**`app/tools/find_dealer_tool.py`** — removed
```python
user_id = "127329"  # hardcoded for now ...
```
The function now uses the actual `user_id_evolve` argument.

**`app/tools/create_claim_tool.py`** — removed both
```python
user_id = 127329
retailerMerchantId = "8182"
```
The function now sends the actual user id and the actual dealer_code.

**`app/tools/claim_status_tool.py`** — removed
```python
user_id = 127329
```
Now uses the actual `user_id_evolve` argument.

### New module — `app/upload_flow/`

A new package that owns the QR + Create Claim flow end-to-end.

- **`messages.py`** — hard-coded user-facing strings in English, Hindi,
  Marathi and Hinglish for every step of the flow (sub-menu, ask firm
  name, numbered match list, invalid serial, ask amount, success,
  failure, cancel). No LLM call is needed to render any of these.
- **`dealer_service.py`** — direct (non-LangChain) async wrappers
  around `find-dealer` and `claim/create`. Same fuzzy-match logic as
  the legacy tool (rapidfuzz, score >= 0.65, top 10). Caches the dealer
  list for 30 minutes per user.
- **`handler.py`** — the deterministic state machine. Every transition
  is documented inline with a comment.

### Wiring — `app/api/routes/chat.py`

A new step "9.5 UPLOAD-PURCHASE DETERMINISTIC HANDLER" was added
between language detection and the LLM agent call. It:

1. Computes the user's last assistant message (so a "2" reply can be
   recognised as a main-menu pick).
2. Calls `upload_flow_handler.handle(...)`.
3. If the handler claims the turn (`handled=True`), the LLM agent is
   skipped entirely; the handler's reply is saved and returned.
4. Otherwise, the request falls through to the existing LLM agent
   path, exactly as before.

The handler's flow state is persisted as a JSON blob inside the
existing `Conversation.match_results_json` Text column, so **no DB
schema migration is needed**.

When the LLM path runs, `match_results_json` is now filtered: only the
legacy list shape is forwarded to the LLM (so the prompt never sees the
upload-flow state blob).

### Prompt — `app/prompt_library/prompt.py`

The four "UPLOAD PURCHASE — ..." sections (~230 lines) that used to
walk the LLM through find_dealer_tool MODE 1 / 2 / 3 and create_claim
have been replaced by a much shorter section telling the LLM:

- The Upload Purchase sub-menu is rendered by the backend; do not
  render it yourself.
- The Scan QR and Create Claim flows are handled by the backend; do
  not call find_dealer_tool or create_claim_tool.
- Never construct or paraphrase a QR scanner URL.
- The Claim Status flow (option 3) IS still your job — use
  claim_status_tool with the user's invoice id.

All other prompt sections (registration, rewards, main menu) are
unchanged.

---

## Flow walkthrough

### QR Upload

1. User sees the main menu (rendered by the LLM in their language).
2. User types "2" (or the Devanagari "२").
3. Handler renders the Upload Purchase sub-menu in the user's language.
4. User types "1" (Scan QR).
5. Handler calls `find-dealer` API with the real `user_id_evolve`,
   caches up to 500 dealers, asks "Please type your dealer firm name."
6. User types e.g. "ram".
7. Handler runs rapidfuzz against the cached list, returns the top 10
   matches as a numbered list, asks for the serial number.
8. User types e.g. "2".
9. Handler picks the dealer at serial 2, builds the QR URL
   deterministically with `urllib.parse.quote_plus`:
   ```
   <base>/scanner?user_id_evolve=<id>&whatsapp_number=<mobile>&dealer_code=<code>
   ```
10. Handler renders the QR link in the user's language and ends the flow.

### Create Claim

Steps 1 to 7 are identical (just option "2" instead of "1" at step 4).
Then:

8. User picks a dealer serial.
9. Handler asks "Please enter the purchase amount in rupees."
10. User types e.g. "1500" (or "१५००").
11. Handler calls `claim/create` with the real `user_id_evolve`, the
    selected `dealer_code` and the parsed amount.
12. Handler renders the success or failure message in the user's
    language and ends the flow.

---

## Why the LLM is no longer involved

The previous design relied on the LLM to:

- Remember to pass the cached match list back as the `cached_dealers`
  argument on the third tool call.
- Call `find_dealer_tool` in the right MODE (1, 2, or 3) based on
  conversation context.
- Not paraphrase or invent dealer codes.
- Render every prompt question in the right language.

With a 500-dealer list and a fuzzy match step in between, this was
unreliable in practice — the LLM occasionally invented a dealer code,
re-asked for the firm name after the user had already picked a serial,
or summarised the numbered list instead of showing it verbatim.

The deterministic handler eliminates all of those failure modes
because it never calls the LLM for any step of the flow that depends
on a `dealer_code`.

---

## What's still LLM-driven (unchanged)

- Main menu rendering (in user's language)
- Registration
- My Rewards (rewards_tool, reward_statement_tool)
- See Claim Status (claim_status_tool)
- Language change detection
- Off-topic intent detection

---

## Edge cases handled

- Devanagari digits (२, १५००) are silently converted to ASCII before
  validation.
- Invalid serial number → re-prompt, do not advance.
- Invalid amount → re-prompt, do not advance.
- No fuzzy match → ask the user to try again, stay on the same stage.
- "cancel" / "back" / "menu" while inside the flow → reset state and
  send a short cancellation message.
- User has zero dealers → graceful "no dealers linked" message.
- Unregistered user → handler does not intercept; the LLM-driven
  registration flow continues as before.
- Session resume / "hi" / "hello" / "start" → handler state is wiped
  in both memory and DB so the next turn starts clean.

---

## Running the smoke test

```bash
cd <project root>
pip install -r requirements.txt
python3 test_upload_flow.py
```

Expected output ends with `[OK] All scenarios passed.`.
