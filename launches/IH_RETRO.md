# Indie Hackers retro post

**Where:** indiehackers.com/post/new — pick "Story" not "Question"

**Optimal timing:** Tuesday or Thursday, 9-11am Eastern.

**Title (use exactly one):**

- I built 4 AI products in 3 weeks. Zero customers. Here's the post-mortem. (RECOMMENDED — IH loves vulnerability)
- I shipped a $99 Stack Audit, $47 cold-email tool, $29 service, $19 templates. 0 sales. Honest retro.
- Built 4 indie products on a 14-bot autonomous stack. Made $0. What I learned.

---

## Body — paste verbatim, edit only the dollar figures if you want them more accurate

```
Three weeks ago I shipped my first indie product (Stack Audit, $99).
Then Pipeline Hunter ($47, MIT-licensed Python file). Then an AI
Affiliate Application Service ($29). Then a Stack Audit Template Pack
($19, self-serve).

Four products. Six real newsletter subscribers. Zero paying customers.

Here's the honest post-mortem of what worked and what didn't, because
the IH community gave me three threads' worth of help getting here and
the least I owe back is the truth.

## What went RIGHT (technically)

I built the whole empire on top of a 14-bot autonomous stack on a Mac
mini. APScheduler + launchd + SQLite + FastAPI. The infrastructure
hums. Telegram pings me on every event. A Gumroad webhook dispatcher
routes any of the 4 products through one URL. Affiliate clicks capture
emails when the program isn't approved yet (whitelist + waitlist
fallback). Stack Audit nudges abandoned carts 4x/day with up to 3
reminders, 12h apart.

It's the kind of system you'd pay $200/month for as a SaaS. It runs
on a $700 computer.

## What went WRONG (commercially)

Traffic. I'm averaging 17-22 affiliate clicks per day, ~$3/day in
estimated revenue, and $0 realized in 3 weeks because none of the
clicks have closed yet.

I built the funnel before I built the audience. Classic mistake. I
have a Twitter account with 27 followers, no SEO yet, and I keep
telling myself "Show HN will fix it" without actually doing the work
of submitting it.

## Four lessons I'd give past-me

**1. Distribution is 80% of the work. I budgeted 20%.**
I spent 3 weeks engineering. I should have spent 3 days engineering
and 18 days posting on Reddit, replying on Twitter, and writing on IH.
The "build it and they will come" mindset is a luxury for established
creators.

**2. Pricing tiers help if you have ANY traffic. They hurt if you don't.**
I have 4 products at 4 price points. Should have had ONE product at
ONE price ($47 Pipeline Hunter is the most defensible) and put 100%
of my energy there. Tier ladders work when funnels exist; mine doesn't
yet.

**3. Affiliate revenue is real but slow.**
I get 17 clicks/day. Each click is worth ~$0.14 EPC across the active
programs (rytr, fliki, pictory, elevenlabs, fireflies, murf). At a
1.5% conversion-to-paid rate that's $0.30/click average. To hit my
$100/day goal I need 333 clicks/day, which means ~10x the current
content output.

**4. The audit IS the product.**
The $99 Stack Audit's biggest win is the substitution map. People who
read the substitution map go "oh, I shouldn't pay for half of these."
That's the actual conversion event. Selling it as a $19 self-serve
template pack might be the higher-ROI play than selling done-for-you.
We'll see.

## Where I'm going from here

This week I'm going to do EXACTLY what I've been deferring:
- Submit Pipeline Hunter to Show HN
- Reply to 5 "what AI tool should I use" tweets per day
- Run a $70 Reddit ads test on r/sideproject
- Write 3 IH posts (this is one of them)
- Generate 50 programmatic SEO articles for long-tail terms

If anyone in the IH community wants to swap newsletter mentions, my
list is small (6 real subscribers, no joke) but my open rates are
100% because I personally email every signup. DM me if interested.

If anyone has been through the "great infra, no customers" dip and
came out the other side, I'm all ears on what unblocked you.

— Kenneth
aitoolsempire.co
```

---

## Why this works on IH

- **Vulnerability beats bravado** — IH algorithm rewards stories where the founder admits they fucked up
- **Concrete numbers** — "27 followers, 6 subs" is more compelling than "small audience"
- **Specific lessons** — not generic ("you need traffic") but pointed ("I have 4 products and should've had 1")
- **Ask in the close** — "newsletter swap" + "tactics that worked" gives commenters an easy hook to engage

## Reply playbook (be ready)

- **"Why 4 products at once?"** → Honest: thought tier laddering would work without traffic. Wrong.
- **"Why not just YouTube?"** → Hate being on camera. Trying programmatic SEO + Twitter instead.
- **"Stack Audit looks neat — is the $99 worth it?"** → Probably not for you. Get the $19 template pack. If you want me to do it for you THEN $99.
- **"Show me the substitution map?"** → Link to /stack-audit-templates ($19) — but generously: "DM me if you want the broad strokes free."
