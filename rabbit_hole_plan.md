# Rabbit Hole — Project Plan

**Course:** COMP6822001 — Speech Recognition (Final Project)
**Concept:** The user speaks 3–6 words; the system continuously transcribes them and surfaces an interesting Wikipedia article that connects them — updating live as words are spoken, not after a "speak → stop → process" cycle.

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

## 3. Revised Roadmap (Step by Step)

### Step 1 — Speech recognition (backend)
- **Do not train a model.** Use pretrained Vosk:
  - `vosk-model-en-us-0.22` for accuracy, or the `small` model for weak hardware.
- Vosk streams natively: `PartialResult()` while speaking, `Result()` when a segment ends. This directly satisfies the "partial/updated transcription" requirement.
- Redirect the effort saved from training into WER experiments.

### Step 2 — Text processing (backend)
- Keep it small for 3–6 words: lowercase, remove stopwords ("the", "of", "um"), optionally lemmatize / extract nouns and entities with spaCy.
- **Word finalizer** is the more important piece: Vosk partials change as the user speaks
  (`machine` → `machine learn` → `machine learning`). Only send stable words to the query, or results will flicker and the API gets spammed.

### Step 3 — Wikipedia API (backend)
- No need to compute most-used words per article — Wikipedia's CirrusSearch already ranks well.
- Endpoints:
  - `/w/rest.php/v1/search/page?q=...&limit=20` — candidate articles + excerpts
  - `/api/rest_v1/page/summary/{title}` — extract, thumbnail, description (for frontend cards)
  - Pageviews API — signal for "interesting"
- Always send a descriptive `User-Agent` header (app name + contact), or requests may be throttled/rejected.
- Cache results to reduce latency and network dependency.

### Step 4 — Reranking model (backend)
Wikipedia returns ~20 candidates; our model reranks them with a combined score:

| Component | What it measures | How |
|---|---|---|
| Relevance | Match between spoken words and article | TF-IDF / BM25, or local sentence embeddings (e.g. `all-MiniLM-L6-v2`) |
| Coverage | How many spoken words the article connects | Count matched query terms in extract/title |
| Interestingness | How engaging the article is | Pageviews, has image, article length |

- Coverage is the core of the Rabbit Hole idea: an article linking "volcano + music + Iceland" beats one matching a single word.
- **Define "interesting" explicitly in the report** — it is subjective and will be questioned.

### Step 5 — Frontend
- Build a **thin vertical slice first** (mic → Vosk → WebSocket → plain HTML page showing partial text + article title), then polish each layer.
- See Section 6 for design ideas.

### Step 6 — Evaluation (backend + frontend)
- Replace random stress testing with a **structured retrieval experiment**: ~50 queries, each result judged "relevant/interesting or not" → report **Precision@1**.
- Use two independent raters to reduce subjectivity.
- Log frontend bugs separately.

---

## 4. Required by the Brief (Missing from Original Roadmap)

- [ ] **WER experiments** (`jiwer`)
  - Baseline: clean speech
  - E1: Indonesian-accented vs. native English speech (Vosk is trained mostly on US accents)
  - E2: Background noise (campus / café conditions)
  - Optional: rare words / proper nouns (key risk for a Wikipedia app)
- [ ] **Latency measurement** — timestamp every pipeline stage
  - ASR latency: word spoken → word on screen
  - End-to-end latency: word finalized → article shown
  - Real-time factor (RTF)
- [ ] **Error analysis** — reference vs. output table, categorize substitution/deletion/insertion, identify patterns
- [ ] **Concrete, reachable target user** — "people who like to explore" is too generic; confirm with lecturer
- [ ] **User testing with ≥5 real target users** — tasks, observation, questionnaire/interview, analysis
- [ ] **Combined evaluation** — link user feedback to technical results
- [ ] **AI Usage Log** — start now, fill in continuously (including planning conversations)
- [ ] **AI Usage Declaration** at the end of the report
- [ ] **Evidence**: screenshots, architecture diagram, results, transcription examples, feedback analysis

---

## 5. Pros and Cons of Key Decisions

### Pretrained Vosk (vs. training / Whisper)
- **Pros:** native streaming with partials, fast on CPU, fully offline, easy setup.
- **Cons:** lower accuracy than Whisper-class models; likely weaker on Indonesian-accented English; **fixed vocabulary** means rare words and proper nouns (e.g. "Fibonacci", "Majapahit") may be misrecognized or impossible to output; Kaldi architecture is more involved to explain.
- **Alternative:** faster-whisper + streaming wrapper — more accurate, better on rare words, but not natively streaming, higher latency, wants a GPU.
- **Verdict:** Vosk is safer; treat vocabulary coverage as a known weakness and test it.

### Word finalizer
- **Pros:** stable queries, no UI flicker, far fewer API calls.
- **Cons:** adds deliberate delay; stability threshold needs tuning (too strict = laggy, too loose = flicker).

### Live Wikipedia API (vs. local index)
- **Pros:** no multi-GB download, always current, strong ranking for free.
- **Cons:** demo depends on network; variable response times; rate limits; risk of the lecturer asking "what did *you* build?"
- **Mitigation:** caching + our own reranker.

### Reranking (relevance + coverage + interestingness)
- **Pros:** cheap, explainable, clearly our own contribution.
- **Cons:** short extracts limit TF-IDF; embeddings add another model and latency; interestingness weights are hand-tuned and must be justified.

### Vertical slice first
- **Pros:** confirms real-time pipeline early (protects the 30% application component); integration issues surface early.
- **Cons:** some throwaway code; app looks rough for longer.

### Structured retrieval evaluation
- **Pros:** reportable metric, more rigorous experimentation section.
- **Cons:** manual labeling effort; subjective judgments.

### Accent and noise experiments
- **Pros:** directly tied to real users and demo environment.
- **Cons:** requires recruiting speakers and consistent recordings.

### Ambitious frontend
- **Pros:** strong demo impact, memorable concept.
- **Cons:** time sink; Three.js competes with Vosk for CPU (may hurt latency); rubric doesn't reward visuals directly.
- **Verdict:** do the partial-vs-final visualization first; 3D only if time allows.

### Overall concept
- **Pros:** fun, original, easy to demo and explain.
- **Cons:** weakest point is the **real-world problem** framing. User testing, the target-user component, and the discussion section all depend on it — pin down a concrete target user early.

---

## 6. Frontend Ideas

1. **Literal rabbit hole** — 3D tunnel (Three.js); each finalized word drops you one level deeper; articles appear as portals on the walls.
2. **Visible partial vs. final words** — partial words are translucent and flickering, then "solidify" when finalized. Cheap, looks good, and proves the system is streaming. *(Do this first.)*
3. **Constellation mode** — words become stars, the article is the constellation connecting them; lines show which word matched which part (visualizes the coverage score).
4. **Trail map** — end-of-session graph of every article visited; exportable/shareable; useful for user testing questions.
5. **Voice navigation** — "deeper" follows a link, "back" returns. Nice-to-have only (adds command-detection complexity).

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
