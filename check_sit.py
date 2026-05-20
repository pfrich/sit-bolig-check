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
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            locale="nb-NO",
            viewport={"width": 1600, "height": 1400},
        )

        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Cookie/samtykke
        for text in ["Godta", "Aksepter", "Tillat alle", "OK", "Jeg forstår"]:
            try:
                if click_text(page, text, required=False):
                    break
            except Exception:
                pass

        # Eventuell navigasjon
        for text in ["Finn bolig", "Søk bolig", "Ledige boliger", "Boliger"]:
            try:
                if click_text(page, text, required=False):
                    page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        save_debug(page, "01_before_filters")

        # Filtre som skal velges
        filters = [
            "Jeg er førstegangsstudent",
            "Trondheim",
            "Hybel i kollektiv m/eget bad",
        ]

        for text in filters:
            click_text(page, text, required=True)

        save_debug(page, "02_after_filters")

        # Datoer: input type=date må bruke YYYY-MM-DD
        page.locator("input[name='minAvailableDate']").fill("2026-07-01")
        page.locator("input[name='maxAvailableDate']").fill("2026-08-05")

        page.wait_for_timeout(1000)
        save_debug(page, "03_after_dates")

        # Trykk på den nederste Søk-knappen
        page.get_by_role("button", name="Søk").last.click(timeout=10000)

        page.wait_for_timeout(5000)
        save_debug(page, "04_results")

        body = page.inner_text("body")
        body_lower = body.lower()

        if "ingen treff med valgte søkeord" in body_lower:
            print("Ingen treff med valgte søkeord. Varsler ikke.")

        else:
            notify(
                "Mulig ledig SiT-hybel funnet!\n\n"
                "Område: Trondheim\n"
                "Boligtype: Hybel i kollektiv m/eget bad\n"
                "Periode: 01.07.2026 - 05.08.2026\n\n"
                "Sjekk manuelt:\n"
                "https://bolig.sit.no/"
            )

            print("Varsel sendt.")

        browser.close()


if __name__ == "__main__":
    main()
