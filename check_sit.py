import re
import requests
from datetime import date, datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

# =========================================================
# KONFIGURASJON
# =========================================================

TOPIC = "per-sit-hybel-2026"
URL = "https://bolig.sit.no/"

MIN_DATE = "2026-06-12"
MAX_DATE = "2026-08-05"

AREA = "Trondheim"
HOUSING_TYPE = "Hybel i kollektiv m/eget bad"

FIRST_YEAR_STUDENT = True
TRUST_BASED_SELECTION = False

HEADLESS = True
DEBUG = False

# Kjør kun i denne perioden
ACTIVE_FROM = date(2026, 5, 20)
ACTIVE_UNTIL = date(2026, 6, 19)

# Kjør kun mellom 06:30 og 23:00 norsk tid
RUN_FROM_HOUR = 6
RUN_FROM_MINUTE = 30
RUN_UNTIL_HOUR = 23
RUN_UNTIL_MINUTE = 0

# =========================================================


def should_run_now() -> bool:
    now = datetime.now(ZoneInfo("Europe/Oslo"))
    today = now.date()

    if today < ACTIVE_FROM or today > ACTIVE_UNTIL:
        print(f"Utenfor aktiv periode: {today}")
        return False

    start = now.replace(
        hour=RUN_FROM_HOUR,
        minute=RUN_FROM_MINUTE,
        second=0,
        microsecond=0,
    )

    end = now.replace(
        hour=RUN_UNTIL_HOUR,
        minute=RUN_UNTIL_MINUTE,
        second=0,
        microsecond=0,
    )

    if not (start <= now <= end):
        print(f"Utenfor klokkeslett: {now}")
        return False

    return True


def notify(message: str) -> None:
    requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": "SiT bolig",
            "Priority": "high",
            "Tags": "house",
        },
        timeout=10,
    )


def save_debug(page, name: str) -> None:
    page.screenshot(path=f"{name}.png", full_page=True)

    with open(f"{name}.txt", "w", encoding="utf-8") as f:
        f.write(page.inner_text("body"))


def safe_name(text: str) -> str:
    return (
        text.replace(" ", "_")
        .replace("/", "_")
        .replace("æ", "ae")
        .replace("ø", "oe")
        .replace("å", "aa")
    )


def click_text(page, text: str, required: bool = True) -> bool:

    page.wait_for_timeout(1000)

    locator = page.get_by_text(text, exact=False)

    # fallback hvis full tekst ikke finnes
    if locator.count() == 0:

        words = text.split()

        if len(words) > 1:
            locator = page.get_by_text(
                words[-1],
                exact=False,
            )

    if locator.count() == 0:

        if DEBUG:
            save_debug(page, f"missing_{safe_name(text)}")

        if required:
            raise Exception(f"Fant ikke tekst: {text}")

        return False

    locator.first.scroll_into_view_if_needed(
        timeout=5000
    )

    locator.first.click(timeout=10000)

    page.wait_for_timeout(400)

    return True


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

    for i in range(links.count()):

        link = links.nth(i)

        href = link.get_attribute("href")

        if not href:
            continue

        url = (
            f"https://bolig.sit.no{href}"
            if href.startswith("/")
            else href
        )

        text = link.inner_text().strip()

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        title = (
            lines[0]
            if lines
            else "Ukjent bolig"
        )

        available_from = extract_available_from(text)

        items.append(
            {
                "title": title,
                "available_from": available_from,
                "url": url,
            }
        )

    unique_items = []
    seen_urls = set()

    for item in items:

        if item["url"] in seen_urls:
            continue

        seen_urls.add(item["url"])

        unique_items.append(item)

    return unique_items


def build_message(
    housing_items: list[dict]
) -> str:

    message = (
        "Mulig ledig SiT-hybel funnet!\n\n"
        f"Område: {AREA}\n"
        f"Boligtype: {HOUSING_TYPE}\n"
        f"Periode: {MIN_DATE} - {MAX_DATE}\n\n"
    )

    if housing_items:

        message += "Boliger:\n\n"

        for item in housing_items[:10]:

            message += f"{item['title']}\n"

            if item["available_from"]:
                message += (
                    f"{item['available_from']}\n"
                )

            message += f"{item['url']}\n\n"

    else:

        message += (
            "Sjekk søket manuelt:\n"
            "https://bolig.sit.no/"
        )

    return message.strip()


def main() -> None:

    if not should_run_now():
        return

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=HEADLESS
        )

        page = browser.new_page(
            locale="nb-NO",
            viewport={
                "width": 1500,
                "height": 1200,
            },
        )

        try:

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=25000,
            )

            page.wait_for_timeout(1500)

            # -------------------------------------------------
            # Cookie/samtykke
            # -------------------------------------------------

            for text in [
                "Godta",
                "Aksepter",
                "Tillat alle",
                "OK",
                "Jeg forstår",
            ]:
                try:
                    if click_text(
                        page,
                        text,
                        required=False,
                    ):
                        break

                except Exception:
                    pass

            # -------------------------------------------------
            # Eventuell navigasjon
            # -------------------------------------------------

            for text in [
                "Finn bolig",
                "Søk bolig",
                "Ledige boliger",
                "Boliger",
            ]:
                try:
                    if click_text(
                        page,
                        text,
                        required=False,
                    ):

                        page.wait_for_timeout(1000)

                        break

                except Exception:
                    pass

            # -------------------------------------------------
            # Filtre
            # -------------------------------------------------

            if FIRST_YEAR_STUDENT:
                click_text(
                    page,
                    "førstegangsstudent",
                )

            if TRUST_BASED_SELECTION:
                click_text(
                    page,
                    "Tillitsbasert utvalg",
                )

            click_text(
                page,
                AREA,
            )

            click_text(
                page,
                HOUSING_TYPE,
            )

            # -------------------------------------------------
            # Datoer
            # -------------------------------------------------

            page.locator(
                "input[name='minAvailableDate']"
            ).fill(MIN_DATE)

            page.locator(
                "input[name='maxAvailableDate']"
            ).fill(MAX_DATE)

            # -------------------------------------------------
            # Søk
            # -------------------------------------------------

            page.get_by_role(
                "button",
                name="Søk",
            ).last.click(timeout=7000)

            page.wait_for_timeout(2500)

            if DEBUG:
                save_debug(page, "result")

            # -------------------------------------------------
            # Resultater
            # -------------------------------------------------

            body_lower = (
                page.inner_text("body").lower()
            )

            if (
                "ingen treff med valgte søkeord"
                in body_lower
            ):
                print(
                    "Ingen treff. Varsler ikke."
                )
                return

            housing_items = get_housing_items(page)

            notify(
                build_message(housing_items)
            )

            print("Varsel sendt.")

        except Exception as e:

            if DEBUG:
                save_debug(page, "error")

            notify(
                f"SiT-sjekk feilet:\n"
                f"{type(e).__name__}: {e}"
            )

            raise

        finally:

            browser.close()


if __name__ == "__main__":
    main()
