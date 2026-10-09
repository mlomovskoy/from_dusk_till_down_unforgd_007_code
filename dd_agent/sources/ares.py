"""Czech public registry (ARES, ares.gov.cz): free official API, no key needed.

Data minimisation: we keep names, roles and dates only. Home addresses and birth dates of
natural persons are dropped before anything is stored or shown.
"""
import unicodedata

import httpx

from ..models import Source, now_iso

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest"
TIMEOUT = 20

LEGAL_FORMS = {
    "101": "sole trader (fyzická osoba podnikající)",
    "111": "general partnership (v.o.s.)",
    "112": "limited liability company (s.r.o.)",
    "113": "limited partnership (k.s.)",
    "121": "joint-stock company (a.s.)",
    "141": "public benefit company (o.p.s.)",
    "205": "cooperative (družstvo)",
    "706": "association (spolek)",
}

REGISTRATION_FLAGS = {
    "stavZdrojeVr": "Commercial register (VR)",
    "stavZdrojeRzp": "Trade licence register (RŽP)",
    "stavZdrojeDph": "VAT register (DPH)",
    "stavZdrojeIr": "Insolvency register (IR)",
    "stavZdrojeCeu": "Central register of bankrupts (CEU)",
}


def normalize_name(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().replace(",", " ").replace(".", " ").split())


