import argparse
import json
import re
from pathlib import Path
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

TOPIC = "per-sit-hybel-2026"
URL = "https://bolig.sit.no/"

DEFAULT_MIN_DATE = "2026-06-10"
DEFAULT_MAX_DATE = "2026-08-05"

AREA = "Trondheim"
HOUSING_TYPE = "Hybel i kollektiv m/eget bad"

FIRST_YEAR_STUDENT = True
TRUST_BASED_SELECTION = False

HEADLESS = True
DEBUG = False

SEEN_FILE = "seen_units.json"
MAX_SEEN_LINKS = 10
MAX_MESSAGE_ITEMS = 20

ACTIVE_FROM = date(2026, 5, 20)
ACTIVE_UNTIL = date(2026, 7, 30)

RUN_FROM_HOUR = 0          # 00:00 (midnatt)
RUN_FROM_MINUTE = 0
RUN_UNTIL_HOUR = 23        # 23:59 (slutten av dagen)
RUN_UNTIL_MINUTE = 59


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check available SiT housing units.")
    parser.add_argument(
        "--mode",
        choices=["new", "summary"],
        default="new",
        help="new = varsle bare nye boliger. summary = send alle treff i søket.",
    )
    parser.add_argument(
        "--from-date",
        default="",
        help="Overstyr fra-dato i søket, f.eks. 2026-08-01. Brukes typisk for summary.",
    )
    parser.add_argument(
        "--to-date",
        default="",
        help="Overstyr til-dato i søket, f.eks. 2026-08-31.",
    )
    return parser.parse_args()


def should_run_now() -> bool:
    now = datetime.now(ZoneInfo("Europe/Oslo"))

    if not (ACTIVE_FROM <= now.date() <= ACTIVE_UNTIL):
        print(f"Utenfor aktiv periode: {now.date()}")
        return False

    start = now.replace(hour=RUN_FROM_HOUR, minute=RUN_FROM_MINUTE, second=0, microsecond=0)
    end = now.replace(hour=RUN_UNTIL_HOUR, minute=RUN_UNTIL_MINUTE, second=0, microsecond=0)

    if not (start <= now <= end):
        print(f"Utenfor klokkeslett: {now}")
        return False

    return True


def notify(message: str, mode: str) -> None:
    title = "SiT bolig - oppsummering" if mode == "summary" else "SiT bolig"

    response = requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": "high", "Tags": "house"},
        timeout=10,
    )
    response.raise_for_status()


