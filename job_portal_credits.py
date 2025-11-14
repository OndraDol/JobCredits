r"""
job_portal_credits.py
---------------------

Sjednocený skript / agent pro sledování kreditů na portálech Teamio a InWork
(Fajnsprava).

- Všechno je v jednom souboru.
- Pro každý portál se otevře viditelné Chromium okno s persistentním profilem.
- Ty se v prohlížeči přihlásíš / ověříš (Teamio i InWork), přepneš na stránku
  se stavem kreditů a v konzoli stiskneš Enter.
- Skript číslo přečte a doplní záznam do credits.json.

Použití v PowerShellu:

    cd C:\job_portal_credits
    .\.venv\Scripts\Activate.ps1

    # Spustit sběr pro oba portály (Teamio + InWork)
    python .\job_portal_credits.py

    # Jen Teamio
    python .\job_portal_credits.py teamio

    # Jen InWork
    python .\job_portal_credits.py inwork

Předpoklady:

- Vedle skriptu existuje nebo se vytvoří `credits.json`.
- Jednorázově jsi spustil `teamio_bootstrap_login.py`, aby vznikl profil
  `teamio_profile` a Teamio tě po dalším spuštění bralo jako známé zařízení.
- Pro InWork se používá `inwork_profile`, ale login/2FA zadáváš ručně.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, Page


# -----------------------------------------------------------------------------
# Společná konfigurace / cesty

PROJECT_ROOT = Path(__file__).resolve().parent
CREDITS_FILE_NAME = "credits.json"
CREDITS_FILE = PROJECT_ROOT / CREDITS_FILE_NAME

TEAMIO_PROFILE_DIR_NAME = "teamio_profile"
TEAMIO_PROFILE_DIR = PROJECT_ROOT / TEAMIO_PROFILE_DIR_NAME

INWORK_PROFILE_DIR_NAME = "inwork_profile"
INWORK_PROFILE_DIR = PROJECT_ROOT / INWORK_PROFILE_DIR_NAME


# -----------------------------------------------------------------------------
# Dataclass pro sjednocený výsledek z portálů


@dataclass
class PortalCredits:
    portal: str           # "Teamio" nebo "InWork"
    credits: int
    timestamp: datetime


# -----------------------------------------------------------------------------
# Helpers pro práci s credits.json


def load_entries(filepath: Path) -> List[Dict[str, Any]]:
    """Načte existující záznamy z credits.json (pokud existuje), jinak []."""
    if not filepath.exists():
        return []
    try:
        with filepath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_entries(new_records: List[PortalCredits], filepath: Path) -> None:
    """Přidá nové záznamy do credits.json a uloží se s odsazením a UTF-8."""
    entries = load_entries(filepath)
    for r in new_records:
        entries.append(
            {
                "timestamp": r.timestamp.isoformat(),
                "portal": r.portal,
                "credits": r.credits,
            }
        )
    with filepath.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


# -----------------------------------------------------------------------------
# TEAMIO část – převzato z původního check_credits.py


TEAMIO_CREDITS_URL: str = os.environ.get(
    "TEAMIO_CREDITS_URL",
    "https://my.teamio.com/recruit/dashboard",
)

# Optional CSS selector for the element containing the credits number.
# If you later find a stable data-testid or class, you can set e.g.:
#   TEAMIO_CREDITS_LOCATOR = "[data-testid='credits-balance']"
TEAMIO_CREDITS_LOCATOR: Optional[str] = os.environ.get(
    "TEAMIO_CREDITS_LOCATOR", None
)

TEAMIO_HEADLESS = False  # necháme viditelné okno prohlížeče


async def extract_teamio_credits_from_page(page: Page) -> int:
    """Přečte počet kreditů z aktuální Teamio stránky.

    Předpokládá, že stránka zobrazuje dashboard se
    'Zbývající předplatné' a řádek typu '1486  kreditů'.
    """
    # 1) Prefer explicit locator, pokud je nastavený
    if TEAMIO_CREDITS_LOCATOR:
        try:
            elem = page.locator(TEAMIO_CREDITS_LOCATOR)
            text = await elem.inner_text()
            digits = "".join(ch for ch in text if ch.isdigit())
            if digits:
                return int(digits)
        except Exception:
            # pokud selže, pokračuj na fallback
            pass

    # 2) Fallback – regex nad textem celé stránky
    body_text = await page.inner_text("body")

    # Hledáme primárně pattern: "1486  kreditů" / "1486 credits" atd.
    word_pattern = r"(?:kredit(?:ů|y)?\b|credit(?:s)?\b)"

    # číslo před slovem (typický případ u tebe: "1486  kreditů")
    pattern_direct = re.compile(r"(\d+)\s*" + word_pattern, re.IGNORECASE)
    # rezervně: slovo před číslem ("kreditů 1486")
    pattern_reverse = re.compile(word_pattern + r"\s*(\d+)", re.IGNORECASE)

    m = pattern_direct.search(body_text)
    if m:
        return int(m.group(1))

    m = pattern_reverse.search(body_text)
    if m:
        return int(m.group(1))

    raise RuntimeError(
        "Teamio: Nepodařilo se najít počet kreditů na stránce.\n"
        "Ujisti se, že jsi na dashboardu se 'Zbývající předplatné' a řádkem jako '1486  kreditů'."
    )


async def fetch_teamio_credits(headless: bool = TEAMIO_HEADLESS) -> PortalCredits:
    """Otevře Teamio dashboard, nechá tě přihlásit, vytáhne kredity a vrátí PortalCredits."""
    if not TEAMIO_PROFILE_DIR.exists():
        raise RuntimeError(
            f"Teamio profil '{TEAMIO_PROFILE_DIR}' neexistuje.\n"
            "Spusť jednou 'teamio_bootstrap_login.py', přihlas se do Teamia a profil se vytvoří."
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(TEAMIO_PROFILE_DIR),
            headless=headless,
        )

        page = await browser.new_page()
        print(f"[Teamio] Otevírám dashboard: {TEAMIO_CREDITS_URL}")
        await page.goto(TEAMIO_CREDITS_URL)
        await page.wait_for_load_state("networkidle")

        print(
            "\nV otevřeném okně prohlížeče zkontroluj, že jsi na dashboardu Teamia,\n"
            "kde vidíš 'Zbývající předplatné' a řádek '1486  kreditů'.\n"
            "- Pokud vidíš přihlašovací obrazovku, přihlas se (včetně 2FA z e-mailu),\n"
            "  dokud neuvidíš dashboard s kredity.\n"
            "- Pokud už dashboard vidíš, nedělej nic.\n"
        )
        input("[Teamio] Až budeš na správné stránce s kredity, stiskni Enter v této konzoli... ")

        # Po potvrzení pro jistotu znovu načteme dashboard (už jako přihlášení).
        await page.goto(TEAMIO_CREDITS_URL)
        await page.wait_for_load_state("networkidle")

        credits_value = await extract_teamio_credits_from_page(page)
        now = datetime.now(timezone.utc)

        await browser.close()
        print(f"[Teamio] {now.isoformat()} – {credits_value} kreditů")  # log do konzole

        return PortalCredits(
            portal="Teamio",
            credits=credits_value,
            timestamp=now,
        )


# -----------------------------------------------------------------------------
# INWORK část – zjednodušená, plně ruční login/2FA


INWORK_DASHBOARD_URL = os.environ.get(
    "INWORK_DASHBOARD_URL",
    "https://www.fajnsprava.cz/prihlasit.html",
)


INWORK_CREDITS_PATTERNS = [
    re.compile(r"Stav\s+kreditů\s*:\s*(\d+)", re.IGNORECASE),
    re.compile(r"\b(\d+)\s*kredit", re.IGNORECASE),
]


async def extract_inwork_credits_from_page(page: Page) -> int:
    """Najde číslo kreditů na InWork stránce podle několika patternů."""
    text = await page.inner_text("body")
    for pat in INWORK_CREDITS_PATTERNS:
        m = pat.search(text)
        if m:
            return int(m.group(1))
    raise RuntimeError(
        "InWork: Nepodařilo se najít 'Stav kreditů: X' na stránce.\n"
        "Ujisti se, že jsi na přehledu, kde je vidět text jako 'Stav kreditů: 2'."
    )


async def fetch_inwork_credits(headless: bool = False) -> PortalCredits:
    """Otevře InWork/Fajnsprava, nechá tě ručně přihlásit, vytáhne kredity a vrátí PortalCredits."""
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(INWORK_PROFILE_DIR),
            headless=headless,
        )
        page = await context.new_page()
        print(f"[InWork] Otevírám: {INWORK_DASHBOARD_URL}")
        await page.goto(INWORK_DASHBOARD_URL, wait_until="networkidle"

        )

        print(
            "\nV otevřeném okně prohlížeče se přihlas do InWork/Fajnsprava (e-mail, heslo, případně SMS/2FA)\n"
            "a přepni se na stránku, kde je vidět 'Stav kreditů: X'.\n"
            "Až budeš na správné stránce, vrať se do konzole.\n"
        )
        input("[InWork] Až budeš na správné stránce se stavem kreditů, stiskni Enter v této konzoli... ")

        await page.wait_for_load_state("networkidle")
        credits_value = await extract_inwork_credits_from_page(page)
        now = datetime.now(timezone.utc)

        await context.close()
        print(f"[InWork] {now.isoformat()} – {credits_value} kreditů")  # log do konzole

        return PortalCredits(
            portal="InWork",
            credits=credits_value,
            timestamp=now,
        )


# -----------------------------------------------------------------------------
# Orchestrátor – jeden entrypoint pro oba portály


async def collect(portals: List[str]) -> None:
    """Spustí sběr dat pro zadané portály a zapíše výsledky do credits.json."""
    results: List[PortalCredits] = []

    # Teamio
    if "teamio" in portals:
        try:
            res = await fetch_teamio_credits(headless=TEAMIO_HEADLESS)
            results.append(res)
        except Exception as e:
            print(f"[Teamio] Chyba: {e}")

    # InWork
    if "inwork" in portals:
        try:
            res = await fetch_inwork_credits(headless=False)
            results.append(res)
        except Exception as e:
            print(f"[InWork] Chyba: {e}")

    if not results:
        print("[AGENT] Nemám žádná nová data k uložení.")
        return

    save_entries(results, CREDITS_FILE)
    print(f"[AGENT] Uloženo {len(results)} záznamů do {CREDITS_FILE_NAME}.")


def parse_args(argv: List[str]) -> List[str]:
    """Rozhodne, pro které portály sbírat data podle argumentů.

    Bez argumentů → oba portály.
    'teamio' → jen Teamio.
    'inwork' → jen InWork.
    """
    if len(argv) <= 1:
        return ["teamio", "inwork"]

    arg = argv[1].lower()
    if arg == "teamio":
        return ["teamio"]
    if arg == "inwork":
        return ["inwork"]

    print("Neznámý argument. Použij bez argumentů, nebo 'teamio' / 'inwork'.")
    sys.exit(1)


def main() -> None:
    portals = parse_args(sys.argv)
    try:
        asyncio.run(collect(portals))
    except KeyboardInterrupt:
        print("\n[AGENT] Přerušeno uživatelem.")


if __name__ == "__main__":
    main()
