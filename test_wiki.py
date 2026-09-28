import sys
import time

from wiki_common import add_flags, merge


def cand(pageid, title, rank, q, cats=()):
    return {"pageid": pageid, "title": title, "rank": rank, "matched_by": [q], "categories": list(cats)}


def test_flags():
    c = add_flags(cand(1, "Bjork", 0, "x", ["Category:Living people"]), False)
    assert c["is_person"] and not c["is_list"] and not c["is_disambig"]
    c = add_flags(cand(2, "Napoleon", 0, "x", ["Category:1769 births", "Category:1821 deaths"]), False)
    assert c["is_person"]
    c = add_flags(cand(3, "List of volcanoes", 0, "x", ["Category:Lists of volcanoes"]), False)
    assert c["is_list"] and not c["is_person"]
    assert add_flags(cand(4, "Mercury", 0, "x"), True)["is_disambig"]


def test_merge():
    a = [cand(1, "Iceland", 3, "volcano iceland"), cand(2, "Hekla", 1, "volcano iceland")]
    b = [cand(1, "Iceland", 0, "iceland"), cand(3, "Reykjavik", 2, "iceland")]
    out = merge([a, b])
    assert [c["title"] for c in out] == ["Iceland", "Hekla", "Reykjavik"]
    assert out[0]["matched_by"] == ["volcano iceland", "iceland"] and out[0]["rank"] == 0
    assert a[0]["matched_by"] == ["volcano iceland"]  # inputs not mutated


def test_network():
    import wiki
    import wiki_lazy
    words = ["volcano", "iceland", "music"]
    for backend in (wiki, wiki_lazy):
        t = time.perf_counter()
        res, stats = backend.candidates(words)
        cold = time.perf_counter() - t
        assert res and res[0]["extract"] and "views" in res[0], backend.__name__
        t = time.perf_counter()
        res2, stats2 = backend.candidates(words)
        warm = time.perf_counter() - t
        assert stats2["requests"] == 0, (backend.__name__, stats2)
        print(f"{backend.__name__}: cold {cold*1000:.0f}ms ({stats['requests']} req), "
              f"warm {warm*1000:.0f}ms, {len(res)} candidates, top: {res[0]['title']}")
        assert warm < 0.05, f"{backend.__name__} warm call too slow: {warm:.3f}s"


test_flags()
test_merge()
print("offline ok")
if "--net" in sys.argv:
    test_network()
    print("network ok")
