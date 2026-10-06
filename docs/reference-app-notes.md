# Reference app: kept, changed, thrown away

Reference: `awesome-llm-apps/voice_ai_agents/insurance_claim_live_agent_team`. It uses FastAPI with a WebSocket, Gemini Live for voice and camera, Gemini Flash for fact extraction and photo checks, an ADK graph for intake rules, a field notebook, and a ZIP adjuster packet.

> **Status:** the notes below come from reading its code. TODO before submission: run it locally and add
> what we observed (latency, how its notebook updates).

## Kept
- **The interaction pattern.** A claimant talks with the camera on, and the claim file builds on screen in real time.
- **Gemini Live for full-duplex voice with barge-in**, using an ephemeral token so the API key never reaches the browser.
- **Non-blocking background work.** Live tool calls return immediately; heavy work runs off the conversation's critical path. Urgent findings interrupt the conversation as injected context.

## Changed
- **Transport.** The browser talks to Gemini Live directly. The backend gets keyframes over plain HTTP and pushes results back over SSE, so voice latency does not depend on our server.
- **Vision.** "Describe the damage in a frame" became detect → read → track → measure: boxes, verbatim text, cross-frame identity and metric geometry, each a separate testable stage.
- **The agent's job.** It directs the capture (targets, re-captures, blur/glare warnings) instead of interviewing about an incident.
- **The packet.** A narrative notebook became a strict schema (`claim_packet.json`) whose totals are computed in code, plus a review queue.

## Thrown away
- **Policy lookup, mock policy directory and intake rules.** The brief says none of these are scored.
- **Incident sketch generation and the avatar.**
- **ADK graph orchestration.** Our stages are plain async functions with explicit inputs and outputs, which is easier to test and to explain line by line.
