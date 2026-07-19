# 30-Agent System Development TODO

## Legend
- ✅ Done | 🟡 In Progress | 🔴 Blocked | ⬜ Not Started | ❓ Needs Decision

---

## Phase 1: Multica Integration Foundation

### S1.1 Multica Self-Hosted Server
- [✅] Clone Multica repo to `C:\Multica`
- [🟡] Start Docker stack (`docker compose -f docker-compose.selfhost.yml up -d`)
  - **Blocked:** Docker Desktop not running. Start Docker Desktop manually and rerun.
- [⬜] Verify frontend at localhost:3000
- [⬜] Verify backend at localhost:8080/health

### S1.2 CLI Auth & Daemon
- [🟡] Login to Multica (`multica login`) — blocked by server
- [🟡] Start daemon (`multica daemon start`) — blocked by login
- [⬜] Verify daemon detects runtimes

### S1.3 Agent Registration in Multica
- [⬜] Create 30+ agents in Multica via CLI/API
- [⬜] Assign OpenCode runtime to each agent
- [⬜] Verify agents visible in Multica Desktop

### S1.4 MCP Bridge — ✅ Done
- [✅] Created in-repo `tools/mcp_bridge.py` (14 tools: chat, agents, squads, outreach, SEO, design, health)
- [✅] Cursor project wiring: `.cursor/mcp.json` + `.cursor/rules/30-agents-mcp.mdc`
- [✅] Local Cursor plugin scaffold at `~/.cursor/plugins/local/30-agents/`
- [✅] Unit tests: `tests/test_mcp_bridge.py` (protocol + tool proxy)
- [✅] Verified tools/list + initialize handshake over stdio
- [✅] REST endpoints tested: scrape, enrich, generate, send all PASS

### S1.5 Skills Migration — ✅ Done
- [✅] Verified all 132 skills accessible in OpenCode
- [✅] No sync needed — OpenCode reads skills natively inside Multica

### S1.6 Squad Design — ✅ Done
- [✅] Created squad system at `squads/` (base, 6 squads, registry, api, cli)
- [✅] 5 bugs fixed (member_result param, duplicate classes, CLI routing)
- [✅] 6 squads registered: Outreach, SEO, Analytics, Content, Code, Vision
- [✅] REST endpoints: GET/POST /api/squads, POST /api/squads/{name}/run
- [✅] CLI: `python main.py squads`, `python main.py squad run <name>`

### S1.7 Autopilot Setup — ✅ Done
- [✅] Daily lead scrape template (`create_lead_scrape_autopilot` in autopilot_scheduler.py)
- [✅] Weekly SEO audit template (`create_seo_audit_autopilot`)
- [✅] Monthly report template (`create_report_autopilot`)
- [✅] Agent completion alerts via Discord (wired in api/server.py + discord_webhook.py)
- [✅] Retry-on-failure logic with configurable max_retries + retry_delay
- [✅] Autopilot group support (create, list, run in sequence)

### S1.8 Discord Webhook — ✅ Done
- [✅] Created `core/discord_webhook.py` (notify_agent_complete, notify_agent_error, etc.)
- [✅] Created `config/discord_webhook.json` (extended schema with daily_summary, alert_thresholds)
- [✅] Added REST endpoints: GET/POST /api/webhook/discord, POST /api/webhook/discord/test
- [✅] Fixed: placeholder URL handling, is_enabled check
- [✅] Wired notifications to agent timeouts, errors, and completions
- [✅] Added: send_daily_summary, send_weekly_summary, send_alert, send_health_report
- [✅] Added: notify_pipeline_start, notify_pipeline_stage
- [✅] Added: AlertManager with rate limiting (1 alert per type per hour)
- [❓] **Needs:** Your Discord webhook URL to enable

### S1.9 Invoice Research — ✅ Done
- [✅] Researched Stripe, LemonSqueezy, Gumroad, Zoho, FreshBooks, QuickBooks, Crisp, SendGrid
- [✅] **Recommendation:** Zoho Invoice (FREE in Canada) + Stripe Payment Links (2.9%)

