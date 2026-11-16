# ALLU Cinemas cloud feasibility probe

This is a read-only source-access test for ALLU Cinemas Tracker. It is **not an active cloud watcher**. It has no cron schedule, device tokens, watchlists, Firebase credentials, TMDB keys, or push sending code.

The manual GitHub Actions workflow launches ordinary Chromium with standard mobile-device emulation and executes the same extractor as the Android app. It checks two near-future dates and an unavailable/distant future date twice. A blocked request, wrong selected date, unsupported content, sold-out status, or unknown availability cannot pass the monitoring gate.

The workflow can test either headless Chromium or the full browser under Xvfb. Date checks are spaced 10 seconds apart and rounds 60 seconds apart. This changes browser execution and request pacing; it does not automate challenges or add stealth plugins.

Reports contain only request status, timestamps, extractor hash, and public movie/show records. Browser profiles, cookies, page HTML, and arbitrary page state are never uploaded. Third-party workflow actions are pinned to verified commit SHAs.

## Run

```sh
python -m pip install -r cloud-probe/requirements.txt
python -m playwright install chromium
python -m unittest discover -s cloud-probe -p 'test_*.py' -v
python cloud-probe/probe.py --rounds 2 --interval 30
```

Exit 0 means both near-future dates had verified bookable shows in both rounds. Exit 2 means the source-access gate did not pass; inspect the sanitized report before attributing the failure to blocking, empty schedules, or changed markup. A passing short probe does not guarantee reliable long-term access.

No recurring workflow or cloud push integration should be enabled until the hosted-runner probe passes. After that, reminder sync, direct-device push delivery, and local Room generation checks must be wired and tested separately. GitHub cron has no punctual-delivery guarantee.
