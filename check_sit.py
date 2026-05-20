import requests
from playwright.sync_api import sync_playwright

# =========================================================
# KONFIGURASJON
# =========================================================

TOPIC = "per-sit-hybel-2026"
URL = "https://bolig.sit.no/"

MIN_DATE = "2026-06-10"
MAX_DATE = "2026-08-05"

AREA = "Trondheim"
HOUSING_TYPE = "Hybel i kollektiv m/eget bad"

FIRST_YEAR_STUDENT = True
TRUST_BASED_SELECTION = False

HEADLESS = True
DEBUG = False

# =========================================================


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
    locator = page.get_by_text(text, exact=False)

    if locator.count() == 0:
        if required:
            if DEBUG:
                save_debug(page, f"missing_{safe_name(text)}")
            raise Exception(f"Fant ikke tekst: {text}")
        return False

    locator.first.click(timeout=7000)
    page.wait_for_timeout(250)
    return True


def get_housing_links(page) -> list[str]:
    links = page.locator("a[href*='/unit/']")
    result = []

    for i in range(links.count()):
        href = links.nth(i).get_attribute("href")
        if not href:
            continue

        full_url = f"https://bolig.sit.no{href}" if href.startswith("/") else href

        if full_url not in result:
            result.append(full_url)

    return result


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)

        page = browser.new_page(
            locale="nb-NO",
            viewport={"width": 1500, "height": 1200},
        )

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1000)

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
                        page.wait_for_timeout(1000)
                        break
                except Exception:
                    pass

            if FIRST_YEAR_STUDENT:
                click_text(page, "Jeg er førstegangsstudent")

            if TRUST_BASED_SELECTION:
                click_text(page, "Tillitsbasert utvalg")

            click_text(page, AREA)
            click_text(page, HOUSING_TYPE)

            page.locator("input[name='minAvailableDate']").fill(MIN_DATE)
            page.locator("input[name='maxAvailableDate']").fill(MAX_DATE)

            page.get_by_role("button", name="Søk").last.click(timeout=7000)
            page.wait_for_timeout(2500)

            if DEBUG:
                save_debug(page, "result")

            body_lower = page.inner_text("body").lower()

            if "ingen treff med valgte søkeord" in body_lower:
                print("Ingen treff. Varsler ikke.")
                return

            housing_links = get_housing_links(page)

            message = (
                "Mulig ledig SiT-hybel funnet!\n\n"
                f"Område: {AREA}\n"
                f"Boligtype: {HOUSING_TYPE}\n"
                f"Periode: {MIN_DATE} - {MAX_DATE}\n\n"
            )

            if housing_links:
                message += "Lenker:\n\n"
                message += "\n".join(housing_links[:10])
            else:
                message += "Sjekk søket manuelt:\nhttps://bolig.sit.no/"

            notify(message)
            print("Varsel sendt.")

        except Exception as e:
            if DEBUG:
                save_debug(page, "error")

            notify(f"SiT-sjekk feilet:\n{type(e).__name__}: {e}")
            raise

        finally:
            browser.close()


if __name__ == "__main__":
    main()
