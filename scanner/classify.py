"""Turn a raw shop title into: is it sealed Pokémon? which set, product type, language."""
import html
import json
import re
import unicodedata
from pathlib import Path


def normalize(text):
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or "")).replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


POKEMON = re.compile(r"\bpokemon\b|\bpkmn\b|\bpkm\b")

# Things that are not sealed product, or not product at all.
EXCLUDE = re.compile(
    r"\bsleeves?\b|\bbinder\b(?!.*collection)|\bportfolio\b|deck ?box|\bplaymat\b|top ?loader|\bacrylic\b|"
    r"display case|\bprotector\b|\bmagnetic\b|\bcard case\b|\bstorage\b|\balbum\b|\bdice\b|"
    r"\bpsa\b|\bcgc\b|\bbgs\b|\bgraded\b|\bplush\b|\bknuffel\b|\bfigure\b|\bpuzzle\b|"
    r"\bt-shirt\b|\bhoodie\b|\bmyst?ery\b|\bmistery\b|\bvoucher\b|gift ?card|\bempty\b|\bleeg\b|"
    r"\bcode card\b|dobbelstenen|\bguide\b|\bguia\b|energy (game|battle)|pack ?battle|\bbreak\b|\bstickers?\b(?!.*collection)|\bonline code\b|\bjumbo card\b|\bsingles?\b|reverse holo|\bart card\b"
)
CARD_NUMBER = re.compile(r"\b\d{1,3}/\d{2,3}\b")

# Ordered: first match wins.
TYPES = [
    ("Sealed Case", r"\bcase\b.*\b(boosters?|displays?|elite trainer|etbs?|blisters?|bundles?|tins?)\b|"
                    r"\b(booster box|display|elite trainer box|etb)\b.*\bcase\b|\bsealed case\b|"
                    r"\bdisplay\b.*\b(mini.?tins?|tins?|blisters?|bundles?|etbs?)\b|\b(tins?|blisters?)\b.*\bdisplay\b|"
                    r"\b([2-9]|[1-9]\d) ?x? ?(bundles?|tins?|blisters?|etbs?|elite trainer boxes|displays?|booster boxes)\b|"
                    r"\b(bundle|blister) box\b|\bx ?([2-9]|[1-9]\d) (bundles?|tins?|blisters?|displays?)\b"),
    ("Half Booster Box", r"half booster ?box|halbes display|\b18 ?er\b|\b18 ?(x )?(booster|pack)s?\b|\b(18|half)[- ]?display\b"),
    ("Build & Battle Stadium", r"build (&|and|n) battle stadium"),
    ("Blister", r"checklane"),
    ("Pokemon Center ETB", r"pokemon center.*(elite trainer|\betb\b|top.?trainer)"),
    ("Elite Trainer Box", r"elite trainer|\betb\b|top.?trainer.?box|coffret dresseur d.elite"),
    ("Booster Box", r"booster ?box|booster.?display|\bdisplay\b|\b(36|30|24|20) ?(x )?(booster|pack)s?\b"),
    ("Booster Bundle", r"booster bundle|\bbundle\b|6 ?booster"),
    ("Ultra Premium Collection", r"ultra.?premium|\bupc\b"),
    ("Super Premium Collection", r"super.?premium"),
    ("Premium Collection", r"premium collection|premium.?kollektion"),
    ("Build & Battle", r"build (&|and|n) battle|prerelease|pre-release kit"),
    ("Tin", r"\btins?\b|tin.?box|\bdose\b|mini.?tin"),
    ("Blister", r"blister|checklane|\b3.?pack\b|three.?pack|2.?pack blister|premium checklane"),
    ("Collection Box", r"collection|kollektion|\bbox\b|coffret|poster (collection|box)|binder collection|surprise"),
    ("Booster Pack", r"booster ?pack|boosterpack|sleeved booster|\bbooster\b|\bpack\b"),
]
TYPES = [(name, re.compile(rx)) for name, rx in TYPES]

LANG_WORDS = [
    ("JP", r"japanese|japanse|japans|japanisch|japonais|giapponese|japones"),
    ("KR", r"korean|koreaanse|koreaans|koreanisch|coreano"),
    ("CN", r"chinese|chinees|simplified chinese|traditional chinese|chinesisch|s-chinese|t-chinese|chino|cinese"),
    ("DE", r"german|deutsch|duitse|duits|allemand"),
    ("FR", r"french|franzosisch|franstalig|franse|frans|francais|francaise"),
    ("IT", r"italian|italienisch|italiaanse|italiaans|italiano"),
    ("ES", r"spanish|spanisch|spaanse|spaans|espanol|castellano"),
    ("EN", r"english|englisch|engelstalig|engelse|engels|anglais|inglese|ingles|englische|englischer|englisches"),
]
LANG_WORDS = [(code, re.compile(r"\b(" + rx + r")\b")) for code, rx in LANG_WORDS]
# Two-letter codes only count in UPPERCASE ("de" is also a Dutch/French word).
LANG_CODE = re.compile(r"(?<![A-Za-z])(EN|ENG|DE|GER|FR|FRA|IT|ITA|ES|ESP|SPA|JP|JPN|JAP|KR|KOR|CN)(?![A-Za-z])")
CODE_MAP = {"ENG": "EN", "GER": "DE", "JPN": "JP", "JAP": "JP", "KOR": "KR", "ITA": "IT", "FRA": "FR", "ESP": "ES", "SPA": "ES"}