def load_seen_links() -> list[str]:
    path = Path(SEEN_FILE)

    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_seen_links(links: list[str]) -> None:
    trimmed = links[:MAX_SEEN_LINKS]

    Path(SEEN_FILE).write_text(
        json.dumps(trimmed, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_debug(page, name: str) -> None:
    page.screenshot(path=f"{name}.png", full_page=True)
    Path(f"{name}.txt").write_text(page.inner_text("body"), encoding="utf-8")


def click_text(page, text: str, required: bool = True) -> bool:
    """Click element by text without unnecessary waits."""
    locator = page.get_by_text(text, exact=False)

    if locator.count() == 0 and len(text.split()) > 1:
        locator = page.get_by_text(text.split()[-1], exact=False)

    if locator.count() == 0:
        if required:
            raise Exception(f"Fant ikke tekst: {text}")
        return False

    locator.first.scroll_into_view_if_needed(timeout=5000)
    locator.first.click(timeout=10000)
    return True


def try_click_one_of(page, texts: list[str]) -> bool:
    """Try clicking one of multiple texts efficiently."""
    for text in texts:
        try:
            if click_text(page, text, required=False):
                page.wait_for_timeout(800)
                return True
        except Exception:
            pass
    return False


def extract_available_from(text: str) -> str:
    match = re.search(
        r"Ledig fra\s+\d{1,2}\.\s+[A-Za-zÆØÅæøå]+\s+\d{4}",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(0).strip()

    for line in text.splitlines():
        if "ledig fra" in line.lower():
            return line.strip()

    return ""


def get_housing_items(page) -> list[dict]:
    links = page.locator("a[href*='/unit/']")
    items = []
    seen = set()

    for i in range(links.count()):
        link = links.nth(i)
        href = link.get_attribute("href")

        if not href:
            continue

        url = f"https://bolig.sit.no{href}" if href.startswith("/") else href

        if url in seen:
            continue

        seen.add(url)
        text = link.inner_text().strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        items.append(
            {
                "title": lines[0] if lines else "Ukjent bolig",
                "available_from": extract_available_from(text),
                "url": url,
            }
        )

    return items


def build_message(items: list[dict], mode: str, min_date: str, max_date: str) -> str:
    if mode == "summary":
        heading = "Daglig oppsummering av ledige SiT-boliger"
        item_heading = "Ledige boliger"
    else:
        heading = "Ny ledig SiT-hybel funnet!"
        item_heading = "Nye boliger"

    message = (
        f"{heading}\n\n"
        f"Område: {AREA}\n"
        f"Boligtype: {HOUSING_TYPE}\n"
        f"Periode: {min_date} - {max_date}\n"
        f"Antall: {len(items)}\n\n"
        f"{item_heading}:\n\n"
    )

    for item in items[:MAX_MESSAGE_ITEMS]:
        message += f"{item['title']}\n"

        if item["available_from"]:
            message += f"{item['available_from']}\n"

        message += f"{item['url']}\n\n"

    if len(items) > MAX_MESSAGE_ITEMS:
        message += f"... og {len(items) - MAX_MESSAGE_ITEMS} til.\n"

    return message.strip()


def main() -> None:
    args = parse_args()

    if not should_run_now():
        return

    min_date = args.from_date.strip() or DEFAULT_MIN_DATE
    max_date = args.to_date.strip() or DEFAULT_MAX_DATE

    print(f"Kjører modus: {args.mode}")
    print(f"Søkeperiode: {min_date} - {max_date}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)

        page = browser.new_page(
            locale="nb-NO",
            viewport={"width": 1024, "height": 768},
        )

        try:
            page.goto(URL, wait_until="networkidle", timeout=12000)

            # Lukk cookie/godkjenne-banner
            try_click_one_of(page, ["Godta", "Aksepter", "Tillat alle", "OK", "Jeg forstår"])

            # Åpne boligsøk
            try_click_one_of(page, ["Finn bolig", "Søk bolig", "Ledige boliger", "Boliger"])

            # Velg filteralternativer
            if FIRST_YEAR_STUDENT:
                try:
                    click_text(page, "førstegangsstudent")
                except Exception:
                    pass

            if TRUST_BASED_SELECTION:
                try:
                    click_text(page, "Tillitsbasert utvalg")
                except Exception:
                    pass

            click_text(page, AREA)
            click_text(page, HOUSING_TYPE)

            page.locator("input[name='minAvailableDate']").fill(min_date)
            page.locator("input[name='maxAvailableDate']").fill(max_date)

            page.get_by_role("button", name="Søk").last.click(timeout=7000)
            page.wait_for_timeout(500)

            if DEBUG:
                save_debug(page, "result")

            body_lower = page.inner_text("body").lower()

            if "ingen treff med valgte søkeord" in body_lower:
                print("Ingen treff. Varsler ikke.")
                return

            housing_items = get_housing_items(page)

            if not housing_items:
                print("Fant treffside, men ingen boliglenker. Varsler ikke.")
                return

            if args.mode == "summary":
                items_to_notify = housing_items
                print("Summary-modus: filtrerer ikke mot seen_units.json.")
            else:
                seen_links = load_seen_links()
                seen_set = set(seen_links)

                items_to_notify = [
                    item for item in housing_items
                    if item["url"] not in seen_set
                ]

                # Oppdater seen_units.json bare i new-modus
                updated_seen_links = [item["url"] for item in housing_items]
                updated_seen_links.extend(
                    link for link in seen_links
                    if link not in updated_seen_links
                )
                save_seen_links(updated_seen_links)

            if not items_to_notify:
                print("Ingen boliger å varsle.")
                return

            notify(build_message(items_to_notify, args.mode, min_date, max_date), args.mode)
            print(f"Varsel sendt for {len(items_to_notify)} boliger.")

        except Exception as e:
            if DEBUG:
                save_debug(page, "error")

            notify(f"SiT-sjekk feilet:\n{type(e).__name__}: {e}", args.mode)
            raise

        finally:
            browser.close()


if __name__ == "__main__":
    main()
