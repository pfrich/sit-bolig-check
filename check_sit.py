import requests
from playwright.sync_api import sync_playwright

TOPIC = "per-sit-hybel-2026"
URL = "https://bolig.sit.no/"


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


def click_text(page, text, required=True):
    locator = page.get_by_text(text, exact=False)

    if locator.count() == 0:
        if required:
            save_debug(page, f"missing_{safe_name(text)}")
            raise Exception(f"Fant ikke tekst: {text}")
        return False

    locator.first.click(timeout=10000)
    page.wait_for_timeout(800)
    return True


def safe_name(text):
    return (
        text.replace(" ", "_")
        .replace("/", "_")
        .replace("æ", "ae")
        .replace("ø", "oe")
        .replace("å", "aa")
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            locale="nb-NO",
            viewport={"width": 1600, "height": 1200},
        )

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        page.wait_for_timeout(3000)

        # Cookie/samtykke
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

        # Eventuell navigasjon til søkeside
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

        # Filtre
        filters = [
            "Tillitsbasert utvalg",
            "Jeg er førstegangsstudent",
            "Trondheim",
            "Hybel i kollektiv m/eget bad",
        ]

        for text in filters:
            click_text(page, text, required=True)

        save_debug(page, "02_after_filters")

        # Datofelter - input type=date må bruke YYYY-MM-DD
        min_date = page.locator("input[name='minAvailableDate']")
        max_date = page.locator("input[name='maxAvailableDate']")

        if min_date.count() == 0:
            save_debug(page, "missing_min_date")
            raise Exception("Fant ikke datofeltet minAvailableDate")

        if max_date.count() == 0:
            save_debug(page, "missing_max_date")
            raise Exception("Fant ikke datofeltet maxAvailableDate")

        min_date.fill("2026-07-01")
        max_date.fill("2026-08-05")

        page.wait_for_timeout(1000)

        save_debug(page, "03_after_dates")

        # Klikk søk
        try:
            page.get_by_role("button", name="Søk").first.click(timeout=10000)
        except Exception:
            page.get_by_text("Søk", exact=False).first.click(timeout=10000)

        page.wait_for_timeout(5000)

        save_debug(page, "04_results")

        body = page.inner_text("body")
        body_lower = body.lower()

        no_hits = any(
            text in body_lower
            for text in [
                "ingen ledige",
                "0 treff",
                "ingen treff",
                "ingen treff med valgte søkeord",
                "fant ingen",
                "ingen boliger",
            ]
        )

        has_possible_hits = any(
            text in body_lower
            for text in [
                "hybel i kollektiv",
                "ledig fra",
                "månedsleie",
                "manedsleie",
                "kr per måned",
                "kr/mnd",
                "søknadsfrist",
            ]
        )

        if no_hits:
            print("Ingen treff funnet. Varsler ikke.")

        elif has_possible_hits:
            notify(
                "Mulig ledig SiT-hybel funnet!\n\n"
                "Område: Trondheim\n"
                "Boligtype: Hybel i kollektiv m/eget bad\n"
                "Periode: 01.07.2026 - 05.08.2026\n\n"
                "Sjekk manuelt:\n"
                "https://bolig.sit.no/"
            )
            print("Varsel sendt.")

        else:
            print("Ingen sikker treffindikasjon funnet. Varsler ikke.")

        browser.close()


if __name__ == "__main__":
    main()
