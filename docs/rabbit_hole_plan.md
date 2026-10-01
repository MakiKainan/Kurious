# Rabbit Hole — Project Plan

**Course:** COMP6822001 — Speech Recognition (Final Project)
**Concept:** The user speaks 3–6 words; the system continuously transcribes them and surfaces an interesting Wikipedia article that connects them — updating live as words are spoken, not after a "speak → stop → process" cycle.

> **If you are Claude:** whenever you finish a task from this plan, check its box (`- [ ]` → `- [x]`, or add ✅ to a roadmap step) in this file.

---

## 1. Rubric Clarification: Model vs. Inference

| Question | Answer | Source in brief |
|---|---|---|
| Do we have to build/train our own ASR model? | **No.** Pretrained, open-source, and Hugging Face models are explicitly allowed. Training is never mentioned. | Section 1, Section 11 ("Allowed") |
| Do we have to run inference ourselves? | **Yes, locally.** External speech APIs (Google, Azure, Amazon Transcribe, OpenAI Speech, AssemblyAI, etc.) are banned. | Sections 1, 11, 17 |
| Is the Wikipedia API allowed? | Yes — it is not a speech recognition service. | Section 11 (only ASR APIs are restricted) |
| Do we still need to understand the model? | **Yes.** The report must cover the selected model, its architecture, algorithms, and limitations, and we may be questioned during the demo. | Sections 15, 21.3; Fundamentals = 15% |

For Vosk, be ready to explain: MFCC feature extraction → acoustic model → lexicon + language model → WFST decoding → how partial results are produced while audio is still streaming.

---

## 2. Architecture

```
Microphone (always open)
      ↓
Audio capture (continuous stream, 16 kHz mono)
      ↓
Vosk ASR (KaldiRecognizer) ── PartialResult() / Result()
      ↓
Word finalizer (decides when a word is stable)
      ↓
Query builder (normalize, stopwords, lemmatize)
      ↓
Wikipedia search → top ~20 candidates
      ↓
Reranker (relevance + coverage + interestingness)
      ↓
FastAPI + WebSocket → Frontend (live transcript + article)
```

Each finalized word triggers a live article update — not a batch after all six words.

---

## 3. Roadmap

### ✅ Step 1 — Speech recognition (backend)
- Pretrained Vosk model (`vosk-model-en-us-0.22-lgraph`), no training.
- `asr.py`: mic → `KaldiRecognizer` → `PartialResult()` while speaking, `Result()` at segment end.
- `run_asr.bat` launches it.

### ✅ Step 2 — Text processing (backend)
- `WordFinalizer` in `asr.py`: a word is stable once a new word appears after it in the partial; flush remaining words on `Result()`.
- Stopwords filtered into a running `query_words` list (lowercase, small hardcoded stopword set).
- `test_finalizer.py` covers the finalizer logic.

### ✅ Step 3 — Wikipedia API (backend)
- [x] `wiki_lazy.py` baseline: REST search + per-candidate summary and pageviews (42 requests per query), stdlib only.
- [x] `wiki.py` optimized client: one MediaWiki Action API call returns extract, thumbnail, description, pageviews and categories for ~20 candidates (deviation from the REST endpoints above, same data, far fewer round trips). Follows `pvipcontinue` pagination, or ~8 of 20 candidates silently get 0 views.
- [x] Session reuse, retries, descriptive `User-Agent`, memory + sqlite (`cache.db`, 24h TTL) cache with stale fallback when offline.
- [x] Wider pool: full query + one search per word, merged by pageid with `matched_by` (feeds Step 4 coverage).
- [x] Flags `is_person`, `is_disambig`, `is_list` derived per candidate (inputs for the Step 4 filter and Step 5 themes).
- [x] `asr.py` runs searches on a background worker; superseded queries are skipped/dropped; `--backend full|lazy`; every search logged to `logs/latency.csv`.
- [x] Tests: `test_wiki.py` (`--net` for live).
- Measured cold latency for "volcano iceland music": full ~2.8–3.0s (3–6 requests), lazy ~14–29s (42 requests). Cache hit ~0ms. Redo with real runs for the report.

