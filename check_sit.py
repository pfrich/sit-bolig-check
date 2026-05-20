import requests
from playwright.sync_api import sync_playwright

TOPIC = "per-sit-hybel-2026"


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


def click_if_exists(page, text):
    locator = page.get_by_text(text, exact=False)

    if locator.count() > 0:
        locator.first.click(timeout=10000)
        page.wait_for_timeout(1000)
        return True

    return False


def main():
    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            locale="nb-NO",
            viewport={"width": 1600, "height": 1200},
        )

        page.goto(
            "https://bolig.sit.no/",
            wait_until="networkidle",
            timeout=60000,
        )

        save_debug(page, "01_start")

        # Cookie-banner
        for text in [
            "Godta",
            "Aksepter",
            "Tillat alle",
            "OK",
            "Jeg forstår",
        ]:
            try:
                if click_if_exists(page, text):
                    break
            except Exception:
                pass

        save_debug(page, "02_after_cookie")

        # Klikk eventuell bolig/søk-knapp
        for text in [
            "Finn bolig",
            "Søk bolig",
            "Ledige boliger",
            "Boliger",
        ]:
            try:
                if click_if_exists(page, text):
                    page.wait_for_load_state("networkidle")
                    break
            except Exception:
                pass

        save_debug(page, "03_after_navigation")

        # Velg filtre
        filters = [
            "Tillitsbasert utvalg",
            "Jeg er førstegangsstudent",
            "Trondheim",
            "Hybel i kollektiv m/eget bad",
        ]

        for text in filters:

            locator = page.get_by_text(text, exact=False)

            if locator.count() == 0:
                save_debug(page, f"missing_{text}")
                notify(f"Fant ikke filter: {text}")
                raise Exception(f"Fant ikke filter: {text}")

            locator.first.click(timeout=10000)

            page.wait_for_timeout(1000)

        save_debug(page, "04_after_filters")

        # Finn synlige inputfelt
        date_inputs = page.locator(
            "input:not([type='checkbox']):not([type='radio'])"
        )

        visible_inputs = []

        total = date_inputs.count()

        for i in range(total):

            try:
                element = date_inputs.nth(i)

                if element.is_visible():
                    visible_inputs.append(element)

            except Exception:
                pass

        print(f"Fant {len(visible_inputs)} synlige inputfelt")

        if len(visible_inputs) < 2:
            save_debug(page, "error_inputs")
            raise Exception(
                f"Fant bare {len(visible_inputs)} synlige inputfelt"
            )

        # Fyll datoer
        visible_inputs[0].click()
        visible_inputs[0].fill("01.07.2026")

        visible_inputs[1].click()
        visible_inputs[1].fill("05.08.2026")

        page.wait_for_timeout(1000)

        save_debug(page, "05_after_dates")

        # Klikk søk
        search_button = page.get_by_role(
            "button",
            name="Søk",
        )

        if search_button.count() > 0:
            search_button.first.click(timeout=10000)
        else:
            page.get_by_text("Søk", exact=False).first.click(
                timeout=10000
            )

        page.wait_for_load_state("networkidle")

        page.wait_for_timeout(3000)

        save_debug(page, "06_results")

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
            print("Ingen treff")
        else:

            notify(
                "Mulig ledig SiT-hybel funnet!\n\n"
                "Trondheim\n"
                "Hybel i kollektiv m/eget bad\n"
                "01.07.2026 - 05.08.2026\n\n"
                "https://bolig.sit.no/"
            )

            print("Varsel sendt")

        browser.close()


if __name__ == "__main__":
    main()