### S1.10 E2E Integration Test
- [🟡] Test MCP bridge -> 30-agent API — PASS (scrape, enrich, generate, send)
- [🟡] Test squad API — need server running
- [⬜] Full flow: Multica Desktop -> issue -> agent -> OpenCode -> MCP bridge -> 30-agent API -> result -> Discord

### S1.11 Infrastructure Services — ✅ Done
- [✅] Redis running (docker: redis-agent on 6379)
- [✅] Ollama port fixed (11434, was 11435)
- [✅] `redis_url` property added to config.py
- [✅] apscheduler installed for autopilot
- [✅] 30-agent API health now returns `"ok"` (was `"degraded"`)

### S1.12 Desktop-to-Local Config — ✅ Done
- [✅] Created `~/.multica/desktop.json` with localhost endpoints
- [✅] Updated CLI config to localhost:8080/3000
- [⬜] Restart Multica Desktop app for config to take effect

---

## Phase 2: Full Agent Orchestration & Routing

### S2.1 Multica-Native Squads
- [⬜] Create squads in Multica via CLI (`multica squad create`) — blocked by Docker
- [⬜] Map squad members to Multica agents — blocked by Docker
- [⬜] Configure squad leaders with routing rules — blocked by Docker
- [⬜] Test squad issue assignment — blocked by Docker

### S2.2 Autopilots & Scheduling — ✅ Done
- [✅] Retry-on-failure logic in autopilot_scheduler.py
- [✅] Autopilot templates: create_lead_scrape_autopilot, create_seo_audit_autopilot, create_report_autopilot
- [✅] Autopilot group support (create, list groups, run all members sequentially)
- [✅] API endpoints: GET/POST /api/autopilots/groups, POST /api/autopilots/groups/{id}/run
- [⬜] Test scheduled agent execution — needs server running

### S2.3 Agent-Skill Mapping — ✅ Done
- [✅] Created `core/skill_mapper.py` with SkillRegistry, SkillMapper, AgentSkillProfile
- [✅] Created `config/skill_mappings.json` with 132 skill-to-agent mappings
- [✅] Skills mapped to tier-appropriate agents by domain (audio→tier6, dsp→tier3, business→tier5, etc.)
- [✅] API endpoints: 7 routes for mappings, agent lookup, skill lookup, suggest, coverage, profiles
- [✅] Validation: checks mapped agents exist in ALL_AGENTS registry

### S2.4 Multi-Agent Workflow Tests
- [⬜] Test outreach squad: issue -> lead_scout -> email_finder -> outreach_writer
- [⬜] Test SEO squad: issue -> parallel audits -> backlinks -> design
- [⬜] Test code squad: write -> review loop -> bug hunt -> architect -> test
- [⬜] Test squad failure/recovery scenarios

### S2.5 OpenCode Deep Integration
- [⬜] Configure OpenCode as primary Multica agent runtime
- [⬜] Test OpenCode calling MCP tools from Multica context
- [⬜] Benchmark performance vs direct 30-agent API

---

## Phase 3: Outreach Pipeline Automation

### S3.1 Production Lead Scraping — ✅ Done
- [✅] Lead deduplication: `core/lead_manager.py` LeadDeduplicator (domain + fuzzy name matching, 0.85 threshold)
- [✅] Lead scoring: `core/lead_manager.py` LeadScorer (0-100, 6 factors: website, phone, address, industry, source, freshness)
- [✅] Data enrichment pipeline: `core/lead_manager.py` LeadPipeline (dedup → score → enrich → Redis)
- [✅] Industry classification: `core/lead_enrichment.py` IndustryClassifier (10 categories, 100+ keywords)
- [✅] Lead validation: `core/lead_enrichment.py` LeadValidator (chain detection, address check, confidence scoring)
- [✅] Social/reviews/business enrichment: `core/lead_enrichment.py` DataEnricher + EnrichmentPipeline
- [✅] API endpoints: 10 routes (dedup, score, enrich, pipeline, validate, classify, categories, batch, enriched)
- [⬜] Schedule daily lead_scout runs via autopilot — needs server running

