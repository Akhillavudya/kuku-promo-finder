import re, glob, os, statistics as st
D = os.path.join('pack', 'I Married a Broken Soldier. He was a Duke')
files = sorted(glob.glob(os.path.join(D, '*.txt')))
hdr = re.compile(r'^\*\*(.+?):\*\*\s*$')
ts  = re.compile(r'^Start:\s*\((\d+):(\d+(?:\.\d+)?)\)\s*\|\s*End:\s*\((\d+):(\d+(?:\.\d+)?)\)')
def sec(m,s): return int(m)*60+float(s)
kinds, durs, nblocks, nscenes, ndlg = {}, [], [], [], []
bad = []
for f in files:
    lines = open(f, encoding='utf-8').read().splitlines()
    blocks, scenes, dlg = 0, 0, 0
    last_end = 0.0
    i = 0
    while i < len(lines):
        L = lines[i].strip()
        if L.startswith('SCENE '): scenes += 1
        m = hdr.match(L)
        if m and i+1 < len(lines):
            t = ts.match(lines[i+1].strip())
            if t:
                blocks += 1
                raw = m.group(1)
                kind = raw.split('(')[0].strip()
                kinds[kind] = kinds.get(kind, 0) + 1
                if kind not in ('CAMERA','ACTION','SOUND FX','MUSIC','VFX','TEXT','TITLE'):
                    dlg += 1
                last_end = max(last_end, sec(t.group(3), t.group(4)))
            else:
                bad.append((os.path.basename(f), i+1, L))
        i += 1
    nblocks.append(blocks); nscenes.append(scenes); ndlg.append(dlg); durs.append(last_end)
print(f'episodes: {len(files)}')
print(f'duration s : min {min(durs):.1f}  med {st.median(durs):.1f}  max {max(durs):.1f}  total {sum(durs)/60:.1f} min')
print(f'blocks/ep  : min {min(nblocks)}  med {st.median(nblocks):.0f}  max {max(nblocks)}  total {sum(nblocks)}')
print(f'scenes/ep  : min {min(nscenes)}  med {st.median(nscenes):.0f}  max {max(nscenes)}')
print(f'dialogue/ep: min {min(ndlg)}  med {st.median(ndlg):.0f}  max {max(ndlg)}')
print('block kinds (top 15):')
for k,v in sorted(kinds.items(), key=lambda x:-x[1])[:15]:
    print(f'   {v:5d}  {k}')
print(f'distinct kinds: {len(kinds)}')
print(f'headers with no parseable timestamp: {len(bad)}')
for b in bad[:5]: print('   ', b)
