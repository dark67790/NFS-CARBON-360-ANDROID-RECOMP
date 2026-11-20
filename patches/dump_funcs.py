import glob, os, re, sys

gen = sys.argv[1]
want = [w.upper().replace('SUB_', 'sub_') for w in sys.argv[2:]]
FUNC = re.compile(r'(?:DEFINE_REX_FUNC|PPC_FUNC_IMPL|PPC_FUNC)\((?:__imp__)?(sub_[0-9A-Fa-f]{8})\)')
INS = re.compile(r'^\s*// ([a-z][a-z0-9.+_-]*)\s*(.*?)\s*$')

funcs = {}
for path in sorted(glob.glob(os.path.join(gen, '*.cpp'))):
    cur = None
    for line in open(path, encoding='utf-8', errors='replace'):
        m = FUNC.match(line)
        if m:
            cur = 'sub_' + m.group(1)[4:].upper()
            funcs.setdefault(cur, [])
            continue
        m = INS.match(line)
        if cur and m:
            funcs[cur].append((m.group(1), m.group(2)))

def callees(n):
    return ['sub_%08X' % int(o[2:], 16) for mn, o in funcs.get(n, [])
            if mn == 'bl' and re.match(r'0x[0-9a-fA-F]+$', o.split()[0] if o else '')]

for n in want:
    ins = funcs.get(n)
    print('\n=========== %s (%s) ===========' % (n, '%d instr' % len(ins) if ins else 'NOT FOUND'))
    if not ins:
        continue
    print('callers:', sorted(f for f in funcs if n in callees(f)))
    print('callees:', callees(n))
    for mn, o in ins[:500]:
        print('  %s %s' % (mn, o))