(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const themes = ['editorial', 'mono', 'dune', 'blueprint', 'ink'];
  const toast = $('[data-status]');
  let toastTimer;
  const announce = (message) => {
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 2400);
  };

  // Support the reference reader's ?date=YYYY-MM-DD URL on a project Pages root.
  // Only navigate to known issues; never synthesize an unverified destination.
  const targetDate = new URLSearchParams(location.search).get('date');
  if (targetDate && /^\d{4}-\d{2}-\d{2}$/.test(targetDate)) {
    const entry = $$('[data-date-entry]').find((link) => link.querySelector('time').dateTime === targetDate);
    if (entry && $('[data-report-date]')?.dataset.reportDate !== targetDate) {
      location.replace(entry.href);
      return;
    }
    if (!entry) announce('No issue has been generated for that date');
  }

  const syncThemes = () => $$('[data-set-theme]').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.setTheme === document.documentElement.dataset.theme));
  });
  syncThemes();
  $$('[data-set-theme]').forEach((button) => button.addEventListener('click', () => {
    const theme = button.dataset.setTheme;
    if (!themes.includes(theme)) return;
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('ai-daily-theme', theme); } catch (_) { /* Private mode. */ }
    syncThemes();
    $('.theme-picker').open = false;
  }));

  const sidebar = $('#archive-sidebar');
  const openButton = $('[data-open-archive]');
  const backdrop = $('.sidebar-backdrop');
  const closeArchive = () => {
    document.body.classList.remove('sidebar-open');
    openButton.setAttribute('aria-expanded', 'false');
    backdrop.hidden = true;
  };
  openButton.addEventListener('click', () => {
    document.body.classList.add('sidebar-open');
    openButton.setAttribute('aria-expanded', 'true');
    backdrop.hidden = false;
    sidebar.querySelector('[data-close-archive]').focus();
  });
  $$('[data-close-archive]').forEach((button) => button.addEventListener('click', () => {
    closeArchive();
    openButton.focus();
  }));
  const desktop = matchMedia('(min-width: 761px)');
  desktop.addEventListener('change', () => { if (desktop.matches) closeArchive(); });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      if (document.body.classList.contains('sidebar-open')) { closeArchive(); openButton.focus(); }
      $$('.theme-picker, .floating-toc').forEach((details) => {
        if (details.open) { details.open = false; details.querySelector('summary').focus(); }
      });
    }
    if (event.key === 'Tab' && document.body.classList.contains('sidebar-open')) {
      const targets = [...sidebar.querySelectorAll('a[href], button, input')].filter((el) => el.getClientRects().length);
      const first = targets[0], last = targets.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  document.addEventListener('click', (event) => {
    $$('.theme-picker, .floating-toc').forEach((details) => { if (!details.contains(event.target)) details.open = false; });
  });

  const search = (input, selector, emptySelector) => {
    if (!input) return;
    input.addEventListener('input', () => {
      const query = input.value.trim().toLocaleLowerCase();
      let matches = 0;
      $$(selector).forEach((entry) => {
        entry.hidden = !entry.dataset.searchText.toLocaleLowerCase().includes(query);
        if (!entry.hidden) matches++;
      });
      $(emptySelector).hidden = matches > 0;
      if (selector === '[data-date-entry]') $$('.date-group').forEach((group) => {
        group.hidden = ![...group.querySelectorAll('[data-date-entry]')].some((entry) => !entry.hidden);
      });
    });
  };
  search($('[data-archive-search]'), '[data-date-entry]', '[data-search-empty]');
  search($('[data-list-search]'), '[data-archive-entry]', '[data-list-empty]');

  $('[data-copy-link]').addEventListener('click', async () => {
    const issue = $('[data-report-date]');
    const url = issue ? new URL(`${document.body.dataset.siteRoot}issues/${issue.dataset.reportDate}/`, location.href).href : location.href;
    try { await navigator.clipboard.writeText(url); announce('Link to this issue copied'); }
    catch (_) { announce('Could not copy. Copy the URL from your browser instead.'); }
  });

  $$('[href^="#item-"]').forEach((link) => link.addEventListener('click', () => {
    const toc = $('.floating-toc');
    if (toc) toc.open = false;
  }));
  const progress = $('[data-reading-progress]');
  const backTop = $('[data-back-top]');
  let scheduled = false;
  const updateProgress = () => {
    const total = document.documentElement.scrollHeight - window.innerHeight;
    progress.style.transform = `scaleX(${total > 0 ? Math.min(1, Math.max(0, window.scrollY / total)) : 0})`;
    if (backTop) backTop.hidden = window.scrollY < 450;
    let active = null;
    $$('[data-article]').forEach((article) => { if (article.getBoundingClientRect().top < 160) active = article.id; });
    $$('.toc-panel a').forEach((link) => link.classList.toggle('active', link.hash === `#${active}`));
    scheduled = false;
  };
  addEventListener('scroll', () => { if (!scheduled) { scheduled = true; requestAnimationFrame(updateProgress); } }, { passive: true });
  addEventListener('resize', updateProgress);
  updateProgress();
  backTop?.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  });
})();
