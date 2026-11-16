"""Read-only cloud feasibility check. This does not schedule monitoring or send alerts."""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

INDIA = timezone(timedelta(hours=5, minutes=30))


def venue_url(day: str) -> str:
    date.fromisoformat(day)
    return "https://in.bookmyshow.com/cinemas/hyderabad/allu-cinemas-kokapet/buytickets/ALUC/" + day.replace("-", "")


def validate_envelope(day: str, envelope: object) -> dict:
    result = {"date": day, "kind": "UNSUPPORTED", "shows": []}
    if not isinstance(envelope, dict):
        return result
    if envelope.get("blocked") is True:
        return result | {"kind": "BLOCKED"}
    location = urlsplit(str(envelope.get("resolvedUrl", "")))
    if (location.scheme != "https" or location.hostname != "in.bookmyshow.com" or
            location.username is not None or location.port not in (None, 443) or
            envelope.get("venue") != "ALUC" or envelope.get("selectedDate") != day):
        return result
    raw_shows = envelope.get("shows")
    if not isinstance(raw_shows, list):
        return result
    shows = []
    for raw in raw_shows:
        if not isinstance(raw, dict) or not isinstance(raw.get("title"), str) or not raw["title"].strip():
            continue
        time = str(raw.get("time", "")).replace("\u00a0", " ").strip()
        match = re.fullmatch(r"(0?[1-9]|1[0-2]):([0-5][0-9])\s*(AM|PM)", time, flags=re.I)
        if not match:
            continue
        minute = (int(match[1]) % 12 + (12 if match[3].upper() == "PM" else 0)) * 60 + int(match[2])
        format_label = str(raw.get("format", ""))
        screen = ("DOLBY_CINEMA" if "DOLBY CINEMA" in format_label.upper() else
                  "ATMOS" if "ATMOS" in format_label.upper() else "OTHER" if format_label else "UNKNOWN")
        availability = raw.get("availability")
        if availability not in ("AVAILABLE", "FAST_FILLING", "SOLD_OUT", "UNKNOWN"):
            availability = "UNKNOWN"
        # Retain public show fields only. Do not copy browser state or arbitrary envelope fields.
        shows.append({"movieId": str(raw.get("movieId", "")), "title": raw["title"].strip(),
                      "language": str(raw.get("language", "")), "format": screen,
                      "formatLabel": format_label, "startMinute": minute, "availability": availability,
                      "sessionId": str(raw.get("sessionId", ""))})
    if shows:
        return result | {"kind": "SUCCESS", "shows": shows}
    if not raw_shows and envelope.get("empty") is True:
        return result | {"kind": "EMPTY"}
    return result


def verdict(samples: list[dict], positive_dates: list[str], rounds: int) -> bool:
    """Both known active dates need a verified, bookable snapshot in every round."""
    return all(any(sample.get("round") == iteration and sample.get("date") == day and
                   sample.get("kind") == "SUCCESS" and
                   any(show.get("availability") in ("AVAILABLE", "FAST_FILLING") for show in sample.get("shows", []))
                   for sample in samples) for iteration in range(1, rounds + 1) for day in positive_dates)


async def check(page, script: str, day: str) -> dict:
    from playwright.async_api import TimeoutError as BrowserTimeout
    try:
        response = await page.goto(venue_url(day), wait_until="domcontentloaded", timeout=30_000)
        status = response.status if response else None
        if status in (403, 429):
            return {"date": day, "kind": "BLOCKED", "http_status": status, "shows": []}
        if status and status >= 400:
            return {"date": day, "kind": "NETWORK_FAILURE", "http_status": status, "shows": []}
        last = {"date": day, "kind": "UNSUPPORTED", "shows": []}
        for _ in range(20):
            payload = await page.evaluate(script.replace("__TARGET_DATE__", day))
            envelope = json.loads(payload) if isinstance(payload, str) else payload
            last = validate_envelope(day, envelope)
            last["http_status"] = status
            if last["kind"] in ("SUCCESS", "EMPTY", "BLOCKED"):
                return last
            await asyncio.sleep(.5)
        return last
    except BrowserTimeout:
        return {"date": day, "kind": "TIMEOUT", "shows": []}
    except Exception:
        return {"date": day, "kind": "NETWORK_FAILURE", "shows": []}


async def run(args) -> int:
    from playwright.async_api import async_playwright
    base = date.fromisoformat(args.start_date) if args.start_date else datetime.now(INDIA).date()
    positives = [(base + timedelta(days=offset)).isoformat() for offset in (1, 2)]
    future = (base + timedelta(days=30)).isoformat()
    script = Path(args.extractor).read_text(encoding="utf-8")
    samples = []
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch(headless=not args.headed)
        # Standard mobile browser emulation; no stealth plugin, borrowed cookies, or challenge automation.
        context = await browser.new_context(**runtime.devices["Pixel 7"])
        page = await context.new_page()
        for iteration in range(1, args.rounds + 1):
            for index, day in enumerate(positives + [future]):
                if index:
                    await asyncio.sleep(args.stagger)
                sample = await check(page, script, day)
                sample.update(round=iteration, checked_at=datetime.now(timezone.utc).isoformat())
                samples.append(sample)
                print(json.dumps({key: value for key, value in sample.items() if key != "shows"} |
                                 {"show_count": len(sample["shows"])}), flush=True)
            if iteration < args.rounds:
                await asyncio.sleep(args.interval)
        await context.close()
        await browser.close()
    eligible = verdict(samples, positives, args.rounds)
    report = {"schema_version": 1, "probe_only": True, "source": "ALUC", "start_date": base.isoformat(),
              "browser_mode": "headed" if args.headed else "headless", "stagger_seconds": args.stagger,
              "extractor_sha256": hashlib.sha256(script.encode()).hexdigest(),
              "positive_dates": positives, "future_date": future,
              "eligible_for_monitoring": eligible, "samples": samples}
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Cloud access gate: " + ("PASSED" if eligible else "NOT PASSED"), flush=True)
    return 0 if eligible else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extractor", default="app/src/main/assets/extract.js")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--rounds", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--interval", type=int, choices=(30, 45, 60), default=30)
    parser.add_argument("--stagger", type=int, choices=(0, 5, 10, 15), default=10)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--output", default="output/cloud-probe/report.json")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