### ✅ Step 4 — Reranking model (backend)
- [x] `rerank.py`, tested by `test_rerank.py` (`--net` for real model + live Wikipedia).
- [x] **Noise filter (before scoring):** drops disambiguation pages, lists (`List/Index/Outline/Glossary/Timeline of`), date pages (`1997`, `1990s`, `19th century`, `March 1`, `1997 in music`), stubs (< 2,500 bytes or a `... stubs` category) and non-famous people (< 30,000 views over ~60 days). Falls back to the unfiltered pool if everything is dropped.
- [x] **Relevance** `rel`: cosine similarity between `all-MiniLM-L6-v2` embeddings of the spoken words and `title. description. extract` (first 128 tokens), clipped to [0, 1]. Article embeddings cached by page id.
- [x] **Coverage** `cov`: fraction of spoken words the article connects to — returned by that word's own search, or mentioned in title/description/extract (accent-stripped, plural-stripped, prefix match for 4+ letters).
- [x] **Interestingness** `int` (report definition): `0.5·views + 0.25·has_image + 0.25·depth`, with `views = log10(views+1)/6` capped at 1 (1M views in ~60 days = 1.0) and `depth = min(1, bytes/50,000)`.
- [x] **Obviousness penalty**: title equal to a spoken word or the whole query (e.g. "Volcano") is penalized, so the rabbit hole goes past the obvious.
- [x] Score = `0.40·rel + 0.35·cov + 0.25·int − 0.15·obvious`. Weights are hand-set; tune and justify them against the Step 6 Precision@1 set.
- [x] `asr.py` prints the top pick with its Wikipedia URL, score parts and 2 runners-up; `logs/latency.csv` logs `wait_ms`, `search_ms`, `rerank_ms`, `total_ms`, `n_filtered`, `top_title`.
- Measured: rerank of a fresh ~76-article pool 1.1–1.5s cold (MiniLM, 4 threads, 128 tokens; 256 tokens was ~4.5s), ~30ms when embeddings are cached. Model load ~11s of imports at startup, in the background. Sample top picks: "napoleon war russia" → French invasion of Russia; "shark ocean horror" → Monster Shark; "volcano iceland music" → Thrihnukagigur.

### ✅ Step 5 — Frontend
- [x] Connected interactive 3D WebGL puzzle-globe frontend (`superfront end/Kurious.dc.html`) to live ASR and search pipeline.
- [x] `server.py` hosts a WebSocket server on `ws://localhost:8765` and static HTTP server on `http://localhost:8000` (with auto-redirect from `/`).
- [x] Live events stream in real time: `partial` (spinning globe impulse & flickering text), `query` (inked words on 3D tiles), `article` (prefetched top candidate + runner-up tiles), and `stopped` (rotates globe, lifts & slots tile, slides out editorial article card).
- [x] Tested via `test_server.py`.

### ☐ Step 6 — Evaluation (backend + frontend)
- Run ~50 queries, two raters judge "relevant/interesting or not," report Precision@1.
- Log frontend bugs separately from ASR/retrieval bugs.

---

## 4. Required by the Brief (Not Yet Done)

- [ ] **WER experiments** (`jiwer`)
  - Baseline: clean speech
  - E1: Indonesian-accented vs. native English speech
  - E2: Background noise (campus / café conditions)
  - Optional: rare words / proper nouns
- [ ] **Latency measurement** — timestamp every pipeline stage
  - ASR latency: word spoken → word on screen
  - End-to-end latency: word finalized → article shown
  - Real-time factor (RTF)
- [ ] **Error analysis** — reference vs. output table, categorize substitution/deletion/insertion, identify patterns
- [ ] **Concrete, reachable target user** — confirm with lecturer
- [ ] **User testing with ≥5 real target users** — tasks, observation, questionnaire/interview, analysis
- [ ] **Combined evaluation** — link user feedback to technical results
- [ ] **AI Usage Log** — fill in continuously (including planning conversations)
- [ ] **AI Usage Declaration** at the end of the report
- [ ] **Evidence** — screenshots, architecture diagram, results, transcription examples, feedback analysis

---

## 5. Key Decisions

- ASR: pretrained Vosk (`lgraph`), not Whisper — streams natively, runs on CPU, works offline. Known weakness: fixed vocabulary misses rare/proper nouns — test this explicitly in Step 4's WER experiments.
- Word finalizer: required before querying Wikipedia, or the UI flickers and the API gets spammed on every partial revision.
- Wikipedia: call the live API + cache, don't build a local index.
- Reranker: hand-rolled relevance + coverage + interestingness score — keep it explainable, justify the weights in the report.
- Frontend: ship the vertical slice first (Section 3, Step 5), then layer on visuals.

---

## 6. Frontend Ideas

1. **Literal rabbit hole** — 3D tunnel (Three.js); each finalized word drops you one level deeper; articles appear as portals on the walls.
2. **Visible partial vs. final words** — partial words are translucent/flickering, then solidify when finalized. *(Build this first — cheap, proves the system is streaming.)*
3. **Constellation mode** — words become stars, the article is the constellation connecting them; lines show which word matched which part of the article.
4. **Trail map** — end-of-session graph of every article visited; exportable, useful for user-testing questions.
5. **Voice navigation** — "deeper" follows a link, "back" returns. Nice-to-have only.

---

## 7. Rubric Mapping

| Component | Weight | Covered by |
|---|---|---|
| Speech Recognition Fundamentals | 15% | Vosk/Kaldi explanation, pipeline, limitations |
| Experimental Workflow & Technical Evaluation | 20% | WER baseline + conditions, latency, RTF, Precision@1, error analysis |
| System Analysis & User Evaluation | 20% | Combined technical + user testing analysis |
| Real-Time Application | 30% | Streaming pipeline, partial transcripts, live article updates |
| Real-World Problem & Target User | 5% | Concrete target user + problem statement |
| AI Usage, Verification & Reflection | 10% | AI Usage Log, verification evidence, declaration |
