# Kurious
Speech recognition project that queries 3-6 words from user then gets calculated to output wikipedia articles based on the words inputted. 

## Setup
1. Download the Vosk model: https://alphacephei.com/vosk/models → `vosk-model-en-us-0.22-lgraph`
2. Extract it into the repo root so you have `vosk-model-en-us-0.22-lgraph/` next to `asr.py` (it's gitignored — too large for GitHub).
3. `pip install -r requirements.txt` (includes torch, a large download).
4. Run `run_asr.bat` (or `python asr.py`). Use `python asr.py --backend lazy` for the slow baseline Wikipedia client.
   - The first run downloads the ~90MB MiniLM reranker model from Hugging Face (needs internet once; no login needed).
   - The reranker takes ~10–20s to load at startup; `[reranker ready]` is printed when done. The first search waits for it.
5. Tests: `python test_finalizer.py`, `python test_wiki.py`, `python test_rerank.py` (add `--net` to hit Wikipedia and load the real model).

Plan and notes live in `docs/`; search latency logs are written to `logs/`.
