# Demo script (about 5 minutes)

For showing the project live: to a teacher, in an interview, or on a call.

## Before you start (2 minutes, once)

```bash
docker compose --profile app up -d          # app at http://localhost:8090
scripts/share.sh                            # only if someone joins remotely: prints a public link
```
- Have `DEMO_PASSWORD` from `.env` ready (sign-in: `demo@example.com`).
- Make your own account an admin for the Evaluation page:
  `docker compose --profile app exec api python -m app.cli make-admin you@example.com`
- Have a résumé PDF ready (yours, or a made-up one; it goes to Gemini's free tier).
- Open one tab on the landing page and one signed in as the demo user.

## The walkthrough

| Time | Show | Say |
|---|---|---|
| 0:00 | **Landing page.** Move the mouse over the terrain. | "A job-matching platform: it ranks every open role for you and explains why. The counts on the right are live from the database. The listings are synthetic, and labelled as such." |
| 0:30 | **Sign in as the demo → Overview.** | "A profile with skills and a preference for backend roles. These are its top matches." |
| 1:00 | **For you.** Point at the top card, then hide one job with ✕. | "Hybrid retrieval, keywords plus meaning, then a ranker that scores ten factors. Hiding a job is logged, and the next ranking learns from it." |
| 1:45 | **Open the top job.** Point at 'Why it ranks here' and the ticked skills. | "Every score is explainable: each bar is how much a factor added. Unknown data counts as neutral, not as a penalty." |
| 2:30 | **Search** "backend python", filter a city. Press back after opening a result. | "Search state lives in the URL, so back and shared links work." |
| 3:00 | **Assistant:** "Find backend jobs in Bengaluru and save the best one." Wait for the confirmation card, approve. Open the steps. | "LangGraph with ten tools. It never saves or changes anything without asking, and every fact in the reply is checked against what the tools returned." |
| 4:00 | **Résumé:** upload a PDF, show the review form. | "Gemini extracts the fields, then code checks them: skills not in the PDF are dropped, keyword-only matches are unticked, and nothing is saved until you confirm." |
| 4:30 | **Evaluation** (admin account). | "Everything is measured: ranking on a public benchmark with human labels, and the assistant on 23 scripted conversations. The numbers come from stored runs with their dataset and commit." |

## Numbers you can quote (all from stored runs)

| Claim | Number | Caveat to say out loud |
|---|---|---|
| Ranking quality (TalentCLEF 2026, human labels) | MAP@100 0.74 (hybrid retrieval) → 0.78 (+ features, the app default) → 0.81 (+ cross-encoder) | 10 queries; both gains were significant in a paired bootstrap (+0.067 [0.038, 0.106] for the full stack) |
| Retrieval (synthetic jobs, silver labels, test split) | NDCG@10: lexical 0.767, hybrid 0.818 | Compare methods, not absolute values; the best embedding model flipped between dev and test |
| Personalization (simulated users) | NDCG@10 on fresh results: 0.04 generic → 0.28 learned from clicks → 0.45 stated preference | Simulated personas, not real people |
| Assistant (23 cases, 2 live runs) | 23/23 tasks, groundedness 1.0, 39/39 facts checked, 0 unconfirmed changes | Known weaknesses: adds an unrequested filter in 2 of 6 cases; retries a failing tool |
| Résumé extraction (10 fictional résumés) | Skill precision and recall 1.0 after checks; injected skill rejected | Optimistic: the fixes were designed after seeing the first run |
| Speed (laptop CPU) | Search end to end 63 ms p50; cross-encoder +420 ms (why it's opt-in) | |

## If something goes wrong

- **Assistant says it's busy:** the Gemini free tier allows only a few requests per minute. Wait a minute, or show the step trace of an earlier conversation.
- **Résumé stuck on "Reading…":** check `docker compose --profile app logs worker`. Without `GEMINI_API_KEY` the page says extraction is unavailable.
- **Share link doesn't open:** run `scripts/share.sh stop && scripts/share.sh` for a fresh link.
- **Too many sign-in attempts (429):** wait the minutes it says, or restart Redis: `docker compose restart redis`.
