"""Phase 1-4: mic -> Vosk -> word finalizer -> query terms -> Wikipedia candidates -> reranked article."""
import argparse
import csv
import json
import os
import queue
import sys
import threading
import time
import urllib.parse

import sounddevice as sd
from vosk import KaldiRecognizer, Model

import rerank

MODEL_PATH = "vosk-model-en-us-0.22-lgraph"
SAMPLE_RATE = 16000

STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "is", "are", "was", "were", "be", "been", "it", "this", "that",
    "um", "uh", "with", "as", "by", "from", "i", "you", "we", "so",
}

LATENCY_LOG = "latency.csv"

audio_q = queue.Queue()
paused = threading.Event()

try:
    import msvcrt  # Windows console key input; other OSes just get Ctrl+C
except ImportError:
    msvcrt = None


def key_listener():
    while True:
        if msvcrt.getwch() in ("\r", " "):
            paused.clear() if paused.is_set() else paused.set()


LATENCY_HEADER = ["timestamp", "backend", "n_words", "query", "wait_ms", "search_ms", "rerank_ms", "total_ms",
                  "requests", "cached", "n_results", "n_filtered", "top_title", "superseded"]


def log_latency(row):
    if os.path.exists(LATENCY_LOG):
        with open(LATENCY_LOG, encoding="utf-8") as f:
            old_header = f.readline().strip()
        if old_header != ",".join(LATENCY_HEADER):  # older format: set it aside, don't mix rows
            os.replace(LATENCY_LOG, f"latency_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    new = not os.path.exists(LATENCY_LOG)
    with open(LATENCY_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(LATENCY_HEADER)
        w.writerow(row)


def wiki_url(title):
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


class WordFinalizer:
    """Vosk partials only grow/append in lgraph mode, so every word but the
    last one in a partial is stable. ponytail: doesn't handle Vosk revising
    an already-emitted word (rare) — add re-diffing if that shows up."""

    def __init__(self):
        self.emitted = []

    def partial(self, text):
        words = text.split()
        stable_count = max(0, len(words) - 1)
        new = []
        while len(self.emitted) < stable_count:
            self.emitted.append(words[len(self.emitted)])
            new.append(self.emitted[-1])
        return new

    def final(self, text):
        words = text.split()
        new = []
        while len(self.emitted) < len(words):
            self.emitted.append(words[len(self.emitted)])
            new.append(self.emitted[-1])
        self.emitted = []
        return new


def callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    audio_q.put(bytes(indata))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["full", "lazy"], default="full")
    backend = ap.parse_args().backend
    if backend == "lazy":
        import wiki_lazy as wiki
    else:
        import wiki
    sys.stdout.reconfigure(errors="replace")

    def load_reranker():
        rerank.load_model()
        print("\n[reranker ready]")

    threading.Thread(target=load_reranker, daemon=True).start()  # ~11s, overlaps the Vosk load

    model = Model(MODEL_PATH)
    rec = KaldiRecognizer(model, SAMPLE_RATE)

    finalizer = WordFinalizer()
    query_words = []
    jobs = queue.Queue()
    latest = [0]

    def search_worker():
        while True:
            gen, words, t0 = jobs.get()
            if not jobs.empty():
                continue  # a newer query is already waiting
            t_start = time.perf_counter()  # t0 = word finalized; the gap is time queued behind older work
            try:
                results, stats = wiki.candidates(words)
                t1 = time.perf_counter()
                ranked, dropped = rerank.rerank(words, results)
            except Exception as e:
                print(f"\nsearch failed: {e}", file=sys.stderr)
                continue
            t2 = time.perf_counter()
            wait_ms, search_ms = (t_start - t0) * 1000, (t1 - t_start) * 1000
            rerank_ms, total_ms = (t2 - t1) * 1000, (t2 - t0) * 1000
            superseded = gen != latest[0]
            top = ranked[0]["title"] if ranked else ""
            log_latency([time.strftime("%Y-%m-%d %H:%M:%S"), backend, len(words), " ".join(words),
                         f"{wait_ms:.0f}", f"{search_ms:.0f}", f"{rerank_ms:.0f}", f"{total_ms:.0f}", stats["requests"],
                         stats["cached"], len(results), dropped, top, superseded])
            if superseded:
                continue
            if not ranked:
                print("\narticle: (no results)")
                continue
            p = ranked[0]["parts"]
            print(f"\narticle: {top}  {wiki_url(top)}\n"
                  f"         (rel {p['rel']:.2f} cov {p['cov']:.2f} int {p['int']:.2f}"
                  f"{' obvious' if p['obvious'] else ''} | {total_ms:.0f}ms: wait {wait_ms:.0f}"
                  f" + search {search_ms:.0f} + rerank {rerank_ms:.0f}, {dropped} noise dropped)")
            if len(ranked) > 1:
                print(f"  also:  {' | '.join(c['title'] for c in ranked[1:3])}")

    threading.Thread(target=search_worker, daemon=True).start()

    def emit_stable(words):
        added = [w for w in words if w not in STOPWORDS]
        query_words.extend(added)
        if words:
            print(f"\nquery:   {' '.join(query_words)}")
        if added:
            latest[0] += 1
            jobs.put((latest[0], list(query_words), time.perf_counter()))

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE, blocksize=8000, dtype="int16",
        channels=1, callback=callback,
    ):
        if msvcrt:
            threading.Thread(target=key_listener, daemon=True).start()
        print("Listening... (Enter/Space = stop/resume, Ctrl+C = quit)")
        last_partial = ""
        was_paused = False
        while True:
            data = audio_q.get()
            if paused.is_set():
                if not was_paused:  # flush the last words so they still get searched
                    was_paused = True
                    text = json.loads(rec.FinalResult()).get("text", "")
                    if text:
                        print(f"\rFINAL:   {text}" + " " * 20)
                    emit_stable(finalizer.final(text))
                    print("\n[stopped - press Enter/Space to start a new query]")
                continue
            if was_paused:
                was_paused = False
                rec.Reset()
                query_words.clear()
                latest[0] += 1
                last_partial = ""
                print("\n[listening - new query]")
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "")
                if text:
                    print(f"\rFINAL:   {text}" + " " * 20)
                emit_stable(finalizer.final(text))
                last_partial = ""
            else:
                partial = json.loads(rec.PartialResult()).get("partial", "")
                if partial and partial != last_partial:
                    print(f"\rpartial: {partial}" + " " * 20, end="", flush=True)
                    last_partial = partial
                emit_stable(finalizer.partial(partial))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
