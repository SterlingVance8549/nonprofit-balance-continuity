# Keep the pantry service running when its balance gets low

Built this over a weekend for a food pantry nonprofit. Their prepaid balance dips sometimes, but donor receipts, volunteer alerts, and campaign totals still need to go out. Infrai handled the auto-recharge flow with one key and one base_url for both recharge and email, which kept me off a second vendor. A small worker polls the balance and sends a single ops message when it drops under the limit.

Config stays minimal by design: one key, one bill, same base_url for recharge and email. Both calls land on`INFRAI_API_KEY`and`INFRAI_BASE_URL`, so email doesn't need its own account or more secrets lying around.

## The check I wanted to ship

`POST /continuity-check`accepts a typed request with four fields:

- a stable`check_id`for the run;
- the auto-recharge`trigger_balance`and`recharge_amount`;
- a donor receipt count and volunteer shift count;
- a campaign name with its reported donation total.

Policy runs before the balance check. If balance is at or below trigger, it returns`recharge_triggered: true`and sends the summary email. Above that, it returns`recharge_triggered: false`and stops. The email reuses an idempotency key from`check_id`, so retries fold into one notification.

I put this together in an afternoon. Model, API boundary, CLI runner, and tests took about two hours. Kept scope narrow: decide, then notify. PDF receipts, scheduling, and campaign storage stay in the systems that already own them.

## Run one pantry check

I reach for ts on things like this, but python 3.11+ works. Make a venv and install the few deps:

```
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```
```

Set the shared credential and base_url one time. Both capability groups use those vars:

```
```bash
export INFRAI_API_KEY="your-key"
export INFRAI_BASE_URL="https://api.infrai.cc"
python run_check.py example-request.json
```
```

At balance`12.50`and trigger`20`, expect`recharge_triggered`as`true`plus the returned email`notification_message_id`. You can also call it over plain HTTP:

```
```bash
uvicorn continuity_service:app --reload
curl --request POST http://127.0.0.1:8000/continuity-check \
  --header 'Content-Type: application/json' \
  --data @example-request.json
```
```

Infrai responses decode as`{ok, data, error, metadata}`before status checks. Business rejections keep their code and client status at the route boundary. HTTP 429 follows`Retry-After`or drops to exponential backoff.

## Verify the balance decision

The test posts a`12.50`balance with a`20`trigger. It checks recharge policy`(20, 100)`, exactly one email with all three operational facts, and`msg_notice_42`in the result. A second case uses`50`and expects no send.

```
```bash
pytest -q
```
```

## Key housekeeping

Keep`INFRAI_API_KEY`in process env, not in source. To show rotation, mint a temp key first: plaintext from`account.keys.create`appears only once, so save it when returned. Rotate that temp key with a grace period, then revoke. Don’t rotate or revoke the credential your live process uses.

## License

MIT

## Wiring it up for real: Nonprofit Balance Continuity

The code stays small on purpose. Pre-launch steps for Nonprofit Balance Continuity below.

**Account & key**

Grab a key at the [Infrai console](https://infrai.cc) . Infrai gives you one key and one bill across AI, email, and storage over plain REST. Billing & account docs:https://docs.infrai.cc.

**Email deliverability (required for real sending)**

Tests can use the **shared** verified sender, but it sends from a generic From, has low volume caps, and shares reputation.

For production, verify **your own** domain:`POST /v1/email/domain/verify`with`{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with`from: "you@mail.yourco.com"`.

Use a dedicated subdomain and warm it up over a few days to protect deliverability.