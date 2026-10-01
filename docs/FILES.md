# What Each File Does

## Main program
| File | What it does |
|---|---|
| `asr.py` | The app itself. Listens to your mic, turns speech into words, and prints the best Wikipedia article for them. |
| `run_asr.bat` | Double-click to start the app. |
| `rerank.py` | Picks the best article out of the ones Wikipedia returned: relevant to your words, connects all of them, and is interesting (not obvious). |
| `wiki.py` | Asks Wikipedia for articles that match your words. The fast version, used by default. |
| `wiki_lazy.py` | A slow, simple version of `wiki.py`. Only used to compare speed in the report. |
| `wiki_common.py` | Small helpers both Wikipedia files share (e.g. "is this article about a person?"). |
| `server.py` | WebSocket bridge (`ws://localhost:8765`) and static HTTP server (`http://localhost:8000`) for the 3D globe frontend. |

## Tests
| File | What it checks |
|---|---|
| `test_server.py` | HTTP serving of the frontend and WebSocket event broadcasting. |
| `test_finalizer.py` | Words are only used once the speech recognizer is sure of them. |
| `test_wiki.py` | Wikipedia results come back correctly. |
| `test_rerank.py` | The best article gets picked and junk pages are thrown out. |

## Setup files
| File | What it's for |
|---|---|
| `README.md` | How to install and run the project. |
| `requirements.txt` | List of Python packages to install. |
| `.gitignore` | Tells Git which files not to upload (big, personal, or generated files). |

## Folders
| Folder | What's inside |
|---|---|
| `docs/` | Project plan, this file, and the pipeline explanation PDF. |
| `logs/` | Speed records of every search (see below). |
| `vosk-model-en-us-0.22-lgraph/` | The speech recognition model. Downloaded separately, too big for GitHub. |
| `__pycache__/` | Python's own temporary files. Safe to ignore or delete. |

## `cache.db`
Wikipedia's answers get saved here so repeat searches are instant and still work offline. Entries expire after 24 hours.
Safe to delete, it rebuilds itself (first searches will just be slower).

## `logs/`
Every search adds a row to `logs/latency.csv`: what was said, how long each step took, and which article was picked.
Used for the report's speed measurements. Older files like `latency_20260928_101102.csv` are from before the log format changed.