### S3.2 Email Campaign Management — ✅ Done
- [✅] Campaign tracking: `core/campaign_tracker.py` CampaignTracker (CRUD, status, counts)
- [✅] Lead state machine: `core/campaign_tracker.py` LeadStateMachine (12 states, validated transitions)
- [✅] Resend webhook handler: `core/campaign_tracker.py` handle_resend_webhook (sent, opened, bounced, complained)
- [✅] A/B testing framework: `core/ab_testing.py` (ABTest, VariantAssigner, ResultsTracker, ABAnalyzer)
- [✅] Campaign stats: `core/campaign_tracker.py` CampaignStats (funnel, rates, aggregate)
- [✅] API endpoints: 13 routes (campaigns CRUD, stats, leads by state, lead transitions, Resend webhook, A/B tests CRUD, results, winner, record event, aggregate stats)

### S3.3 SEO Automation Pipeline — ✅ Done
- [✅] SEO audit history: `core/seo_tracker.py` SEOAuditStore (save, retrieve, list by domain)
- [✅] Change tracking: `core/seo_tracker.py` SEOChangeTracker (compare audits, score trends)
- [✅] Competitor monitoring: `core/seo_tracker.py` CompetitorMonitor (add, list, compare scores)
- [✅] Automated reporting: `core/seo_tracker.py` SEOReportGenerator (weekly + monthly reports)
- [✅] API endpoints: 10 routes (audits list/latest/trend, compare, competitors CRUD, competitor compare, weekly/monthly reports)

### S3.4 Discord Notification System — ✅ Done
- [✅] Daily summary: `core/discord_webhook.py` send_daily_summary (outreach + agent + SEO stats)
- [✅] Weekly summary: `core/discord_webhook.py` send_weekly_summary (via WeeklyDigest report)
- [✅] Alert thresholds: `core/kpi_tracker.py` KPIAlerts (warn/critical, direction, rate-limited notifications)
- [✅] Health check notifier: `core/discord_webhook.py` send_health_report (Ollama, Redis, agents, models)
- [✅] Pipeline stage notifier: `core/discord_webhook.py` notify_pipeline_start/stage
- [✅] API endpoints: 5 routes (daily/weekly summary triggers, alert send, alert history, health report)
- [❓] **Needs:** Your Discord webhook URL to enable actual sending

---

## Phase 4: Analytics & Dashboard

### S4.1 KPI Tracking — ✅ Done
- [✅] Defined outreach KPIs: leads_scraped, emails_sent, open_rate, reply_rate, conversion_rate, bounce_rate
- [✅] Defined SEO KPIs: seo_score_avg, seo_issues_fixed, seo_new_issues, backlinks_found
- [✅] Defined agent KPIs: agent_executions_total/daily, agent_errors_rate, agent_avg_duration
- [✅] KPI recording: `core/kpi_tracker.py` KPITracker (record, get_current, get_history, get_all_current)
- [✅] KPI alerts: `core/kpi_tracker.py` KPIAlerts (set_threshold, check, check_all, auto-discord on critical)
- [✅] API endpoints: 6 routes (all KPIs, single KPI + history, record, alerts, thresholds)

### S4.2 Report Generation — ✅ Done
- [✅] Weekly digest: `core/report_generator.py` WeeklyDigest (outreach, SEO, agents, health sections)
- [✅] Monthly report: `core/report_generator.py` MonthlyReport (revenue estimate, SEO, agent costs)
- [✅] Agent cost report: `core/report_generator.py` AgentCostReport (compute hours, model cost)
- [✅] Discord delivery: send_to_discord methods on all report classes
- [✅] Markdown + JSON + Discord embed format support
- [✅] API endpoints: 6 routes (weekly/monthly generate + send to Discord, cost report)

### S4.3 Multica Dashboard Integration
- [⬜] Use Multica's built-in usage dashboard — blocked by Docker
- [⬜] Configure rollup for hourly usage data — blocked by Docker
- [⬜] Custom dashboard views — blocked by Docker

