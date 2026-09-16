# Deploying to CML

This repo is structured as a CML Applied ML Prototype (AMP) via
[`.project-metadata.yaml`](../.project-metadata.yaml), so it can be imported
as a CML project in one step. That file (and [`run_app.py`](../run_app.py),
its Application entrypoint) stays at the repository root because CML reads
both from there directly — they are not duplicated or moved into this
folder. This page documents the deployment flow they drive.

1. In your CML workspace, create a new project from this Git repo (push this
   directory to a repo CML can reach first).
2. CML will prompt for the environment variables declared in
   `.project-metadata.yaml`: `TWILIO_AUTH_TOKEN`, `DEEPGRAM_API_KEY`,
   `CARTESIA_API_KEY`, `CAII_BASE_URL`, `CAII_API_KEY`, `CAII_MODEL_NAME`.
   Leave `PUBLIC_BASE_URL` blank for now — the Application's URL isn't known
   until it's first started.
3. On import, CML runs the `install_dependencies` and `seed_customer_data`
   tasks, then starts the `Voice AI Agent` Application.
4. Once running, copy the Application's URL (shown in the CML UI, something
   like `https://voice-ai-agent.<workspace-domain>`). Set it as
   `PUBLIC_BASE_URL` in the Application's environment variables and restart
   it — this is required so Twilio signature validation and the `wss://`
   media-stream URL are computed correctly behind CML's proxy.
5. In the Twilio console, set the phone number's **"A call comes in"**
   webhook to `https://<same-domain>/voice` (HTTP POST).
6. Call the number.

**Note on websockets**: CML's application proxy supports websockets on TLS
workspaces out of the box. If your workspace runs without TLS, its external
load balancer needs websockets explicitly allowed on port 80 — check with
your CML admin if `/media-stream` connections fail to upgrade.

`bypass_authentication: true` is set on the Application because Twilio's
webhook can't complete CML's normal login flow — this makes `/voice` and
`/media-stream` reachable without a CML session. That's compensated by
Twilio request-signature validation in `twilio_gateway.validate_request`, so
requests not actually from your Twilio account are rejected.

## Hardware sizing

Per-task sizing (from `.project-metadata.yaml`):

| Task | CPU | Memory |
| --- | --- | --- |
| Install dependencies | 1 | 2 GB |
| Seed mock customer dataset | 1 | 2 GB |
| Voice AI Agent (Application) | 2 | 4 GB |

This app itself only orchestrates HTTP/websocket calls to external
services — it does no local inference, so it has no GPU requirement of its
own. The LLM is a separate Cloudera AI Inference Service deployment, whose
sizing depends entirely on the model you choose there (see your workspace's
Cloudera AI Inference Service docs for model-specific GPU/memory sizing).

## Audio/speaker requirements

This is a phone-call demo, not a browser audio demo: the caller and the
agent's voice both go through the actual PSTN/Twilio call, not the machine
running CML. There's no local speaker or microphone requirement on the CML
side. What you do need:

- A phone (mobile or landline) to place the demo call on.
- If you're presenting the `/dashboard` page live alongside the call, a
  screen to show it on — the dashboard is visual only and doesn't play
  audio itself.
