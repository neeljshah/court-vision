"""Contract Q6 scan -- patterns assembled from single characters at runtime."""
import re, sys
from pathlib import Path
c = [chr(n) for n in range(32, 127)]
def w(*i): return "".join(c[n - 32] for n in i)
WORDS = [w(68,79,76,76,65,82), w(82,79,73), w(80,82,79,70,73,84), w(69,68,71,69), w(66,65,78,75,82,79,76,76)]
FIGS  = [w(43,49,56,46,51,56), w(48,46,49,49,57), w(43,53,52), w(55,56,46,49,49),
         w(56,46,57,52), w(53,52,46,53,55), c[4]]
PATS = ([re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in WORDS]
        + [re.compile(re.escape(t), re.IGNORECASE) for t in FIGS])
total = 0
for arg in sys.argv[1:]:
    tail = arg.startswith("tail1:")
    path = arg[6:] if tail else arg
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if tail:
        text = [line for line in text.splitlines() if line.strip()][-1]
    hits = sum(len(p.findall(text)) for p in PATS)
    total += hits
    print("%-96s %d" % (arg, hits))
print("FILES %d  HITS %d" % (len(sys.argv) - 1, total))
