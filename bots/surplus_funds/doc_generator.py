"""
Fee Agreement & Claim Document Generator.
Auto-fills PDF/DOCX templates with deal data from CRM.
"""
import os
import sys
from datetime import datetime
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bots.shared.standards import get_logger

log = get_logger("doc_generator")

CONTRACTS_DIR = os.path.expanduser("~/Desktop/wholesale-re/contracts")
OUTPUT_DIR = os.path.expanduser("~/Desktop/wholesale-re/contracts/generated")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def generate_fee_agreement(lead: Dict) -> str:
    """Generate a surplus funds fee agreement as HTML (printable/signable)."""
    owner = lead.get("former_owner", "________________")
    county = lead.get("county", "________________")
    state = lead.get("state", "__")
    amount = lead.get("surplus_amount", 0)
    case_num = lead.get("case_number", "________________")
    address = lead.get("property_address", "________________")
    fee_pct = lead.get("fee_percentage", 15)
    fee_amt = round(amount * fee_pct / 100, 2)
    today = datetime.utcnow().strftime("%B %d, %Y")

    html = f"""<!DOCTYPE html>
<html><head><style>
body {{ font-family: 'Times New Roman', serif; font-size: 14px; line-height: 1.8; max-width: 700px; margin: 40px auto; color: #111; }}
h1 {{ text-align: center; font-size: 20px; margin-bottom: 30px; }}
.line {{ border-bottom: 1px solid #333; display: inline-block; min-width: 200px; }}
.sig-line {{ border-bottom: 1px solid #333; width: 300px; margin-top: 40px; }}
p {{ margin: 10px 0; }}
</style></head><body>

<h1>SURPLUS FUNDS RECOVERY FEE AGREEMENT</h1>

<p>This Fee Agreement ("Agreement") is entered into on <strong>{today}</strong> by and between:</p>

<p><strong>Client (Former Property Owner):</strong><br>
Name: <span class="line">{owner}</span><br>
Address: <span class="line">________________________</span><br>
Phone: <span class="line">________________________</span><br>
Email: <span class="line">________________________</span></p>

<p><strong>Recovery Agent:</strong><br>
Name: Kenneth Bonnet<br>
Company: AI Tools Empire | Asset Recovery Division<br>
Email: bosaibot@gmail.com</p>

<p><strong>1. SURPLUS FUNDS INFORMATION</strong></p>
<p>County: <strong>{county} County, {state}</strong><br>
Case/Tax Deed Number: <strong>{case_num}</strong><br>
Property Address: <strong>{address}</strong><br>
Approximate Surplus Amount: <strong>${amount:,.2f}</strong></p>

<p><strong>2. SERVICES</strong></p>
<p>Recovery Agent agrees to research, prepare, and file all necessary documentation to recover surplus funds held by {county} County, {state} on behalf of the Client.</p>

<p><strong>3. FEE</strong></p>
<p>Client agrees to pay Recovery Agent a fee of <strong>{fee_pct}%</strong> of the total surplus funds recovered. Based on the estimated surplus of ${amount:,.2f}, the estimated fee is <strong>${fee_amt:,.2f}</strong>.</p>

<p>This fee is due ONLY upon successful recovery. If no funds are recovered, no fee is owed. Recovery Agent receives payment directly from the disbursement at closing, or Client pays within 10 business days of receiving funds from the county.</p>

<p><strong>4. AUTHORIZATION</strong></p>
<p>Client hereby authorizes Recovery Agent to act on Client's behalf in connection with the recovery of the surplus funds described above, including but not limited to: filing claims, communicating with county officials, and executing necessary paperwork.</p>

<p><strong>5. TERM</strong></p>
<p>This Agreement remains in effect for 12 months from the date of signing, or until the surplus funds are recovered, whichever comes first.</p>

<p><strong>6. GOVERNING LAW</strong></p>
<p>This Agreement shall be governed by the laws of the State of {state}.</p>

<br>
<p><strong>CLIENT SIGNATURE:</strong></p>
<div class="sig-line"></div>
<p>{owner} &nbsp;&nbsp;&nbsp;&nbsp; Date: _______________</p>

<br>
<p><strong>RECOVERY AGENT SIGNATURE:</strong></p>
<div class="sig-line"></div>
<p>Kenneth Bonnet &nbsp;&nbsp;&nbsp;&nbsp; Date: _______________</p>

</body></html>"""

    # Save to file
    safe_name = f"fee_agreement_{county}_{state}_{case_num}".replace(" ", "_").replace("/", "-")[:60]
    path = os.path.join(OUTPUT_DIR, f"{safe_name}.html")
    with open(path, "w") as f:
        f.write(html)

    log.info(f"Fee agreement generated: {path}")
    return path


