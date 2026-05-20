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
            save_debug(page, f"missing_{text}")
            raise Exception(f"Fant ikke tekst: {text}")
        return False

    locator.first.click(timeout=10000)
    page.wait_for_timeout(800)
    return True


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

        save_debug(page, "01_start")

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

        # Eventuell navigasjon
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

        save_debug(page, "02_navigation")

        # Filtre
        filters = [
            "Tillitsbasert utvalg",
            "Jeg er førstegangsstudent",
            "Trondheim",
            "Hybel i kollektiv m/eget bad",
        ]

        for text in filters:
            click_text(page, text)

        save_debug(page, "03_filters")

        # Datofelter
        min_date = page.locator("input[name='minAvailableDate']")
        max_date = page.locator("input[name='maxAvailableDate']")

        if min_date.count() == 0:
            save_debug(page, "missing_min_date")
            raise Exception("Fant ikke minAvailableDate")

        if max_date.count() == 0:
            save_debug(page, "missing_max_date")
            raise Exception("Fant ikke maxAvailableDate")

        min_date.fill("2026-07-01")
        max_date.fill("2026-08-05")

        page.wait_for_timeout(1000)

        save_debug(page, "04_dates")

        # Klikk søk
        search_button = page.get_by_role(
            "button",
            name="Søk",
        )

        if search_button.count() > 0:
            search_button.first.click(timeout=10000)
        else:
            page.get_by_text(
                "Søk",
                exact=False
            ).first.click(timeout=10000)

        page.wait_for_timeout(5000)

        save_debug(page, "05_results")

        body = page.inner_text("body")

        no_hits = any(
            text in body
            for text in [
                "Ingen ledige",
                "0 treff",
                "Ingen treff",
                "Fant ingen",
                "Ingen boliger",
            ]
        )

        if no_hits:
            print("Ingen treff funnet.")
        else:

            notify(
                "Mulig ledig SiT-hybel funnet!\n\n"
                "Trondheim\n"
                "Hybel i kollektiv m/eget bad\n"
                "01.07.2026 - 05.08.2026\n\n"
                "https://bolig.sit.no/"
            )

            print("Varsel sendt.")

        browser.close()


if __name__ == "__main__":
    main()
