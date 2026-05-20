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
            "Tags": "house"
        }
    )


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(
            "https://bolig.sit.no/",
            wait_until="networkidle",
            timeout=60000
        )

        # Skjermbilde for feilsøking
        page.screenshot(path="start.png", full_page=True)

        # Velg filtre
        page.get_by_text("Tillitsbasert utvalg", exact=False).click(timeout=10000)
        page.get_by_text("Jeg er førstegangsstudent", exact=False).click(timeout=10000)
        page.get_by_text("Trondheim", exact=False).click(timeout=10000)
        page.get_by_text("Hybel i kollektiv m/eget bad", exact=False).click(timeout=10000)

        # Datoer
        page.get_by_label("Tidligst", exact=False).fill("01.07.2026")
        page.get_by_label("Senest", exact=False).fill("05.08.2026")

        # Søk
        page.get_by_role("button", name="Søk").click()

        page.wait_for_load_state("networkidle")

        page.screenshot(path="resultat.png", full_page=True)

        body = page.inner_text("body")

        no_hits = (
            "Ingen ledige" in body
            or "0 treff" in body
            or "Ingen treff" in body
        )

        if not no_hits:
            notify(
                "Mulig ledig SiT-hybel funnet!\n\n"
                "Trondheim\n"
                "Hybel i kollektiv m/eget bad\n"
                "01.07.2026–05.08.2026\n\n"
                "https://bolig.sit.no/"
            )

        browser.close()

except Exception as e:
    notify(f"SiT-sjekk feilet:\n{type(e).__name__}: {e}")
    raise
