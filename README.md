# Kurious
Speech recognition project that queries 3-6 words from user then gets calculated to output wikipedia articles based on the words inputted. 

## Setup
1. Download the Vosk model: https://alphacephei.com/vosk/models → `vosk-model-en-us-0.22-lgraph`
2. Extract it into the repo root so you have `vosk-model-en-us-0.22-lgraph/` next to `asr.py` (it's gitignored — too large for GitHub).
3. `pip install vosk sounddevice`
4. Run `run_asr.bat` (or `python asr.py`).
