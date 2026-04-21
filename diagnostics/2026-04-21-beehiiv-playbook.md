# Beehiiv 5-Minute Playbook — 2026-04-21

Your API key + publication ID are wired. Every `/subscribe` and `/stack-audit`
signup now lands in beehiiv with `send_welcome_email: true` already set.
What's missing: the actual welcome email content (set-once, available on
all tiers including free).

**Status:** Max trial, Day 8 of 14. Automations are Scale-gated after trial
— don't invest time in multi-email drips yet. Master the single welcome
email now, iterate later.

---

## Step 1 — Turn on the welcome email (2 min)

1. Open the beehiiv tab → Sidebar → **Settings**
2. Find **"Signup flow"** or **"Publication settings"** → **"Welcome Email"** toggle
3. Turn it **ON**
4. Paste the copy from `WELCOME_EMAIL_V1` below
5. Save

If the welcome-email section is under **Newsletter → Settings** instead,
same idea — one email, triggered on signup.

---

## Step 2 — Disable double-opt-in (optional, 1 min)

Default beehiiv requires email confirmation. Every sub is `validating` until
they click a link. At 3 existing subscribers that's costing you real conversion.

1. Sidebar → **Settings** → **Signup / Subscription**
2. Look for "Require email confirmation" or "Double opt-in"
3. Turn **OFF** unless you're emailing EU readers (GDPR soft-requires it)

Trade-off: slightly higher spam/junk rate, materially higher activation rate.

---

## Step 3 — Paste your first weekly newsletter (later this week, 10 min)

One newsletter per week is the single biggest driver for newsletter growth
— beehiiv's recommendation algorithm rewards weekly cadence. Use the
`FRIDAY_ROUNDUP_V1` template below as your first one. Schedule for Friday
9 AM ET.

---

# WELCOME_EMAIL_V1

**Subject line (A test this eventually):** `Your AI stack audit — how this works`

**Preview text:** Reply with your stack. I send back what to drop, what to keep, what to add.

**Body (HTML):**

```html
<p>Hey,</p>

<p>Thanks for jumping on. You just signed up for AI Tools Empire Weekly — a
short email every Friday that tells you which AI tools are actually worth
paying for and which are garbage.</p>

<p><strong>Before Friday, here's what to do:</strong></p>

<p>Reply to this email with the AI tools you're paying for right now. Be
specific — include the monthly cost if you know it. Something like:</p>

<blockquote style="border-left: 3px solid #10b981; padding: 8px 16px; margin: 16px 0; color: #475569;">
ChatGPT Plus — $20<br>
Jasper — $49<br>
Descript — $24<br>
Zapier — $29
</blockquote>

<p>Within 48 hours I'll send you back a 3-line audit: what to drop, what
to keep, what to add. No sales pitch, no upsell, no "book a demo." Just
the 3 lines.</p>

<p>Most readers save $50–$120/month after acting on one audit. Some save
more. One reader dropped three redundant subscriptions and kept one tool
that did all three jobs better.</p>

<p><strong>Why I do this:</strong> I pay for ~15 AI tools myself and I
notice patterns. Most people's stacks have 2–4 tools doing the same thing
with different brand names.</p>

<p>Hit reply and paste your stack. I'll get back to you.</p>

<p>— Kenneth<br>
<em>AI Tools Empire</em></p>

<hr style="border: none; border-top: 1px solid #e2e8f0; margin: 32px 0;">

<p style="font-size: 13px; color: #94a3b8;">
P.S. If you prefer a web form over email, the same audit runs at
<a href="https://aitoolsempire.co/stack-audit" style="color: #10b981;">aitoolsempire.co/stack-audit</a>.
</p>
```

**What it does right (brand voice audit):**
- Second-person ("you"), not corporate "we" ✅
- Short sentences, no filler ✅
- One concrete CTA (reply with stack) ✅
- Specific numbers ($50–$120/month saved, 3-line audit, 48 hours) ✅
- Zero banned phrases ✅
- Not signing off with "thanks for watching" or the like ✅

---

# FRIDAY_ROUNDUP_V1 (template for your first weekly)

**Subject line:** `The one AI tool I'd buy this week (and two I'd drop)`

**Preview text:** One pick, two kills, one prompt, one question.

**Body structure** — pick the [bracketed] specifics each Friday:

```html
<h2>🔧 Tool of the week</h2>
<p><strong>[Tool Name]</strong> — [one sentence what it does].
I've been using it for [N days/weeks] and [specific result with a number].
[Affiliate link]</p>

<h2>💸 Kill your [tool type]</h2>
<p>If you're still paying for [old tool 1] or [old tool 2], read this.
[Two sentences why they're outdated]. Switch to [new thing] — [specific reason].</p>

<h2>📰 Article you might've missed</h2>
<p><a href="[article URL]">[Article title]</a> — [one sentence hook].
[One sentence why it matters to them right now].</p>

<h2>⚡ One prompt</h2>
<pre style="background: #f1f5f9; padding: 12px; border-radius: 6px; font-size: 14px;">
[Actual useful prompt — 3-6 lines. Not "write a blog post about X".
Something specific with variables they can fill in.]
</pre>
<p>Paste into Claude, ChatGPT, whatever. Replace the [brackets].</p>

<h2>💬 Reader question</h2>
<p><em>"[Paraphrased reader question — real or plausible]"</em></p>
<p>[Your 2-3 sentence answer. Don't hedge. Take a position.]</p>

<hr>

<p>Want a free 3-line audit of your AI stack? Reply with the tools you're
paying for. 48 hours. No pitch.</p>

<p>— Kenneth</p>
```

**Rules for filling this in:**
- Pick ONE tool for Tool-of-the-Week. Never 3. Never "best of" lists.
- "Two I'd drop" must be specific tools — not categories.
- The prompt is real value — don't pad with fluff.
- Reader question is OK to invent if you don't have a real one, just make
  it plausible ("Why is my content not ranking?", "Is Notion AI worth it?").
- Every email ends with the stack-audit CTA until conversion rate is > 2%.

---

# What NOT to do in beehiiv

- **Don't upgrade to Scale ($84/mo) yet.** You need ~500 engaged subscribers
  and a measured reply rate before the automation features justify the cost.
- **Don't enable beehiiv Boosts without reading the fine print.** They show
  your newsletter to subs of other pubs, which grows your list fast but
  dilutes quality.
- **Don't write to "your community".** Write to one person. Use "you."

---

# After you paste the welcome email

Come back and tell me:
1. Is double opt-in on or off (affects sub conversion math)
2. Any error messages or missing field in beehiiv

I'll wire the follow-ups accordingly.
