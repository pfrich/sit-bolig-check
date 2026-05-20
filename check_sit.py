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


def click_if_visible(page, text, timeout=3000):
    locator = page.get_by_text(text, exact=False)
    if locator.count() > 0:
        locator.first.click(timeout=timeout)
        return True
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            locale="nb-NO",
            viewport={"width": 1600, "height": 1200},
        )

        page.goto(URL, wait_until="networkidle", timeout=60000)
        save_debug(page, "01_start")

        # Cookie/samtykke hvis det vises
        for text in ["Godta", "Aksepter", "Tillat alle", "OK", "Jeg forstår"]:
            try:
                if click_if_visible(page, text):
                    page.wait_for_timeout(1000)
                    break
            except Exception:
                pass

        save_debug(page, "02_after_cookie")

        # Forsøk å komme til bolig-/søkeside hvis forsiden har knapp/lenke
        for text in ["Finn bolig", "Søk bolig", "Ledige boliger", "Boliger"]:
            try:
                if click_if_visible(page, text):
                    page.wait_for_load_state("networkidle", timeout=30000)
                    page.wait_for_timeout(1000)
                    break
            except Exception:
                pass

        save_debug(page, "03_search_page")

        # Velg filtre
        filter_texts = [
            "Tillitsbasert utvalg",
            "Jeg er førstegangsstudent",
            "Trondheim",
            "Hybel i kollektiv m/eget bad",
        ]

        for text in filter_texts:
            try:
                clicked = click_if_visible(page, text, timeout=10000)
                if not clicked:
                    raise Exception(f"Fant ikke filtertekst: {text}")
                page.wait_for_timeout(500)
            except Exception as e:
                save_debug(page, f"error_filter_{text.replace(' ', '_')}")
                notify(f"SiT-sjekk feilet ved filter:\n{text}\n\n{type(e).__name__}: {e}")
                raise

        save_debug(page, "04_after_filters")

# Datoer - fyll kun synlige tekst-/datofelt, ikke checkboxer
date_inputs = page.locator(
    "input:not([type='checkbox']):not([type='radio']):visible"
)

count = date_inputs.count()
print(f"Fant {count} synlige input-felt for dato/tekst")

if count < 2:
    save_debug(page, "error_date_inputs")
    raise Exception(f"Fant bare {count} synlige input-felt. Forventet minst 2.")

date_inputs.nth(0).click()
date_inputs.nth(0).fill("01.07.2026")

date_inputs.nth(1).click()
date_inputs.nth(1).fill("05.08.2026")

        save_debug(page, "05_after_dates")

        # Søk
        try:
            page.get_by_role("button", name="Søk").click(timeout=10000)
        except Exception:
            page.get_by_text("Søk", exact=False).first.click(timeout=10000)

        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        save_debug(page, "06_result")

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
                "Område: Trondheim\n"
                "Boligtype: Hybel i kollektiv m/eget bad\n"
                "Periode: 01.07.2026–05.08.2026\n\n"
                "Sjekk manuelt:\n"
                "https://bolig.sit.no/"
            )
            print("Varsel sendt.")

        browser.close()


if __name__ == "__main__":
    main()