def generate_purchase_agreement(deal: Dict) -> str:
    """Generate a pre-filled wholesale purchase agreement."""
    seller = deal.get("seller_name", deal.get("contact_name", "________________"))
    address = deal.get("address", "________________")
    price = deal.get("price", 0)
    today = datetime.utcnow().strftime("%B %d, %Y")

    html = f"""<!DOCTYPE html>
<html><head><style>
body {{ font-family: 'Times New Roman', serif; font-size: 13px; line-height: 1.7; max-width: 700px; margin: 30px auto; color: #111; }}
h1 {{ text-align: center; font-size: 18px; font-weight: bold; }}
.line {{ border-bottom: 1px solid #333; display: inline-block; min-width: 180px; }}
.sig-line {{ border-bottom: 1px solid #333; width: 280px; margin-top: 30px; }}
</style></head><body>

<h1>CONTRACT FOR PURCHASE OF RESIDENCE OR OTHER REAL ESTATE</h1>

<p>THIS CONTRACT is made on <strong>{today}</strong> by and between</p>
<p><span class="line"><strong>{seller}</strong></span> (Seller) whose address is</p>
<p><span class="line">{address}</span> and</p>
<p><span class="line"><strong>Kenneth Bonnet and/or assigns</strong></span> (Buyer) whose mailing address is</p>
<p><span class="line">bosaibot@gmail.com | AI Tools Empire</span></p>

<p><strong>THE PARTIES AGREE AS FOLLOWS:</strong></p>

<p><strong>1) PURCHASE AND SALE:</strong> The Seller agrees to sell and the Buyer agrees to buy the property located at: <strong>{address}</strong> together with all fixtures, landscaping, improvements, and appurtenances.</p>

<p><strong>2) PURCHASE PRICE:</strong> $<span class="line"><strong>{price:,}</strong></span></p>

<p><strong>TERMS:</strong> All cash. Buyer to close within 14-21 days of acceptance. No financing contingency.</p>

<p><strong>3) PRORATIONS:</strong> Real property taxes will not be prorated. Rents will not be prorated.</p>

<p><strong>4) DEFECTS:</strong> Seller warrants Property to be free from hazardous substance and from violation of any zoning, environmental, building, health or other governmental codes or ordinances.</p>

<p><strong>5) NO JUDGEMENTS:</strong> Seller warrants that there are no judgements threatening the equity in Property.</p>

<p><strong>6) POSSESSION:</strong> Possession of Property will be delivered to the Buyer when the title transfers.</p>

<p><strong>7) INSPECTIONS:</strong> Buyer shall have the right to enter Property and inspect prior to closing.</p>

<p><strong>8) CONTINGENCY:</strong> This contract is contingent upon Buyer's inspection within <span class="line">14</span> working days.</p>

<p><strong>9) ACCEPTANCE:</strong> If not accepted by Seller prior to <span class="line">_______________</span>, this contract shall be void.</p>

<p><strong>10) DEPOSITS:</strong> Upon acceptance Buyer will place in escrow an earnest money deposit of $<span class="line">500</span>.</p>

<p><strong>11) CLOSING:</strong> Closing will take place on or before <span class="line">_______________</span>.</p>

<p><strong>12) OTHER AGREEMENTS:</strong></p>
<ul>
<li>Buyer agrees to purchase Property in "as is" condition.</li>
<li>Buyer may assign or transfer any rights to a third party without Seller's consent.</li>
<li>Buyer to pay all closing costs.</li>
<li>In the event of default, the sole remedy shall be the earnest money deposit.</li>
</ul>

<br>
<p><strong>Buyer:</strong></p>
<div class="sig-line"></div>
<p>Kenneth Bonnet &nbsp;&nbsp;&nbsp;&nbsp; Date: _______________</p>

<br>
<p><strong>I accept and agree to be bound by above contract:</strong></p>
<div class="sig-line"></div>
<p>{seller} (Seller) &nbsp;&nbsp;&nbsp;&nbsp; Date: _______________</p>

</body></html>"""

    safe_name = f"purchase_agreement_{address[:30]}".replace(" ", "_").replace(",", "").replace("/", "-")
    path = os.path.join(OUTPUT_DIR, f"{safe_name}.html")
    with open(path, "w") as f:
        f.write(html)

    log.info(f"Purchase agreement generated: {path}")
    return path


if __name__ == "__main__":
    # Test
    test_lead = {
        "former_owner": "John Smith",
        "county": "DeKalb",
        "state": "GA",
        "surplus_amount": 15234.56,
        "case_number": "2024002754",
        "property_address": "123 Main St, Decatur, GA 30030",
        "fee_percentage": 15,
    }
    path = generate_fee_agreement(test_lead)
    print(f"Fee agreement: {path}")

    test_deal = {
        "seller_name": "Jane Doe",
        "address": "257 Peyton Pl SW, Atlanta, GA 30311",
        "price": 75000,
    }
    path2 = generate_purchase_agreement(test_deal)
    print(f"Purchase agreement: {path2}")
