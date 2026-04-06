/**
 * AI Tools Empire — Main JavaScript
 * Mobile menu, scroll animations, count-up, smooth scroll, sticky nav
 */

(function () {
  'use strict';

  /* ── Utility: DOM ready ── */
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  /* ══════════════════════════════════════
     MOBILE MENU TOGGLE
     ══════════════════════════════════════ */
  function initMobileMenu() {
    const hamburger = document.querySelector('.nav-hamburger');
    const mobileMenu = document.querySelector('.nav-mobile-menu');
    if (!hamburger || !mobileMenu) return;

    hamburger.addEventListener('click', function () {
      const isOpen = mobileMenu.classList.toggle('open');
      hamburger.classList.toggle('open', isOpen);
      hamburger.setAttribute('aria-expanded', isOpen);
      document.body.style.overflow = isOpen ? 'hidden' : '';
    });

    // Close on backdrop click / link click
    mobileMenu.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        mobileMenu.classList.remove('open');
        hamburger.classList.remove('open');
        hamburger.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
      });
    });

    // Close on Escape
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && mobileMenu.classList.contains('open')) {
        mobileMenu.classList.remove('open');
        hamburger.classList.remove('open');
        hamburger.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
      }
    });
  }

  /* ══════════════════════════════════════
     STICKY NAV SHRINK ON SCROLL
     ══════════════════════════════════════ */
  function initStickyNav() {
    const nav = document.querySelector('.nav');
    if (!nav) return;

    let lastScroll = 0;

    window.addEventListener('scroll', function () {
      const currentScroll = window.scrollY;

      if (currentScroll > 80) {
        nav.classList.add('scrolled');
      } else {
        nav.classList.remove('scrolled');
      }

      lastScroll = currentScroll;
    }, { passive: true });
  }

  /* ══════════════════════════════════════
     INTERSECTION OBSERVER — SCROLL ANIMATIONS
     ══════════════════════════════════════ */
  function initScrollAnimations() {
    const elements = document.querySelectorAll('.animate-on-scroll');
    if (!elements.length) return;

    if (!('IntersectionObserver' in window)) {
      // Fallback: make all visible immediately
      elements.forEach(function (el) { el.classList.add('visible'); });
      return;
    }

    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.12,
      rootMargin: '0px 0px -40px 0px'
    });

    elements.forEach(function (el) { observer.observe(el); });
  }

  /* ══════════════════════════════════════
     COUNT-UP ANIMATION
     ══════════════════════════════════════ */
  function countUp(el, target, duration) {
    var start = 0;
    var startTime = null;
    var suffix = el.dataset.suffix || '';
    var prefix = el.dataset.prefix || '';

    function step(timestamp) {
      if (!startTime) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      // Ease out cubic
      var eased = 1 - Math.pow(1 - progress, 3);
      var current = Math.round(eased * target);
      el.textContent = prefix + current.toLocaleString() + suffix;
      if (progress < 1) requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
  }

  function initCountUp() {
    var elements = document.querySelectorAll('[data-count]');
    if (!elements.length) return;

    if (!('IntersectionObserver' in window)) {
      elements.forEach(function (el) {
        el.textContent = (el.dataset.prefix || '') + Number(el.dataset.count).toLocaleString() + (el.dataset.suffix || '');
      });
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var el = entry.target;
          var target = parseInt(el.dataset.count, 10);
          var duration = parseInt(el.dataset.duration || '1800', 10);
          countUp(el, target, duration);
          observer.unobserve(el);
        }
      });
    }, { threshold: 0.5 });

    elements.forEach(function (el) { observer.observe(el); });
  }

  /* ══════════════════════════════════════
     SMOOTH SCROLL FOR ANCHOR LINKS
     ══════════════════════════════════════ */
  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        var href = this.getAttribute('href');
        if (href === '#') return;
        var target = document.querySelector(href);
        if (target) {
          e.preventDefault();
          var navHeight = document.querySelector('.nav') ? document.querySelector('.nav').offsetHeight : 0;
          var targetTop = target.getBoundingClientRect().top + window.scrollY - navHeight - 16;
          window.scrollTo({ top: targetTop, behavior: 'smooth' });
        }
      });
    });
  }

  /* ══════════════════════════════════════
     AFFILIATE CLICK TRACKING
     ══════════════════════════════════════ */
  function initAffiliateTracking() {
    document.querySelectorAll('.affiliate-link').forEach(function (link) {
      link.addEventListener('click', function () {
        var tool = this.dataset.tool;
        if (tool) {
          fetch('/track/click/' + tool + '?source=' + encodeURIComponent(window.location.pathname), {
            method: 'POST', keepalive: true
          }).catch(function () {}); // silent fail
        }
      });
    });
  }

  /* ══════════════════════════════════════
     EXIT INTENT POPUP
     ══════════════════════════════════════ */
  function initExitPopup() {
    var POPUP_KEY = 'popup_shown_v2';
    if (sessionStorage.getItem(POPUP_KEY)) return;

    var popup = document.getElementById('exit-popup');
    if (!popup) return;

    function showPopup() {
      if (sessionStorage.getItem(POPUP_KEY)) return;
      sessionStorage.setItem(POPUP_KEY, '1');
      popup.style.display = 'flex';
      document.body.style.overflow = 'hidden';
    }

    // Exit intent (desktop only)
    if (window.innerWidth > 768) {
      document.addEventListener('mouseleave', function (e) {
        if (e.clientY < 10) showPopup();
      });
    }

    // Scroll 65% trigger
    window.addEventListener('scroll', function () {
      var scrolled = window.scrollY / Math.max(1, document.body.scrollHeight - window.innerHeight);
      if (scrolled > 0.65) showPopup();
    }, { passive: true });

    // Close on backdrop click
    popup.addEventListener('click', function (e) {
      if (e.target === popup) closePopup();
    });
  }

  /* ══════════════════════════════════════
     TOAST HELPER (global)
     ══════════════════════════════════════ */
  window.showToast = function (msg) {
    var t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._timeout);
    t._timeout = setTimeout(function () { t.classList.remove('show'); }, 4200);
  };

  /* ══════════════════════════════════════
     CLOSE POPUP (global)
     ══════════════════════════════════════ */
  window.closePopup = function () {
    var popup = document.getElementById('exit-popup');
    if (popup) {
      popup.style.display = 'none';
      document.body.style.overflow = '';
    }
  };

  /* ══════════════════════════════════════
     POPUP SUBSCRIBE HANDLER (global)
     ══════════════════════════════════════ */
  window.handlePopupSubscribe = async function (e) {
    e.preventDefault();
    var emailEl = document.getElementById('popup-email');
    var btn = e.target.querySelector('button');
    if (!emailEl || !btn) return;

    var email = emailEl.value.trim();
    if (!email) return;

    btn.textContent = 'Subscribing...';
    btn.disabled = true;

    try {
      var r = await fetch('/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, name: '', source: 'exit-popup' })
      });
      var d = await r.json();
      closePopup();
      showToast(d.success ? '✓ Check your inbox — kit is on its way!' : (d.message || 'Something went wrong.'));
    } catch (err) {
      closePopup();
      showToast('Something went wrong. Please try again.');
    }
  };

  /* ══════════════════════════════════════
     ACTIVE NAV LINK
     ══════════════════════════════════════ */
  function initActiveNav() {
    var path = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(function (link) {
      var href = link.getAttribute('href');
      if (href && href !== '/' && path.startsWith(href)) {
        link.classList.add('active');
      } else if (href === '/' && path === '/') {
        link.classList.add('active');
      }
    });
  }

  /* ══════════════════════════════════════
     INIT ALL
     ══════════════════════════════════════ */
  ready(function () {
    initMobileMenu();
    initStickyNav();
    initScrollAnimations();
    initCountUp();
    initSmoothScroll();
    initAffiliateTracking();
    initExitPopup();
    initActiveNav();
  });

})();
