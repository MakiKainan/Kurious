import re

USER_AGENT = "Kurious/0.1 (COMP6822001 student project; https://github.com/MakiKainan/Kurious)"
_PERSON = re.compile(r"^Category:(Living people|\d+( BC)? (births|deaths))$")


def add_flags(c, disambig):
    c["is_disambig"] = disambig
    c["is_list"] = c["title"].startswith("List of")
    c["is_person"] = any(_PERSON.match(cat) for cat in c["categories"])
    return c


def merge(lists):
    """Dedupe candidates by pageid; record every query that returned each one."""
    out = {}
    for cands in lists:
        for c in cands:
            m = out.get(c["pageid"])
            if m is None:
                out[c["pageid"]] = dict(c, matched_by=list(c["matched_by"]))
            else:
                m["matched_by"] += [q for q in c["matched_by"] if q not in m["matched_by"]]
                m["rank"] = min(m["rank"], c["rank"])
    return sorted(out.values(), key=lambda c: (-len(c["matched_by"]), c["rank"]))
