"""Phase 1+2: continuous mic -> Vosk -> word finalizer -> query terms on stdout."""
import json
import queue
import sys

import sounddevice as sd
from vosk import KaldiRecognizer, Model

MODEL_PATH = "vosk-model-en-us-0.22-lgraph"
SAMPLE_RATE = 16000

STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "is", "are", "was", "were", "be", "been", "it", "this", "that",
    "um", "uh", "with", "as", "by", "from", "i", "you", "we", "so",
}

audio_q = queue.Queue()


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
    model = Model(MODEL_PATH)
    rec = KaldiRecognizer(model, SAMPLE_RATE)

    finalizer = WordFinalizer()
    query_words = []

    def emit_stable(words):
        for w in words:
            if w not in STOPWORDS:
                query_words.append(w)
        if words:
            print(f"\nquery:   {' '.join(query_words)}")

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE, blocksize=8000, dtype="int16",
        channels=1, callback=callback,
    ):
        print("Listening... (Ctrl+C to stop)")
        last_partial = ""
        while True:
            data = audio_q.get()
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
