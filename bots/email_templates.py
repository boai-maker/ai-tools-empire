"""
Email templates for all outreach — wholesale offers, surplus funds, buyer outreach.
Centralized so all bots use consistent, professional messaging.
"""

WHOLESALE_OFFER = """Hi {first_name},

I came across {address} listed at ${price:,} and I'd like to submit a cash offer of ${offer_price:,}.

I'm a local investor and can close in 14-21 days. No contingencies, no financing delays.

This is a firm offer — I'm ready to sign a purchase agreement today if the seller is willing.

A few questions:
- Is the seller flexible on timeline?
- Are there any existing offers?
- Can you send the seller's disclosure?

Looking forward to your response.

Kenneth Bonnet
AI Tools Empire | Real Estate Division
bosaibot@gmail.com
"""

SURPLUS_FUNDS_EMAIL = """Hi {first_name},

I'm reaching out because I found unclaimed surplus funds in your name from a property tax sale in {county} County, {state}.

According to county records, approximately ${amount:,.2f} in surplus funds exists from the sale of {address}. This money belongs to you as the former property owner, but the county will not contact you about it.

I specialize in helping people recover these funds. My service is completely free upfront — I only get paid if you get paid. My fee is {fee_pct}% of the recovered amount, and you receive the rest.

Here is what happens next:
1. I verify your claim eligibility (24 hours)
2. I prepare and file all paperwork with the county
3. The county processes the claim (30-90 days)
4. You receive your money

There is no cost to you unless the claim is successful.

Would you like me to start the process? Simply reply to this email.

Kenneth Bonnet
AI Tools Empire | Asset Recovery Division
bosaibot@gmail.com
"""

SURPLUS_FOLLOWUP = """Hi {first_name},

I wanted to follow up on my previous message about ${amount:,.2f} in unclaimed surplus funds that may be owed to you from {county} County, {state}.

This money is sitting with the county right now. You are the rightful owner, and I can help you claim it at no upfront cost.

If you have any questions about the process, I am happy to explain. There is no obligation — just reply to this email and I will verify your eligibility.

This offer is time-sensitive as claim deadlines do apply.

Kenneth Bonnet
AI Tools Empire | Asset Recovery Division
bosaibot@gmail.com
"""

BUYER_INTEREST = """Hi {first_name},

I am reaching out to see if you are actively buying investment properties in the {markets} area.

I source off-market deals consistently — distressed properties, estate sales, foreclosures, and vacant properties — and I am building a vetted buyer list for quick assignments.

If you are in the market, I would like to know:

1. What areas do you buy in?
2. What is your typical price range?
3. Do you prefer rehab projects or turnkey?
4. How fast can you close with cash?

Once I know your criteria, I will only send you matching properties.

Kenneth Bonnet
AI Tools Empire | Real Estate Division
bosaibot@gmail.com
"""

BUYER_DEAL_BLAST = """Hi {first_name},

I have a new off-market deal that matches your buy criteria:

Property: {address}
Price: ${price:,}
ARV: ${arv:,}
Beds/Baths: {beds}/{baths} | {sqft:,} sqft
Estimated Profit: ${profit:,}
Assignment Fee: $10,000

This deal passes the 70% rule and is ready for immediate assignment.

Interested? Reply with "send details" and I will send the full comp package and contract today.

Kenneth Bonnet
AI Tools Empire | Real Estate Division
bosaibot@gmail.com
"""
