(function () {
  const targetDate = '__TARGET_DATE__';
  const ymd = targetDate.replace(/-/g, '');
  const text = el => (el && (el.innerText || el.textContent) || '').trim();
  const visible = el => !!(el && el.getClientRects().length);
  const body = text(document.body);
  const blocked = /just a moment|verify you are human|checking your browser|access denied|enable javascript and cookies to continue/i.test(body.slice(0, 2500));
  // Observed mobile page state, 2026-11-16. Read only the public venue/show query;
  // never serialize the surrounding global state, which also contains cookies/config.
  const query = window.__INITIAL_STATE__?.venueShowtimesFunctionalApi?.queries?.['getShowtimesByVenue-ALUC-' + ymd];
  const data = query?.data?.showDetailsTransformed;
  if (!blocked && data && data.Date === ymd && data.Venues?.VenueCode === 'ALUC' &&
      /ALLU Cinemas\s*:\s*Kokapet/i.test(data.Venues?.VenueName || '')) {
    const selectedControl = Array.from(document.querySelectorAll('[aria-pressed="true"], [aria-selected="true"]'))
      .find(el => /\d{1,2}/.test(text(el)) && /Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec/i.test(text(el)));
    const month = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][Number(targetDate.slice(5,7))-1];
    const selectedText = text(selectedControl).replace(/\s+/g, ' ');
    const selectedMatches = !!selectedControl && new RegExp('(?:^|\\D)' + Number(targetDate.slice(8,10)) + '(?:\\D|$)').test(selectedText) && selectedText.toLowerCase().includes(month.toLowerCase());
    const records = [];
    for (const movie of data.Event || []) for (const variant of movie.ChildEvents || []) for (const show of variant.ShowTimes || []) {
      if (show.ShowDateCode !== ymd || !String(show.ShowDateTime || '').startsWith(ymd)) continue;
      // The mobile UI renders status 2 amber (fast filling), 3 green (available).
      // Other numeric statuses remain UNKNOWN until independently verified.
      let availability = 'UNKNOWN';
      if (data.Venues.isVenueDown === false && query.isSuccess === true) {
        if (String(show.AvailStatus) === '2') availability = 'FAST_FILLING';
        if (String(show.AvailStatus) === '3') availability = 'AVAILABLE';
      }
      records.push({ movieId: String(variant.EventCode || ''), title: movie.EventTitle || variant.EventName || '',
        language: variant.EventLanguage || '', format: [variant.EventDimension, show.Attributes].filter(Boolean).join(' · '),
        time: show.ShowTime || '', availability, url: '', sessionId: String(show.SessionId || '') });
    }
    return JSON.stringify({resolvedUrl:location.href, venue:'ALUC', selectedDate:selectedMatches ? targetDate : '', blocked:false,
      empty: selectedMatches && query.isSuccess === true && data.Venues.isVenueDown === false && Array.isArray(data.Event) && data.Event.length === 0,
      shows:records, diagnostic:'adapter=mobile-state-v1; selectedDateConfirmed=' + selectedMatches});
  }
  const venue = /ALLU Cinemas\s*:\s*Kokapet/i.test(text(document.querySelector('h1')) || '') ? 'ALUC' : '';

  // A retained URL alone is never selected-date evidence. Use the selected date control.
  const dateNodes = Array.from(document.querySelectorAll(
    '[aria-selected="true"], [aria-current="date"], .date-container .active, .date-container .selected, ' +
    '.date-list .active, .dates-wrapper .active, .date-details._active, .date-details.active, .date-details.selected, ' +
    '[class*="date"].__selected, [class*="date"].__active, [data-date].active, [data-date].selected'
  )).filter(visible);
  const normalizeDate = value => {
    const match = (value || '').match(/(?:^|\D)(20\d{2})[-/]?(\d{2})[-/]?(\d{2})(?:$|\D)/);
    return match ? match[1] + '-' + match[2] + '-' + match[3] : '';
  };
  let selectedDate = '';
  for (const node of dateNodes) {
    const family = [node, ...node.querySelectorAll('[data-date], [data-date-time], a')];
    for (const candidate of family) {
      const values = ['data-date', 'data-date-time', 'data-show-date', 'href', 'aria-label'].map(k => candidate.getAttribute(k) || '');
      const found = values.map(normalizeDate).find(Boolean);
      if (found) { selectedDate = found; break; }
    }
    if (selectedDate) break;
  }

  // Legacy BMS venue markup: every session must remain inside its movie row.
  const rows = Array.from(document.querySelectorAll('li.list, .movie-list > li, [data-event-id]'));
  const shows = [];
  for (const row of rows) {
    if (!visible(row) || row.closest('footer')) continue;
    const titleNode = row.querySelector('.__movie-name, a[data-event-code], a[href*="/movies/"][href*="/ET"]');
    const title = text(titleNode).replace(/\s*\((?:U|UA|A|S|UA\d+\+?)\)\s*$/i, '').trim();
    if (!title) continue;
    const movieIds = Array.from(row.querySelectorAll('a[href*="/movies/"][href*="/ET"]')).map(a => (a.href.match(/ET\d+/) || [])[0]).filter(Boolean);
    if (new Set(movieIds).size > 1) continue;
    const movieId = row.getAttribute('data-event-id') || (titleNode.href && (titleNode.href.match(/ET\d+/) || [])[0]) || '';
    const language = text(row.querySelector('.__language, .language, [data-language]'));
    const rowFormat = text(row.querySelector('.__format, .format, [data-format]'));
    const pills = Array.from(row.querySelectorAll('a.showtime-pill, .showtime-pill-container .showtime-pill, [data-session-id]'));
    for (const pill of pills) {
      if (!visible(pill)) continue;
      const time = (text(pill.querySelector('.__text')) || text(pill)).match(/\b(?:0?[1-9]|1[0-2]):[0-5][0-9]\s*(?:AM|PM)\b/i);
      if (!time) continue;
      const session = pill.closest('.showtime-pill-container') || pill;
      const metadata = (pill.className + ' ' + session.className + ' ' + (pill.getAttribute('data-availability') || '')).toLowerCase();
      let availability = 'UNKNOWN';
      if (/sold.?out|soldout|disabled|unavailable|housefull/.test(metadata) || pill.getAttribute('aria-disabled') === 'true') availability = 'SOLD_OUT';
      else if (/(?:^|\s)(?:_?available|available-show|available)(?:\s|$)/.test(metadata)) availability = 'AVAILABLE';
      else if (/fast.?filling|_filling|filling/.test(metadata)) availability = 'FAST_FILLING';
      const sessionFormat = text(session.querySelector('.__attribute, .__attributes, .attribute, .showtime-attributes, [data-format]'));
      let url = '';
      const href = pill.getAttribute('href');
      if (href && !/^(javascript:|#)/i.test(href)) { try { url = new URL(href, location.href).href; } catch (_) {} }
      shows.push({ movieId, title, language, format: [rowFormat, sessionFormat].filter(Boolean).join(' · '), time: time[0], availability, url });
    }
  }
  const empty = /no shows available|no shows found|no showtimes available|no screenings available/i.test(
    text(document.querySelector('main, #showtimes, .movie-list, .no-shows, .no-shows-message'))
  );
  return JSON.stringify({ resolvedUrl: location.href, venue, selectedDate, blocked, empty, shows,
    diagnostic: 'rows=' + rows.length + '; selectedControls=' + dateNodes.length + '; target=' + ymd });
})();
