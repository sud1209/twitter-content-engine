# Sud (@laajardni) — X Posts Strategy
**Version:** 1.0 | 2026-03-23

---

## CONTENT PILLARS

| Pillar | Core angle | Audience |
|---|---|---|
| **AI Innovations** | Cuts through hype with specific, falsifiable observations. Cross-domain applications. | Tech Twitter, AI researchers, Indian tech scene |
| **Sports & Cricket** | Match takes, selection opinions, institutional (BCCI) snark. Test cricket over T20 for depth. | Cricket Twitter India, sports fans |
| **eSports & Dota 2** | Patch meta, draft analysis, SEA/India scene coverage. | Dota 2 community, SEA eSports audience |
| **Literature** | Strong opinions on specific books. Abandoned-book takes are as valid as recommendations. | Reading Twitter, literary fiction fans |
| **Gaming & Experimental Cooking** | Experiment logs (cooking), specific game mechanics (gaming). Paired because both are personal/odd. | Broad / personality-driven audience |

---

## WEEKLY CADENCE

| Day | Pillar | Funnel | Goal |
|---|---|---|---|
| Monday | AI Innovations | TOFU | Broad reach — shareable AI take |
| Tuesday | Sports & Cricket | MOFU | Community — Cricket Twitter engagement |
| Wednesday | eSports & Dota 2 | TOFU | Reach — Dota/eSports community |
| Thursday | Literature | MOFU | Depth — book opinions, discussion |
| Friday | Gaming & Exp. Cooking | TOFU | Personality — low-stakes fun post |
| Saturday | AI Innovations | MOFU | Depth — longer AI take or thread |
| Sunday | Flex (auto: lowest-engagement pillar) | TOFU | Recovery — give struggling pillar a second slot |

**Post time:** 21:00 IST (15:30 UTC) — peak Indian Twitter evening window.

---

## FUNNEL DEFINITIONS

**TOFU (Top of Funnel):**
- Shareable, standalone post. No assumed context.
- Hook is the whole post. One idea, fully resolved.
- CTA: none, or implicit (follow for more of this)

**MOFU (Middle of Funnel):**
- Personal story, opinion thread, or community-building post.
- Assumes some familiarity with the pillar.
- CTA: question that invites reply ("genuinely curious what you think about X")

**BOFU (Bottom of Funnel) — INACTIVE until newsletter launches:**
- Deep-dive post that ends with newsletter subscribe CTA.
- Activates automatically when `newsletter_url` is set in `config.json`.

---

## KEYWORD TARGETS

Defined in `config.json` under `pillar_keywords`. The trend scanner uses these to find relevant RSS/news items before content generation. Review monthly and update as vocabulary shifts.

---

## HASHTAG RULES
- Maximum 2 hashtags per post
- Only use hashtags for live/topical events: IPL match days, TI bracket days, major AI releases
- Zero hashtags on opinion posts, literature takes, cooking experiments
- Never use generic hashtags (#AI, #cricket) — they add noise without reach

---

## REPURPOSING SYSTEM (once content accumulates)
One strong post can become up to 3 formats:
1. **Original post** (primary format)
2. **Thread** (only if the idea genuinely needs more space)
3. **Quote-RT of yourself** 7 days later with a new angle or updated take

Build the X audience first before expanding to other platforms.

---

## PLAYBOOK UPDATE CYCLE
Updated automatically via **Refresh Playbooks** in the dashboard. The command:
1. Fetches recent posts from benchmark accounts (@Iyervval, @ruchirsharma_1, @mujifren)
2. Loads the last 20 published posts from the queue
3. Appends a dated "Trend Update" section with 3-5 actionable insights

Run monthly, or after any significant change in engagement patterns.