def get_basic(ico: str) -> dict | None:
    r = httpx.get(f"{BASE}/ekonomicke-subjekty/{ico}", timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def search_by_name(name: str, limit: int = 10) -> list[dict]:
    r = httpx.post(f"{BASE}/ekonomicke-subjekty/vyhledat",
                   json={"obchodniJmeno": name, "pocet": limit}, timeout=TIMEOUT)
    if r.status_code in (400, 404):
        return []
    r.raise_for_status()
    return r.json().get("ekonomickeSubjekty", [])


def get_public_register(ico: str) -> dict | None:
    r = httpx.get(f"{BASE}/ekonomicke-subjekty-vr/{ico}", timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    records = r.json().get("zaznamy", [])
    primary = [z for z in records if z.get("primarniZaznam")]
    return (primary or records or [None])[0]


def _person_name(entry: dict) -> str | None:
    if fo := entry.get("fyzickaOsoba"):
        parts = [fo.get("titulPredJmenem"), fo.get("jmeno"), fo.get("prijmeni"), fo.get("titulZaJmenem")]
        name = " ".join(p for p in parts if p) or fo.get("textOsoba")
        return name.title() if name and name.isupper() else name
    if po := entry.get("pravnickaOsoba"):
        name = po.get("obchodniJmeno") or po.get("textOsoba")
        return f"{name} (IČO {po['ico']})" if po.get("ico") else name
    return None


def people(vr: dict) -> list[dict]:
    """Statutory body members and partners, with role and dates only."""
    out = []
    for organ in vr.get("statutarniOrgany", []) or []:
        for m in organ.get("clenoveOrganu", []) or []:
            name = _person_name(m)
            if not name:
                continue
            func = ((m.get("clenstvi") or {}).get("funkce") or {})
            out.append({
                "name": name,
                "role": _role(func.get("nazev") or m.get("nazevAngazma") or organ.get("nazevOrganu", "")),
                "since": func.get("vznikFunkce") or m.get("datumZapisu"),
                "until": m.get("datumVymazu"),
                "current": not m.get("datumVymazu"),
            })
    for group in vr.get("spolecnici", []) or []:
        for s in group.get("spolecnik", []) or []:
            osoba = s.get("osoba") or {}
            name = _person_name(osoba)
            if not name:
                continue
            share = ""
            for podil in s.get("podil", []) or []:
                if not podil.get("datumVymazu") and (v := podil.get("velikostPodilu")):
                    share = f" ({v.get('hodnota')})"
            out.append({
                "name": name,
                "role": "partner / shareholder" + share,
                "since": osoba.get("datumZapisu") or s.get("datumZapisu"),
                "until": s.get("datumVymazu"),
                "current": not s.get("datumVymazu"),
            })
    return out


def basic_source(basic: dict, source_id: str) -> Source:
    ico = basic["ico"]
    regs = basic.get("seznamRegistraci", {}) or {}
    lines = [
        f"Business name: {basic.get('obchodniJmeno')}",
        f"IČO: {ico}",
        f"Registered office: {(basic.get('sidlo') or {}).get('textovaAdresa', 'n/a')}",
        f"Legal form: {LEGAL_FORMS.get(str(basic.get('pravniForma')), basic.get('pravniForma'))}",
        f"Date established: {basic.get('datumVzniku', 'n/a')}",
    ]
    if basic.get("datumZaniku"):
        lines.append(f"Date dissolved: {basic['datumZaniku']}")
    if basic.get("dic"):
        lines.append(f"VAT ID: {basic['dic']}")
    for key, label in REGISTRATION_FLAGS.items():
        state = regs.get(key)
        if state:
            lines.append(f"{label}: {'record exists' if state == 'AKTIVNI' else 'no record' if state == 'NEEXISTUJICI' else state}")
    if basic.get("czNace2008"):
        lines.append(f"Activity codes (CZ-NACE): {', '.join(basic['czNace2008'])}")
    lines.append(f"Registry record last updated: {basic.get('datumAktualizace', 'n/a')}")
    return Source(
        id=source_id,
        url=f"https://ares.gov.cz/ekonomicke-subjekty?ico={ico}",
        title=f"ARES registry record — {basic.get('obchodniJmeno')} (IČO {ico})",
        text="\n".join(lines),
        origin="registry",
        publisher="ares.gov.cz (official)",
        fetched_at=now_iso(),
    )


ROLES = {
    "předseda představenstva": "chair of the board",
    "místopředseda představenstva": "vice-chair of the board",
    "člen představenstva": "board member",
    "předseda dozorčí rady": "chair of the supervisory board",
    "člen dozorčí rady": "supervisory board member",
    "jednatel": "managing director (jednatel)",
    "prokurista": "authorised signatory (prokura)",
    "Člen statutárního orgánu": "statutory body member",
}
STATUS = {"AKTIVNI": "active", "ZANIKLY": "dissolved", "V_LIKVIDACI": "in liquidation"}


def _role(text: str) -> str:
    return ROLES.get(text, ROLES.get(text.lower(), text))


def register_source(vr: dict, ico: str, source_id: str) -> Source:
    names = vr.get("obchodniJmeno", []) or []
    current_name = next((n["hodnota"] for n in names if not n.get("datumVymazu")), ico)
    lines = [f"Commercial register file: {_file_mark(vr)}",
             f"Subject status: {STATUS.get(vr.get('stavSubjektu'), vr.get('stavSubjektu', 'n/a'))}"]
    former = [n for n in names if n.get("datumVymazu")]
    for n in former:
        lines.append(f"Former name: {n['hodnota']} ({n.get('datumZapisu')} to {n.get('datumVymazu')})")
    for cap in vr.get("zakladniKapital", []) or []:
        if not cap.get("datumVymazu") and (v := cap.get("vklad")):
            lines.append(f"Registered capital: {v.get('hodnota')} {v.get('typObnos', '')}")
    for p in sorted(people(vr), key=lambda p: (not p["current"], p["until"] or "")):
        span = f"since {p['since']}" if p["current"] else f"{p['since']} to {p['until']}"
        lines.append(f"{'Current' if p['current'] else 'Former'} {p['role']}: {p['name']} ({span})")
    return Source(
        id=source_id,
        url=f"https://or.justice.cz/ias/ui/rejstrik-$firma?ico={ico}",
        title=f"Commercial register (via ARES) — {current_name}",
        text="\n".join(lines),
        origin="registry",
        publisher="ares.gov.cz / justice.cz (official)",
        fetched_at=now_iso(),
    )


def _file_mark(vr: dict) -> str:
    for z in vr.get("spisovaZnacka", []) or []:
        if not z.get("datumVymazu"):
            return f"{z.get('oddil')} {z.get('vlozka')}, {z.get('soud')}"
    return "n/a"