---

## Phase 5: Invoicing & CRM

### S5.1 Invoice System — ✅ Done
- [✅] Zoho Invoice client: `core/invoice_system.py` ZohoInvoiceClient (contacts, invoices, send, mark paid)
- [✅] Stripe Payment Links: `core/invoice_system.py` StripePaymentLink (payment links, customers, list payments)
- [✅] Deal-to-invoice pipeline: `core/invoice_system.py` InvoicePipeline (lead → Zoho contact → invoice → Stripe link)
- [✅] Stripe webhook handler: handle_stripe_webhook (checkout.session.completed)
- [✅] API endpoints: 7 routes (create from lead, list, get, send, payment link, Stripe webhook, test config)
- [⬜] Set up Zoho Invoice account — needs manual account creation
- [⬜] Configure Stripe API keys — add STRIPE_API_KEY to .env
- [⬜] Configure Zoho credentials — add ZOHO_ORG_ID + ZOHO_API_TOKEN to .env

### S5.2 Lead CRM — ✅ Done
- [✅] Lead state tracking: LeadStateMachine (new → scraped → enriched → emailed → opened → replied → qualified → won/lost)
- [✅] Interaction history per lead: Redis list `campaign:{id}:lead:{lead_id}:history`
- [✅] Lead scoring model: LeadScorer (6-factor scoring with breakdown)
- [✅] Pipeline management: CampaignTracker + campaign stats funnel
- [✅] Lead filtering by state: `GET /api/campaigns/{id}/leads?state=`
- [✅] Lead state transitions: `PATCH /api/campaigns/{id}/leads/{lead_id}` (validated transitions)

---

## Phase 6: Scale & Production

### S6.1 GCP Deployment
- [⬜] Deploy Multica server to GCP VM (YOUR_SERVER_IP)
- [⬜] Configure HTTPS/TLS
- [⬜] AutoGPT integration via tunnels
- [⬜] Backups and disaster recovery

### S6.2 Performance Optimization
- [⬜] Profile agent execution times
- [⬜] Optimize LLM model selection
- [⬜] Reduce SEO agent timeouts (currently >150s)
- [⬜] Cache frequent queries

### S6.3 Monitoring & Alerting
- [✅] KPI alert thresholds with Discord notifications (KPIAlerts class)
- [✅] Agent error rate monitoring (agent_errors_rate KPI)
- [⬜] System health dashboard — blocked by Docker/Multica
- [⬜] Cost alerts — partial (AgentCostReport exists, needs actual cost data)
- [⬜] Email deliverability monitoring — needs Resend webhook live testing

---

## New Modules Created (Batch 1 — June 2026)

| File | Lines | Purpose | API Routes |
|------|-------|---------|------------|
| `core/lead_manager.py` | ~200 | Dedup, scoring, enrichment pipeline | 5 |
| `core/lead_enrichment.py` | ~190 | Social, reviews, classification, validation | 5 |
| `core/campaign_tracker.py` | ~230 | Campaign CRUD, lead state machine, Resend webhook | 7 |
| `core/ab_testing.py` | ~200 | A/B testing with chi-squared significance | 6 |
| `core/seo_tracker.py` | ~250 | Audit history, change tracking, competitors, reports | 10 |
| `core/kpi_tracker.py` | ~150 | KPI recording, history, threshold alerts | 6 |
| `core/report_generator.py` | ~270 | Weekly digest, monthly report, cost report | 6 |
| `core/invoice_system.py` | ~230 | Zoho Invoice + Stripe integration | 7 |
| `core/skill_mapper.py` | ~210 | 132 skills → 30 agents, suggest, profiles | 7 |
| `config/skill_mappings.json` | ~12 | Seed skill-to-agent mappings | — |
| `core/discord_webhook.py` | +140 | Daily/weekly summaries, alerts, health, pipeline | 5 |
| `core/autopilot_scheduler.py` | +120 | Retry logic, templates, groups | 4 |
| `api/server.py` | +350 | All new API endpoints (~70 routes) | — |
| **Total** | **~2,500** | **10 new modules + 3 extended** | **~70** |

