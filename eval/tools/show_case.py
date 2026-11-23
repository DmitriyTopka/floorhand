"""Print one candidate (by chat hash + question ts) in full, masked, with
message timestamps. Review helper only. Usage: show_case.py HASH QTS [HASH QTS...]"""
import sys
from tt_logs import load_days, merge_chats, kyiv
from find_candidates import cid
from pii import mask

chats = {cid(k): v for k, v in merge_chats(load_days()).items()}
args = sys.argv[1:]
for hsh, qts in zip(args[::2], args[1::2]):
    h = chats[hsh]["history"]
    qts = float(qts)
    i = min(range(len(h)), key=lambda n: abs(float(h[n]["ts"]) - qts))
    lo = i
    while lo > 0 and h[lo - 1]["author"] == "client":
        lo -= 1
    print(f"######## {hsh} {qts}")
    for x in h[max(0, lo - 2): i + 7]:
        print(f"[{float(x['ts']):.3f} {kyiv(x['ts']):%d.%m %H:%M:%S} {x['author']}] {mask(x['content'])[:600]}")
