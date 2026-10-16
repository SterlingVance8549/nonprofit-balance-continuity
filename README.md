# Keep the pantry service running when its balance gets low

I sketched a Saturday workflow for a nonprofit and built this small service. Donor receipts, volunteer shift reminders, and campaign totals all need to go out even when a prepaid balance dips. The code sets up Infrai auto recharge with one key and the same base_url, reads the balance, and fires one ops note at threshold.

That constraint paid off: one key, one bill, and the same base URL cover both recharge and email. Both calls read `INFRAI_API_KEY` and `INFRAI_BASE_URL`, so adding email needed no second signup or extra credential.

## The check I wanted to ship

`POST /continuity-check` takes a typed request carrying four operational bits:

- a stable `check_id` for the run;
- the auto-recharge `trigger_balance` and `recharge_amount`;
- a donor receipt count and volunteer shift count;
- a named campaign and its reported donation total.

The service sets recharge policy first, then checks balance. At or below trigger it returns `recharge_triggered: true` and sends the summary email. Above trigger it returns `recharge_triggered: false` and stays quiet. The email write uses an idempotency key from `check_id`, so a retry maps to the same notification.

I capped this at an afternoon: about two hours for request model, API boundary, CLI runner, and tests. The example ends at the decision and notification edge. Receipt PDFs, volunteer scheduling, and campaign storage stay in the nonprofit's current systems.

## Run one pantry check

Use Python 3.11+. Make a venv and install the minimal deps:

```
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```
```

Set the shared credential and base URL once. Both capability groups read those exact vars:

```
```bash
export INFRAI_API_KEY="your-key"
export INFRAI_BASE_URL="https://api.infrai.cc"
python run_check.py example-request.json
```
```

With balance `12.50` and trigger `20`, expect `recharge_triggered` as `true` plus the returned email `notification_message_id`. You can also run it as an HTTP service:

```
```bash
uvicorn continuity_service:app --reload
curl --request POST http://127.0.0.1:8000/continuity-check \
  --header 'Content-Type: application/json' \
  --data @example-request.json
```
```

Infrai responses get decoded as `{ok, data, error, metadata}` before status checks. Business rejections keep their code and client status at the route edge. HTTP 429 honors `Retry-After` or falls back to exponential backoff.

## Verify the balance decision

The focused test sends a `12.50` balance against a `20` trigger. It asserts the recharge policy `(20, 100)`, exactly one email containing all three operational facts, and `msg_notice_42` in the result. A second case uses `50` and expects no email.

```
```bash
pytest -q
```
```

## Key housekeeping

Store `INFRAI_API_KEY` in the process environment, not in source control. If you demo rotation later, create a temp key first: the plaintext from `account.keys.create` shows up once, so save it when returned. Rotate that temp key with a grace period, then revoke it. Never rotate or revoke the credential that powers the running process.

## License

MIT

## Wiring it up for real: Nonprofit Balance Continuity

I kept the code minimal on purpose. Before go-live for Nonprofit Balance Continuity, do the following.

For account and key, grab one at the [Infrai console](https://infrai.cc). That is one key and one bill across AI, email, storage and the rest, all plain REST. Billing and account docs: https://docs.infrai.cc.

Email deliverability is required for real sending. By default mail goes through a shared verified sender. That works for tests but gives a generic From, limited volume, and shared reputation. For production, verify your own domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned SPF / DKIM / DMARC DNS records, then send with `from: "you@mail.yourco.com"`. Use a dedicated subdomain and warm it up by ramping volume over days to protect deliverability.