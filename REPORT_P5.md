STATUS: IN PROGRESS — phase 2 (workers running)
Branch p5-ref @ bbb685d; worker branches p5-viewer, p5-engine, p5-opensta @ bbb685d (created); started 2026-11-05 21:46 CST, last update 2026-11-05 21:55 CST

## 1. Result table
| ID | status (done / partial / skipped) | commit(s) | note |
|----|-----------------------------------|-----------|------|
| R32 | pending | | W1 |
| R33 | pending | | W1 |
| R34 | pending | | W1 |
| R35 | pending | | W2 |
| R36 | pending | | W2 |
| R37 | pending | | W2 |
| R38 | pending | | W3 |
| R39 | pending | | W3 |
| R40 | pending | | lead |
| R41 | pending | | lead, optional |
| R42 | pending | | lead, optional |
| R43 | pending | | lead |

## 2. Tests
before (viewer-v2 @ ed316ad): 155 (4 skipped) on /usr/bin/python3 (3.9.6), 155 (1 skipped) on ~/.local/bin/python3.12
after interface commit bbb685d: 159 (4 skipped) / 159 (1 skipped) — 4 new lookup_detail tests
after:  (pending)
commands:
    /usr/bin/python3 -m unittest discover -s tests
    ~/.local/bin/python3.12 -m unittest discover -s tests

## 3. Viewer
(pending)

## 4. OpenSTA correlation
(pending)

## 5. Engine
(pending)

## 6. Decisions I made (ambiguities resolved on my own)
1. Worktree location. Section 9 step 3 names `../p5-wt/w1` (outside the repo), while section 1 allows new directories only under the repo and `~/tools/`. I took the explicit step-3 path, `../p5-wt/{w1,w2,w3}` next to the repo, as the more specific rule; the worktrees are removed at the end (section 8.5).
2. `.gitignore` did not exist on viewer-v2. Section 1 allows adding `ref/results/`, `out/`, `*.pyc`; I created it with `*.pyc` (the untracked `__pycache__/` directories hold only `.pyc` files). W3 adds `ref/results/` and `out/`.
3. Docker is not available on this Mac (`docker info` fails), so W3 was told to use route 2 (OpenSTA source build under `~/tools/opensta`, Homebrew dependencies) within the 90-minute box, else route 3.
4. The Tk smoke test on `s1423` (section 6) belongs to W1's `tests/test_viewer.py`, but `data/s1423.v` is made by W3 on another branch; W1 was told to write it so it skips while the files are absent. It runs after the merge.

## 7. Decisions for you
(pending)

## 8. Reviewer findings
(pending)

## 9. Not done
(pending)

## 10. How to reproduce every number above
    git checkout viewer-v2
    /usr/bin/python3 -m unittest discover -s tests          # 155 tests, 4 skipped
    ~/.local/bin/python3.12 -m unittest discover -s tests   # 155 tests, 1 skipped
