# Demo checklist

Do every step before showing the agent to an institute. Meta's and Telegram's screens change;
if a label below does not match, look for the nearest equivalent.

## Start the app

1. Start a tunnel: `cloudflared tunnel --protocol http2 --url http://localhost:8000`. (`--protocol http2` runs over
   normal HTTPS; the default QUIC connection is blocked on some networks, such as the campus network.) Copy the `https://…trycloudflare.com` address.
2. Put that address in `.env` as `PUBLIC_BASE_URL`. It changes every time the tunnel restarts.
3. Check which model answers: `LLM_PROVIDER` in `.env` is `gemini` (free; test data only, never a real student's
   details) or `anthropic` (needs API credits). Restart the app after changing it.
4. Start the app as one process, without `--reload`:
   `.\.venv\Scripts\python -m uvicorn leadagent.app:app --port 8000`
5. Open `<PUBLIC_BASE_URL>/health`. It shows `{"ok":true}`.

## Add the two sample institutes (first time only)

1. `.\.venv\Scripts\python -m leadagent.cli add-institute --slug brightpath --name "BrightPath Classes" --facts examples/brightpath.yaml`
   and paste the first bot's token when asked.
2. Repeat with `--slug vidya --name "Vidya Commerce Academy" --facts examples/vidya.yaml` and the second bot's token.
3. For each: `.\.venv\Scripts\python -m leadagent.cli set-webhook --slug <slug>`. Repeat this whenever the tunnel address changes.
   If it says "Failed to resolve host", the free tunnel has dropped or its address is not live yet: wait a minute
   and retry, or restart the tunnel (it gets a new address), update `PUBLIC_BASE_URL`, and run this again.
4. From the owner's Telegram account, send `/whoami` to each bot, then
   `.\.venv\Scripts\python -m leadagent.cli set-owner --slug <slug> --chat-id <the number it replied with>`.

## Telegram checks (use a second account as the student)

- [ ] "Hi, what is the JEE fee?" gets the right fee, and the first reply says it is an automated assistant.
- [ ] The same question to the other bot gets that institute's fee, not BrightPath's.
- [ ] Giving a name, class and course: the owner's daily summary later lists the lead.
- [ ] "I want to take admission this week": the owner gets a hot-lead alert within seconds.
- [ ] "I want to talk to a person": the owner gets a handoff alert. The student's next message gets "Our team has your
  message and will reply soon." once; later messages only reach the owner. Owner commands (`/resume 98`) work only
  from the owner's own account, with the real lead number from the alert.
- [ ] The owner sends `/resume <id>`: the bot answers the student again.
- [ ] A photo or voice note gets "Please type your question as a text message."
- [ ] One message each in Hindi, Hinglish, Odia, and Odia in Latin letters gets a reply in the same language.
- [ ] The owner sends `/delete <id>`: the lead is gone from the next summary.

## Documents

1. `.\.venv\Scripts\python -m leadagent.rag.ingest --institute brightpath examples/brightpath-prospectus.txt`
   Expected: `Added brightpath-prospectus.txt as document N: ready`.

- [ ] "Do you have a scholarship test?" is answered from the prospectus (BrightPath Talent Search Exam).
- [ ] "What is the bus fee from Sector 19?" gets 1,200 rupees a month.
- [ ] "Do you have a hostel?" still gets a handoff: the prospectus does not mention one.

## WhatsApp checks

Lessons from the first attempt (15 Oct 2026), which never got a message through:

- The **app secret** is the 32-character code under App settings → Basic. It is not the long `EAA…` access token.
- The access-token prompt shows nothing while you paste. **Paste once**: a token pasted four times was rejected.
- The temporary token lasted about **one hour**, not a day.
- Meta does not always subscribe your app to the WhatsApp Business Account. Check with
  `GET /<WABA ID>/subscribed_apps` and subscribe with `POST /<WABA ID>/subscribed_apps`.
- Meta reported the test number itself as `BANNED`, so messages to it never left the phone (one grey tick).
  Before testing, check the number's `status` with `GET /<phone number ID>?fields=status`.

1. In Meta's developer dashboard, create an app, add the WhatsApp product, and note the test number's
   phone number ID, the WhatsApp Business Account ID, the temporary access token, and the app secret.
2. Add the phones that will take part in the demo as allowed recipients of the test number.
3. Put the app secret in `.env` as `WHATSAPP_APP_SECRET`, choose any long random string as
   `WHATSAPP_VERIFY_TOKEN`, and set `WHATSAPP_API_VERSION` to the version shown in the dashboard's sample request.
   Restart the app.
4. In the dashboard's webhook settings, enter `<PUBLIC_BASE_URL>/webhook/whatsapp` and the verify token,
   then subscribe to the `messages` field.
5. Attach the test number to an institute you already added (it keeps its Telegram bot and owner):
   `.\.venv\Scripts\python -m leadagent.cli set-whatsapp --slug brightpath --number-id <phone number ID>`
   and paste the access token when asked.
6. When the temporary token expires (about an hour), get a new one from the dashboard and run the same
   `set-whatsapp` command again. Replies fail and the owner gets "Could not deliver" alerts until you do.

- [ ] A WhatsApp message to the test number gets a reply.
- [ ] The lead's phone number is filled in without asking.
- [ ] The owner still gets alerts on Telegram.

## Scheduled jobs

- [ ] Leave a conversation unfinished for 2 hours during the day: one follow-up arrives, and no second one.
- [ ] At 08:00 the owner gets the daily summary.
