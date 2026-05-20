import requests
from playwright.sync_api import sync_playwright

# =========================================================
# KONFIGURASJON
# =========================================================

TOPIC = "per-sit-hybel-2026"

MIN_DATE = "2026-06-13"
MAX_DATE = "2026-08-05"

AREA = "Trondheim"
HOUSING_TYPE = "Hybel i kollektiv m/eget bad"

FIRST_YEAR_STUDENT = True
TRUST_BASED_SELECTION = False

HEADLESS = True

URL = "https://bolig.sit.no/"

# =========================================================


def notify(text):
    requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=text.encode("utf-8"),
        headers={
            "Title": "SiT bolig",
            "Priority": "high",
            "Tags": "house",
        },
        timeout=20,
    )


def save_debug(page, name):
    page.screenshot(path=f"{name}.png", full_page=True)

    with open(f"{name}.txt", "w", encoding="utf-8") as f:
        f.write(page.inner_text("body"))


def safe_name(text):
    return (
        text.replace(" ", "_")
        .replace("/", "_")
        .replace("æ", "ae")
        .replace("ø", "oe")
        .replace("å", "aa")
    )


def click_text(page, text, required=True):

    locator = page.get_by_text(text, exact=False)

    if locator.count() == 0:

        if required:
            save_debug(page, f"missing_{safe_name(text)}")

            raise Exception(f"Fant ikke tekst: {text}")

        return False

    locator.first.click(timeout=10000)

    page.wait_for_timeout(700)

    return True


def main():

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=HEADLESS)

        page = browser.new_page(
            locale="nb-NO",
            viewport={"width": 1600, "height": 1400},
        )

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        page.wait_for_timeout(3000)

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
                if click_text(page, text, required=False):
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
                if click_text(page, text, required=False):

                    page.wait_for_timeout(2000)

                    break

            except Exception:
                pass

        save_debug(page, "01_before_filters")

        # -------------------------------------------------
        # Filtre
        # -------------------------------------------------

        if FIRST_YEAR_STUDENT:
            click_text(
                page,
                "Jeg er førstegangsstudent",
                required=True,
            )

        if TRUST_BASED_SELECTION:
            click_text(
                page,
                "Tillitsbasert utvalg",
                required=True,
            )

        click_text(
            page,
            AREA,
            required=True,
        )

        click_text(
            page,
            HOUSING_TYPE,
            required=True,
        )

        save_debug(page, "02_after_filters")

        # -------------------------------------------------
        # Datoer
        # -------------------------------------------------

        min_date = page.locator(
            "input[name='minAvailableDate']"
        )

        max_date = page.locator(
            "input[name='maxAvailableDate']"
        )

        if min_date.count() == 0:
            save_debug(page, "missing_min_date")

            raise Exception(
                "Fant ikke datofeltet minAvailableDate"
            )

        if max_date.count() == 0:
            save_debug(page, "missing_max_date")

            raise Exception(
                "Fant ikke datofeltet maxAvailableDate"
            )

        min_date.fill(MIN_DATE)

        max_date.fill(MAX_DATE)

        page.wait_for_timeout(1000)

        save_debug(page, "03_after_dates")

        # -------------------------------------------------
        # Søk
        # -------------------------------------------------

        page.get_by_role(
            "button",
            name="Søk",
        ).last.click(timeout=10000)

        page.wait_for_timeout(5000)

        save_debug(page, "04_results")

        # -------------------------------------------------
        # Resultater
        # -------------------------------------------------

        body = page.inner_text("body")

        body_lower = body.lower()

        NO_HITS_TEXTS = [
            "ingen treff med valgte søkeord",
            "ingen treff",
            "ingen ledige",
            "0 treff",
            "fant ingen",
            "ingen boliger",
        ]

        no_hits = any(
            text in body_lower
            for text in NO_HITS_TEXTS
        )

        if no_hits:

            print(
                "Ingen treff med valgte søkeord. Varsler ikke."
            )

        else:

            notify(
                "Mulig ledig SiT-hybel funnet!\n\n"
                f"Område: {AREA}\n"
                f"Boligtype: {HOUSING_TYPE}\n"
                f"Periode: {MIN_DATE} - {MAX_DATE}\n\n"
                "Sjekk manuelt:\n"
                "https://bolig.sit.no/"
            )

            print("Varsel sendt.")

        browser.close()


if __name__ == "__main__":
    main()
