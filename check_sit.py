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

        page.goto(URL, wait_until="networkidle", timeout=60000)
        save_debug(page, "01_start")

        # Cookie/samtykke
        for text in ["Godta", "Aksepter", "Tillat alle", "OK", "Jeg forstår"]:
            try:
                if click_text(page, text, required=False):
                    break
            except Exception:
                pass

        save_debug(page, "02_after_cookie")

        # Eventuell navigasjon til søk/boligoversikt
        for text in ["Finn bolig", "Søk bolig", "Ledige boliger", "Boliger"]:
            try:
                if click_text(page, text, required=False):
                    page.wait_for_load_state("networkidle", timeout=30000)
                    break
            except Exception:
                pass

        save_debug(page, "03_after_navigation")

        # Filtre
        filters = [
            "Tillitsbasert utvalg",
            "Jeg er førstegangsstudent",
            "Trondheim",
            "Hybel i kollektiv m/eget bad",
        ]

        for text in filters:
            try:
                click_text(page, text, required=True)
            except Exception as e:
                notify(f"SiT-sjekk feilet ved filter:\n{text}\n\n{e}")
                raise

        save_debug(page, "04_after_filters")

        # Finn aktuelle tekst-/datofelt.
        # Viktig: ekskluder checkbox, radio og number.
        inputs = page.locator(
            "input:not([type='checkbox']):not([type='radio']):not([type='number'])"
        )

        candidates = []

        for i in range(inputs.count()):
            el = inputs.nth(i)

            try:
                if not el.is_visible():
                    continue

                input_type = el.get_attribute("type")
                name = el.get_attribute("name")
                input_id = el.get_attribute("id")
                placeholder = el.get_attribute("placeholder")
                aria = el.get_attribute("aria-label")

                print(
                    f"Synlig input {i}: "
                    f"type={input_type}, "
                    f"name={name}, "
                    f"id={input_id}, "
                    f"placeholder={placeholder}, "
                    f"aria={aria}"
                )

                candidates.append(el)

            except Exception:
                pass

        print(f"Fant {len(candidates)} aktuelle synlige inputfelt")

        if len(candidates) < 2:
            save_debug(page, "error_too_few_inputs")
            notify("SiT-sjekk feilet: fant ikke to datofelt.")
            raise Exception("Fant ikke to datofelt")

        # Forsøk først label-basert
        filled = False

        try:
            page.get_by_label("Tidligst", exact=False).fill(
                "01.07.2026", timeout=5000
            )
            page.get_by_label("Senest", exact=False).fill(
                "05.08.2026", timeout=5000
            )
            filled = True
        except Exception:
            pass

        # Fallback: bruk de to siste relevante feltene,
        # fordi de første kan være søkefelt eller andre tekstfelt.
        if not filled:
            candidates[-2].click()
            candidates[-2].fill("01.07.2026")

            candidates[-1].click()
            candidates[-1].fill("05.08.2026")

        page.wait_for_timeout(1000)
        save_debug(page, "05_after_dates")

        # Klikk Søk
        try:
            page.get_by_role("button", name="Søk").first.click(timeout=10000)
        except Exception:
            page.get_by_text("Søk", exact=False).first.click(timeout=10000)

        page.wait_for_load_state("networkidle", timeout=30000)
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
