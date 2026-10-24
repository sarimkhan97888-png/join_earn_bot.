"""Bhasha: hn = Hinglish (asli code wali), hi = Hindi (Devanagari), en = English.

Code me sab messages Hinglish me likhe hain. Dusri bhasha ke user ko bhejne se pehle `tr()` unhe
i18n_data.SERVER ke table se badal deta hai (exact match, phir {} wale templates, phir paragraph/line-wise).
Table me na mile to message jaisa hai waisa (Hinglish) chala jata hai, kuch tootta nahi."""
import contextvars
import re
import time

import i18n_data

LANGS = ("hn", "hi", "en")
cur = contextvars.ContextVar("lang", default="hn")  # API request ki bhasha (auth middleware set karta hai)

_EXACT = {}
_PATS = []
_CONSTS = []


def _build():
    _EXACT.clear(); _PATS.clear(); _CONSTS.clear()
    for src, (hi, en) in i18n_data.SERVER.items():
        if "{}" in src:
            parts = src.split("{}")
            grp = "(.+?)" if "\n" in src else "([^\n]+?)"  # ek-line template ek hi line se match ho
            rx = re.compile("^" + grp.join(re.escape(p) for p in parts) + "$", re.S)
            _PATS.append((sum(len(p) for p in parts), rx, {"hi": hi, "en": en}))
        else:
            _EXACT[src] = {"hi": hi, "en": en}
    _PATS.sort(key=lambda x: -x[0])  # sabse specific (zyada fixed text) pehle
    for src, (hi, en) in i18n_data.CONSTS.items():
        _CONSTS.append((src, {"hi": hi, "en": en}))


_build()


def _fill(t, groups):
    if "{" not in t:
        return t
    try:
        return t.format(*groups)
    except (IndexError, KeyError, ValueError):
        return t


def _one(text, lang):
    e = _EXACT.get(text)
    if e:
        return e[lang]
    for _, rx, tr in _PATS:
        m = rx.match(text)
        if m:
            return _fill(tr[lang], m.groups())
    return None


def _split(text, sep, lang):
    parts = text.split(sep)
    if len(parts) < 2:
        return None
    out, hit = [], False
    for p in parts:
        r = _one(p, lang) if p.strip() else None
        if r is None:
            r = _split(p, "\n", lang) if sep == "\n\n" else None
        if r is None:
            out.append(p)
        else:
            out.append(r); hit = True
    return sep.join(out) if hit else None


def tr(text, lang=None):
    """Hinglish text -> user ki bhasha. Na mile to wahi text."""
    lang = lang or cur.get()
    if lang not in ("hi", "en") or not isinstance(text, str) or not text:
        return text
    for src, t in _CONSTS:
        if src in text:
            text = text.replace(src, t[lang])
    r = _one(text, lang)
    if r is not None:
        return r
    r = _split(text, "\n\n", lang)
    if r is None:
        r = _split(text, "\n", lang)
    return r if r is not None else text


# ---- user ki bhasha (cache) ----
_cache = {}  # uid -> (lang, time)


def cached(uid):
    v = _cache.get(uid)
    return v[0] if v and time.monotonic() - v[1] < 600 else None


def remember(uid, lang):
    if len(_cache) > 50000:
        _cache.clear()
    _cache[uid] = (lang or "en", time.monotonic())


async def lang_of(uid):
    import db
    l = cached(uid)
    if l is None:
        try:
            l = await db.get_lang(uid)
        except Exception:
            l = None
        remember(uid, l)
        l = l or "en"
    return l


async def tr_for(uid, text):
    return tr(text, await lang_of(uid))
