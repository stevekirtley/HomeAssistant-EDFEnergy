# Power Perks relay

EDF announce Flextras Power Perks free electricity sessions by SMS the day before, and
nowhere else. There is nothing in the Kraken API, the edfenergy.com APIs, or the mobile
app (its Power Perks screen is a fixed "Free Electricity is auto-applied when available"
banner, and the app source contains no event fetch at all). The only machine-readable
signal is the text on the phone that holds the account's registered mobile number.

This relay turns that text into a JSON feed the integration polls:

```
iPhone Shortcut ──POST text──▶ power_perks.php ──parse──▶ cache/*.json ──GET──▶ integration
```

Hosting it on a server rather than posting straight to Home Assistant means a text is
never lost while Home Assistant is down, and every user of the integration gets the
sessions, not just the phone owner.

## Deploy

One file. Copy `power_perks.php` next to the existing relay, make sure `cache/` is
writable by the web server, and create `config.php` with a long random token:

```
scp power_perks.php steve@thoughtful:/www/live/apirelay/power_perks.php
ssh steve@thoughtful 'cd /www/live/apirelay && printf "<?php\nreturn [\"ingest_token\" => \"%s\"];\n" "$(openssl rand -hex 24)" > config.php && chmod 644 config.php'
```

`config.php` must be readable by the web server user, not just your own, or ingest
silently stays disabled. Check with:

```
curl https://apirelay.sitetest.org.uk/power_perks.php?action=health
```

`ingest_enabled` and `cache_writable` should both be true.

## Actions

| Action | Method | Auth | Purpose |
|---|---|---|---|
| `ingest` | POST `{text, received_at?, sender?}` | token | Store and parse one text. Re-sending the same text is a no-op. |
| `sessions` | GET | integration user agent or token | The parsed sessions, last 60 days onward. What the integration polls. |
| `parse` | GET `?text=...&received_at=...` | none | Dry-run the parser without storing anything. |
| `messages` | GET | token | Every stored text with its parse result, for debugging. |
| `health` | GET | none | Liveness, counts, and whether ingest is configured. |

The token goes in an `X-Token` header or a `token` query parameter.

The sessions feed is served only to requests whose `User-Agent` starts with
`stevekirtley-ha-edf-energy/` (the integration's), or that carry the token. The
integration is open source so this is a deterrent, not a lock, but it keeps the feed out
of casual scrapers and other projects. A per-address rate limit (30 requests per 5
minutes by default) keeps any copying cheap. Both are adjustable in `config.php` via
`feed_user_agent_prefix`, `rate_limit_requests` and `rate_limit_window_seconds`.

## The parser

EDF reword their messages, so the parser keys on three things only:

- the words "Power Perks" (any spacing or hyphenation, any case),
- a date: `19 September`, `19th Sept 2026`, `September 19`, `19/09`, or `today`,
  `tomorrow`, `tonight`, or a weekday name, all resolved against when the text arrived,
- a time window: `4am-4pm`, `4am to 4pm`, `between 4am and 4pm`, `04:00-16:00`,
  `11.30am`, `4 p.m.`, `midday`, `noon`, `midnight`, with any dash character. A missing
  am/pm on one side is inferred from the other (`4-4pm` is 04:00-16:00).

A text without all three is stored with a `parse_error` and produces no session. Times
are UK local and published with their offset. Run the tests with `php tests.php`.

If the parser misses or misreads a text, fix it without a code change by editing
`cache/power_perks_overrides.json` on the server:

```json
[
  {"code": "power_perks_202609190400", "start": "2026-09-19T04:00:00+01:00", "end": "2026-09-19T16:00:00+01:00"},
  {"code": "power_perks_202609200400", "remove": true}
]
```

Overrides win on a code clash. The integration also has a
`edf_energy.register_power_perks_session` action for a purely local fix.

## The iPhone Shortcut

On the phone with the registered mobile number, in the Shortcuts app:

1. Automation tab, **+**, **Message**.
2. Sender: **EDFINFO**. Message contains: **Power Perks**. Set **Run Immediately** and
   turn off **Notify When Run**.
3. Add a **Get Contents of URL** action:
   - URL: `https://apirelay.sitetest.org.uk/power_perks.php?action=ingest`
   - Method: **POST**
   - Headers: `X-Token` = the token from `config.php`
   - Request Body: **JSON** with `text` = **Shortcut Input** (the message content) and,
     optionally, `received_at` = **Current Date** (formatted ISO 8601) and
     `sender` = `EDFINFO`.

Test it by texting yourself the words "Power Perks tomorrow 4am-4pm" from a contact
renamed EDFINFO, or by calling `ingest` with curl. Then check `?action=sessions` with
the integration's user agent:

```
curl -A "stevekirtley-ha-edf-energy/test" "https://apirelay.sitetest.org.uk/power_perks.php?action=sessions"
```

Message automations only run while the phone is on and connected, so if a text arrives
while the phone is off it is ingested when the phone wakes, and the integration picks it
up on its next 15 minute poll.