# Other spellings of English (or Dutch, which has no own print run) set names.
ENGLISH_VARIANTS = {"mega evolutie", "mega-evolution", "prismatic evolution", "paradoxrift", "scarlet and violet base",
                    "champions path", "sword and shield base", "sword & shield - base", "sun & moon - base",
                    "sun and moon base", "xy evolutions", "xy - evolutions"}

# Product words that only appear in non-English listings.
FOREIGN_WORDS = re.compile(r"\bcoffret\b|\bdresseur\b|sammel|kollektion|\bdose\b|\bsobre\b|\bcaja\b|coleccion|collezione|"
                           r"\bscatola\b|\bbusta\b|\bdisplay de\b|top.?trainer|\bbooster.?display\b.*\b(de|fr)\b")

PREORDER = re.compile(r"pre-?order|preorder|voorverkoop|vorbestellung|vorverkauf|precommande|releasedatum|release date")


def _language(raw, norm):
    m = LANG_CODE.search(re.sub(r"<[^>]+>", " ", html.unescape(raw)))
    if m:
        return CODE_MAP.get(m.group(1), m.group(1))
    return next((code for code, rx in LANG_WORDS if rx.search(norm)), None)


def _all_languages(raw):
    norm = normalize(raw).replace("-", " ")
    found = {CODE_MAP.get(c, c) for c in LANG_CODE.findall(raw)}
    found |= {code for code, rx in LANG_WORDS if rx.search(norm)}
    return found


class Classifier:
    def __init__(self, sets_path):
        sets = json.loads(Path(sets_path).read_text(encoding="utf-8"))
        aliases = []
        for s in sets:
            for a in s["aliases"]:
                aliases.append((normalize(a), s["set"]))
        aliases.sort(key=lambda x: -len(x[0]))  # longest alias first
        self.aliases = [(re.compile(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])"), name) for a, name in aliases]
        # Aliases that tell nothing about the language: the English set name itself, or a set code (sv8.5, me05).
        self.neutral = {(normalize(s["set"]), s["set"]) for s in sets}
        self.neutral |= {(a, name) for a, name in aliases if re.search(r"\d", a) or a in ENGLISH_VARIANTS
                         or name.startswith("JP ")}

    def classify(self, title, context="", default_language=None):
        """Return dict or None when it's not a sealed Pokémon product."""
        t = normalize(title)
        if not POKEMON.search(t) and not POKEMON.search(normalize(context)):
            return None
        if EXCLUDE.search(t) or CARD_NUMBER.search(t):
            return None

        ptype = next((name for name, rx in TYPES if rx.search(t)), None)
        if ptype is None:
            return None

        # Titles usually read "<series> - <set> - <product>", so when several set names
        # match (e.g. "Mega Evolution - Perfect Order"), the right-most one is the actual set.
        hits = [(m.start(), m.end(), name) for rx, name in self.aliases for m in [rx.search(t)] if m]
        # Drop names that sit inside a longer match ("151" inside "pokemon card 151").
        hits = [h for h in hits if not any(o[0] <= h[0] and h[1] <= o[1] and o[1] - o[0] > h[1] - h[0] for o in hits)]
        pset = max(hits)[2] if hits else None
        alias_hit = t[max(hits)[0]:max(hits)[1]] if hits else None

        lang = _language(title, t)
        if lang is None and context:
            # Many shops keep the language in a category or tag ("Engels", "idioma-ingles").
            # Only trust that when it names exactly one language.
            found = _all_languages(context)
            lang = found.pop() if len(found) == 1 else None
            if lang is None and found - {"EN"} and default_language == "EN":
                return {"set": pset or "Unknown set", "type": ptype, "language": "?",
                        "preorder": bool(PREORDER.search(t)), "group": None}
        if pset and pset.startswith("JP "):
            lang = lang or "JP"
        if lang is None and default_language:
            # A shop's default language only applies when nothing in the title points to another
            # language: a German/French/Spanish set name or product word means it is not the default.
            foreign = (pset and (alias_hit, pset) not in self.neutral) or FOREIGN_WORDS.search(t)
            lang = None if foreign and default_language == "EN" else default_language
        lang = lang or "?"

        return {
            "set": pset or "Unknown set",
            "type": ptype,
            "language": lang,
            "preorder": bool(PREORDER.search(t)),
            "group": f"{pset}|{ptype}|{lang}" if pset and lang != "?" else None,
        }
