// AI Tools Empire — Client-side JS

// ── Affiliate link click tracking ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Track all affiliate link clicks
  document.querySelectorAll('.affiliate-link, [data-tool]').forEach(link => {
    link.addEventListener('click', () => {
      const tool = link.dataset.tool;
      if (tool) {
        fetch(`/track/click/${tool}?source=${encodeURIComponent(window.location.pathname)}`, {
          method: 'POST', keepalive: true
        }).catch(() => {});
      }
    });
  });

  // Sticky header shadow
  const nav = document.querySelector('.nav');
  if (nav) {
    window.addEventListener('scroll', () => {
      nav.style.boxShadow = window.scrollY > 10
        ? '0 4px 20px rgba(0,0,0,0.1)'
        : 'none';
    });
  }

  // Exit-intent popup for email capture (fires once per session)
  if (!sessionStorage.getItem('popup_shown')) {
    let shown = false;
    document.addEventListener('mouseleave', (e) => {
      if (e.clientY < 10 && !shown) {
        shown = true;
        sessionStorage.setItem('popup_shown', '1');
        showExitPopup();
      }
    });
  }
});

// ── Exit-intent popup ─────────────────────────────────────────────────────────
function showExitPopup() {
  const overlay = document.createElement('div');
  overlay.style.cssText = `
    position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:9999;
    display:flex;align-items:center;justify-content:center;padding:20px;
  `;
  overlay.innerHTML = `
    <div style="background:white;border-radius:16px;padding:40px;max-width:460px;width:100%;text-align:center;position:relative;">
      <button onclick="this.closest('[style]').remove()" style="position:absolute;top:12px;right:16px;background:none;border:none;font-size:20px;cursor:pointer;color:#94a3b8;">✕</button>
      <div style="font-size:40px;margin-bottom:12px;">🤖</div>
      <h2 style="font-size:24px;font-weight:800;margin:0 0 10px;color:#1e293b;">Wait — Don't Leave Empty-Handed!</h2>
      <p style="color:#64748b;margin:0 0 24px;line-height:1.6;">Get our FREE weekly digest of the best AI tool deals, reviews, and money-saving tips.</p>
      <form onsubmit="handlePopupSubscribe(event)" style="display:flex;flex-direction:column;gap:12px;">
        <input type="email" id="popup-email" placeholder="Enter your email..." required
          style="padding:14px 18px;border-radius:10px;border:2px solid #e2e8f0;font-size:15px;outline:none;">
        <button type="submit" style="background:#6366f1;color:white;border:none;padding:14px;border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;">
          Yes, Send Me Free AI Tool Deals!
        </button>
      </form>
      <p style="font-size:12px;color:#94a3b8;margin:12px 0 0;">No spam. Unsubscribe anytime.</p>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });
}

async function handlePopupSubscribe(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  btn.innerHTML = '<span class="spinner"></span> Subscribing...';
  btn.disabled = true;

  const email = document.getElementById('popup-email').value;
  const res = await fetch('/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
  const data = await res.json();

  if (data.success) {
    e.target.closest('[style*="position:fixed"]').remove();
    showToast('🎉 Subscribed! Check your inbox for a welcome email.');
  } else {
    btn.textContent = 'Try again';
    btn.disabled = false;
  }
}
