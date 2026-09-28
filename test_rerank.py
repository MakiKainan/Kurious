import sys
import time

import numpy as np

from rerank import coverage, noise_reason, obvious, rerank


def cand(pageid, title, **kw):
    c = {"pageid": pageid, "title": title, "description": "", "extract": "", "thumbnail": None,
         "views": 50_000, "length": 30_000, "categories": [], "matched_by": [], "rank": 0,
         "is_person": False, "is_disambig": False, "is_list": False}
    c.update(kw)
    return c


def fake_embed(texts):
    return [np.ones(4) / 2 for _ in texts]  # every doc equally relevant, so other signals decide


def test_noise():
    assert noise_reason(cand(1, "Mercury", is_disambig=True)) == "disambiguation"
    assert noise_reason(cand(2, "List of volcanoes", is_list=True)) == "list"
    assert noise_reason(cand(3, "Outline of Iceland")) == "list"
    for t in ("1997", "44 BC", "1990s", "19th century", "March 1", "1997 in music"):
        assert noise_reason(cand(4, t)) == "date page", t
    assert noise_reason(cand(5, "Tiny place", length=900)) == "stub"
    assert noise_reason(cand(6, "Hill", categories=["Category:Iceland geography stubs"])) == "stub"
    assert noise_reason(cand(7, "John Smith (footballer)", is_person=True, views=800)) == "obscure person"
    assert noise_reason(cand(8, "Björk", is_person=True, views=400_000)) is None
    assert noise_reason(cand(9, "1984 (novel)")) is None  # a year inside a real title is fine
    assert noise_reason(cand(10, "No length info", length=0)) is None


def test_coverage():
    c = cand(1, "Eyjafjallajökull", extract="An Icelandic volcano whose eruption disrupted music tours.")
    assert coverage(["volcanoes", "iceland", "music"], c) == 1.0  # plural + prefix match
    assert coverage(["eyjafjallajokull"], c) == 1.0               # accent-stripped
    assert coverage(["opera"], cand(2, "Hekla", matched_by=["opera"])) == 1.0  # per-word search hit
    assert coverage(["cat"], cand(3, "Catalonia")) == 0.0         # short words need an exact token


def test_obvious():
    assert obvious(["volcano", "iceland"], cand(1, "Volcano")) == 1.0
    assert obvious(["volcanoes"], cand(2, "Volcano (1997 film)")) == 1.0
    assert obvious(["volcano", "iceland"], cand(3, "Volcanism of Iceland")) == 0.0


def test_ranking():
    words = ["volcano", "iceland", "music"]
    popular = cand(1, "Iceland", extract="Iceland is a Nordic island country.", views=900_000, thumbnail="x")
    connector = cand(2, "Björk", extract="Icelandic singer whose music references the volcano landscape.",
                     is_person=True, views=200_000, thumbnail="x")
    noise = cand(3, "Volcano (disambiguation)", is_disambig=True)
    ranked, dropped = rerank(words, [popular, connector, noise], embed=fake_embed)
    assert dropped == 1 and ranked[0]["title"] == "Björk", [c["title"] for c in ranked]
    assert ranked[1]["parts"]["obvious"] == 1.0

    ranked, dropped = rerank(words, [noise], embed=fake_embed)  # all noise -> fallback, not blank
    assert len(ranked) == 1 and dropped == 0
    assert rerank([], [popular], embed=fake_embed) == ([], 0)


def test_network():
    import rerank as rr
    import wiki
    queries = [["volcano", "iceland", "music"], ["shark", "ocean", "horror"], ["napoleon", "war", "russia"]]
    t = time.perf_counter()
    rr.load_model()
    print(f"model load {time.perf_counter() - t:.1f}s")
    for words in queries:
        cands, _ = wiki.candidates(words)
        timings = []
        for _ in range(2):  # cold, then warm (embedding cache)
            t = time.perf_counter()
            ranked, dropped = rerank(words, cands)
            timings.append((time.perf_counter() - t) * 1000)
        print(f"\n{' '.join(words)}: {len(cands)} candidates, {dropped} dropped, "
              f"rerank cold {timings[0]:.0f}ms warm {timings[1]:.0f}ms")
        for c in ranked[:3]:
            p = c["parts"]
            print(f"  {c['score']:.3f}  {c['title']:<40} rel {p['rel']:.2f} cov {p['cov']:.2f} "
                  f"int {p['int']:.2f} obv {p['obvious']:.0f}")
        top = ranked[0]
        assert noise_reason(top) is None, top["title"]
        assert top["parts"]["cov"] >= 2 / 3, (top["title"], top["parts"])


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    test_noise()
    test_coverage()
    test_obvious()
    test_ranking()
    print("offline ok")
    if "--net" in sys.argv:
        test_network()
        print("\nnetwork ok")