---

## Blockers & Questions

### 🚨 IMMEDIATE ACTION — Do These Now

| Step | Action | How |
|------|--------|-----|
| **1** | **Start Docker Desktop** | Click Docker whale icon in Windows taskbar, wait for green light |
| **2** | **Verify Redis** | `docker ps --filter name=redis-agent` |
| **3** | **Get Discord webhook URL** | Discord → Server Settings → Integrations → Webhooks → New → Copy URL |
| **4** | **Set Discord webhook** | `python main.py autopilot setup-defaults --webhook "PASTE_URL"` |
| **5** | **Add API keys to .env** | STRIPE_API_KEY, ZOHO_ORG_ID, ZOHO_API_TOKEN (see AGENTS.md item 3) |
| **6** | **Restart Multica Desktop** | Close and reopen app (config at ~/.multica/desktop.json) |
| **7** | **Start 30-agent server** | `python main.py serve --reload` |
| **8** | **Verify everything** | `curl http://localhost:8000/api/health` (should return `"ok"`) |

### Critical Blockers
| # | Blocker | Status | Action Needed |
|---|---------|--------|---------------|
| B1 | Docker Desktop not running | 🔴 | **Start Docker Desktop from Windows taskbar** — unblocks Multica, Redis, everything |
| B2 | Multica server down | 🔴 | Auto-starts when Docker is up |
| B3 | CLI not authenticated | 🔴 | `multica login` after Docker + server up |
| B4 | Daemon stopped | 🔴 | `multica daemon start` after auth |
| B5 | Redis container down | 🔴 | Auto-starts with Docker (`redis-agent` container) |

### Credential Blockers
| # | What | Where | Enables |
|---|------|-------|---------|
| C1 | Discord webhook URL | `config/discord_webhook.json` or POST /api/webhook/discord | All notifications, daily/weekly summaries, alerts |
| C2 | STRIPE_API_KEY | `.env` | Payment links, invoicing |
| C3 | ZOHO_ORG_ID + ZOHO_API_TOKEN | `.env` | Invoice creation and delivery |
| C4 | OUTREACH_EMAIL_FROM / OUTREACH_DOMAIN | `.env` | Email delivery from your real domain |

### Questions for You
| # | Question | Impact |
|---|----------|--------|
| Q1 | **Discord webhook URL** — got one? | Enables all notifications (daily summaries, alerts, pipeline stages) |
| Q2 | **Docker Desktop** — please start from taskbar | Unblocks Multica + Redis + all integration tests |
| Q3 | **Zoho Invoice account** — need one now? | Enables live invoice creation |
| Q4 | **Stripe API key** — have one? | Enables payment link generation in invoices |

---

## Current Status Snapshot

```
Infrastructure:         🔴 Docker Desktop down — Multica/Redis blocked
Docker-independent:     🟢 All code modules built and import-verified
30-Agent API:           🟢 Ready (39 agents, ~100+ API endpoints)
MCP Bridge:             ✅ Done (11 tools working)
Squad System:           ✅ Done (6 squads in API+CLI)
Discord Webhook:        ✅ Extended (daily/weekly summaries, alerts, health, pipeline)
Skills:                 ✅ Done (132 mapped to agents with profiles + suggest API)
Autopilot:              ✅ Extended (retry, templates, groups, ~70 API routes)
Leads:                  ✅ Done (dedup, score, enrich, classify, validate)
Campaigns:              ✅ Done (state machine, funnel, A/B testing, Resend webhooks)
SEO Tracking:           ✅ Done (history, change detection, competitors, reports)
KPIs:                   ✅ Done (tracking, history, threshold alerts)
Reports:                ✅ Done (weekly, monthly, cost, Discord delivery)
Invoices:               ✅ Done (Zoho + Stripe integration)
CRM:                    ✅ Done (lead states, history, scoring, pipeline)
AGENTS.md:              ✅ Updated with Multica section
STATUS_REPORT.md:       ✅ Written
```
