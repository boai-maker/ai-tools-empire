# Show HN preflight checklist — Pipeline Hunter

The existing `launches/SHOW_HN.md` has the post copy ready. This is the
checklist for the actual submission day.

---

## Best submission window

**Tuesday or Wednesday, 8:00 AM Eastern.**

Why: HN's daily traffic peaks 9am-12pm Eastern. Submitting at 8am puts
you in the early-adopter scroll BEFORE the bigger Show HN posts of the
day claim oxygen. Avoid Mondays (weekend backlog) and Thursdays/Fridays
(Show HN engagement falls).

**Backup window:** Saturday 9am Eastern. Lower traffic but less
competition for front page.

---

## Day-of preflight (do these in order, ~25 min total)

### 1. Make sure the product page is bulletproof (5 min)

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://aitoolsempire.co/pipeline-hunter
curl -s -o /dev/null -w "%{http_code}\n" https://bosaibot.gumroad.com/l/bfapw
```

Both should return 200. If either is 4xx or 5xx, fix BEFORE submitting.

### 2. Stress-test the buy flow (5 min)

- Open the Gumroad URL in incognito
- Add to cart, get to the payment step
- Confirm the price shows $47 (not $97 — sometimes Gumroad reverts)
- Confirm the after-purchase content/receipt is the polished version

### 3. Test the actual product file (5 min)

- Buy your own product (refund yourself after — Gumroad allows)
- Download the file
- Make sure README, prompts, code all open cleanly
- This catches "I uploaded the wrong file" 70% of bugs that kill
  Show HN posts in the comments

### 4. Submit to HN (3 min)

Go to **https://news.ycombinator.com/submit**

| Field | Value |
|---|---|
| Title | `Show HN: Pipeline Hunter – AI cold-email agent in one Python file` |
| URL | `https://aitoolsempire.co/pipeline-hunter` (NOT the Gumroad URL — HN dings direct-buy URLs) |
| Text | (leave blank — Show HN posts with text get penalized) |

Click submit. **DO NOT close the tab.**

### 5. Post the maker comment IMMEDIATELY (3 min)

The maker comment in `launches/SHOW_HN.md` is ready. Copy the whole
"Hey HNers — I'm Kenneth, the maker..." block and paste it as the
FIRST comment on your own post within 60 seconds of submitting.

This is the single biggest factor in Show HN engagement. A maker
comment within the first minute roughly doubles your odds of hitting
the front page.

### 6. Set up the watching scripts (5 min)

```bash
# Tail the request log so we see traffic spikes as they happen
tail -f /var/log/aitoolsempire/access.log 2>/dev/null || tail -f ~/ai-tools-empire/logs/access.log

# In a second terminal, watch your Gumroad sales dashboard
open https://gumroad.com/sales
```

If a sale fires, you'll get a Telegram `💰 PAID Pipeline Hunter ($47)`
within 5 seconds via the unified dispatcher.

---

## Comment-reply playbook (have these ready)

HN comments come fast in the first hour. Don't get caught flat.

**"How is this different from [Lemlist / Smartlead / Apollo]?"**
> "Those are great hosted platforms. Pipeline Hunter is for people
> who specifically want to OWN their cold-email stack — your code,
> your domain, your sending IP, your costs (~$0.01/email vs $0.50-2
> effective on the SaaS). It's not a competitor to those, it's an
> alternative for the segment that wants to bring it in-house."

**"Why $47?"**
> "Because the prompts are the product. Three months of A/B testing
> on real pipelines distilled into 3 templates. The code is the
> wrapper; the tuned prompts + QUICKSTART are the actual value.
> Going to $97 after 50 sales — early-adopter discount."

**"Why not open-source it for free?"**
> "It is open-source — MIT licensed. You can fork it, white-label it,
> bundle it inside your product, no attribution required. The $47 is
> for: the tuned prompts, the email-sender deliverability config, the
> follow-up cadence logic, and the docs. Source code is open."

**"Doesn't this just spam people?"**
> "Same answer as for any cold-email tool: depends on the operator.
> The pack ships with: real-from-address requirement, plain-text
> option, mandatory unsubscribe, randomized send delays, and a
> suppression-list hook. It does NOT do AI 'warmup' theater because
> that's mostly snake oil. Your domain reputation is yours."

**"Show me the prompts?"**
> "Email me kenneth@aitoolsempire.co, I'll send you one of the three
> as a sample. Or buy the $47 pack and you get all three plus the
> tuning guide."

**"Is this AI-generated?"**
> "Hand-written — and I'll send the actual git log if anyone wants
> proof. The DESIGN was helped by Claude (I'm a one-person team and
> use AI for code review). The product copy is mine."

---

## Hour-by-hour battle plan

**T+0 to T+15 min:** Maker comment posted. Reply to first 3 comments
within 60 seconds each. Keep tab open, refresh every 30 seconds.

**T+15 to T+60 min:** This is when the post either climbs or stalls.
If you hit 5+ upvotes, you're on the climb. If you're stuck at 2-3,
the title or timing is the issue — you can't recover, just learn.

**T+1 to T+3 hr:** Reply to every comment. Even the negative ones,
generously. HN respects engagement. Don't take bait — the curators
watch for argumentative makers.

**T+3 to T+8 hr:** Front page if you got traction. This is the heavy-
traffic window. Don't change ANYTHING on the site. Don't push a deploy.
Don't let a 500 happen.

**T+24 hr:** Post falls off the front page. This is where the real
work starts — every commenter who DM'd you is a potential customer
warming up.

---

## What "success" looks like

- 50+ upvotes in first 4 hours (front page territory)
- 20+ comments
- 5-50 sales depending on visibility
- 50-300 newsletter signups
- 5-15 follow-up DMs / emails about the audit service or Affiliate
  Service products

## What "failure" looks like

- <5 upvotes after 1 hour → post died, move on, try Tuesday next week
- Negative engagement → take notes for v2, do not panic-reply

You only get ONE Show HN per project per Y Combinator's unwritten
rules. Make this count.
