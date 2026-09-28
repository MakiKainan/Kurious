"""Phase 4 reranker: noise filter, then score = relevance (MiniLM) + coverage + interestingness - obviousness."""
import math
import re
import threading
import unicodedata

import numpy as np

W_REL, W_COV, W_INT, W_OBVIOUS = 0.40, 0.35, 0.25, 0.15
FAMOUS_VIEWS = 30_000   # over the ~60-day pageview window, about 500/day
STUB_BYTES = 2_500
DEPTH_BYTES = 50_000    # article size that counts as fully "deep"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TORCH_THREADS = 4       # leave CPU headroom for Vosk
MAX_TOKENS = 128        # intro's opening is enough; 256 was ~2x slower per doc

_LISTY = ("Index of ", "Outline of ", "Glossary of ", "Timeline of ")
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_PAGE = re.compile(
    rf"^(\d{{1,4}}( BC| AD| BCE| CE)?"      # 1997, 44 BC
    rf"|\d{{1,4}}0s( BC)?"                  # 1990s
    rf"|\d{{1,2}}(st|nd|rd|th) century( BC)?"  # 19th century
    rf"|({_MONTHS}) \d{{1,2}}"               # March 1
    rf"|\d{{3,4}}s? in .+)$"                 # 1997 in music
)

_model = None
_model_lock = threading.Lock()
_emb_cache = {}


def norm(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()


def _tokens(s):
    return re.findall(r"[a-z0-9]+", norm(s))


def _stem(word):
    for suffix in ("es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _mentions(word, tokens):
    w = _stem(norm(word))
    if len(w) >= 4:
        return any(t.startswith(w) for t in tokens)
    return w in tokens


def noise_reason(c):
    """Why a candidate is noise, or None if it's worth showing."""
    if c.get("is_disambig"):
        return "disambiguation"
    if c.get("is_list") or c["title"].startswith(_LISTY):
        return "list"
    if _DATE_PAGE.match(c["title"]):
        return "date page"
    if 0 < c.get("length", 0) < STUB_BYTES or any(cat.endswith(" stubs") for cat in c.get("categories", [])):
        return "stub"
    if c.get("is_person") and c.get("views", 0) < FAMOUS_VIEWS:
        return "obscure person"
    return None


def coverage(words, c):
    tokens = set(_tokens(" ".join((c["title"], c.get("description") or "", c.get("extract") or ""))))
    hits = sum(1 for w in words if w in c.get("matched_by", ()) or _mentions(w, tokens))
    return hits / len(words)


def interest(c):
    views = min(1.0, math.log10(c.get("views", 0) + 1) / 6)
    has_image = 1.0 if c.get("thumbnail") else 0.0
    depth = min(1.0, c.get("length", 0) / DEPTH_BYTES)
    return 0.5 * views + 0.25 * has_image + 0.25 * depth


def obvious(words, c):
    title = norm(re.sub(r"\s*\(.*\)$", "", c["title"])).strip()
    options = {norm(" ".join(words))} | {norm(w) for w in words} | {_stem(norm(w)) for w in words}
    return 1.0 if title in options else 0.0


def load_model():
    """Blocking and idempotent; call from a background thread at startup (~11s of imports)."""
    global _model
    with _model_lock:
        if _model is None:
            import torch
            torch.set_num_threads(TORCH_THREADS)
            from sentence_transformers import SentenceTransformer
            try:  # cached copy loads in 0.2s; the online update check alone costs ~8s
                _model = SentenceTransformer(MODEL_NAME, device="cpu", local_files_only=True)
            except Exception:
                # first run: download. Public model, so never send a saved HF login (an expired one fails)
                _model = SentenceTransformer(MODEL_NAME, device="cpu", token=False)
            _model.max_seq_length = MAX_TOKENS
    return _model


def _default_embed(texts):
    return load_model().encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)


def _doc(c):
    return f"{c['title']}. {c.get('description') or ''}. {c.get('extract') or ''}"


def _embed_docs(cands, embed):
    if embed is not None:
        return embed([_doc(c) for c in cands])
    missing = [c for c in cands if c["pageid"] not in _emb_cache]
    if missing:
        for c, v in zip(missing, _default_embed([_doc(c) for c in missing])):
            _emb_cache[c["pageid"]] = v
    return [_emb_cache[c["pageid"]] for c in cands]


def rerank(words, candidates, embed=None):
    """Returns (ranked candidates with score/parts, number dropped as noise)."""
    if not words or not candidates:
        return [], 0
    kept = [c for c in candidates if noise_reason(c) is None]
    dropped = len(candidates) - len(kept)
    if not kept:  # never leave the screen blank
        kept, dropped = list(candidates), 0

    q = (embed or _default_embed)([" ".join(words)])[0]
    docs = _embed_docs(kept, embed)
    ranked = []
    for c, v in zip(kept, docs):
        parts = {
            "rel": max(0.0, min(1.0, float(np.dot(q, v)))),
            "cov": coverage(words, c),
            "int": interest(c),
            "obvious": obvious(words, c),
        }
        score = W_REL * parts["rel"] + W_COV * parts["cov"] + W_INT * parts["int"] - W_OBVIOUS * parts["obvious"]
        ranked.append(dict(c, score=score, parts=parts))
    ranked.sort(key=lambda c: -c["score"])
    return ranked, dropped
