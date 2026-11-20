import collections, glob, os, re, sys

gen = sys.argv[1]
FUNC = re.compile(r'(?:DEFINE_REX_FUNC|PPC_FUNC_IMPL|PPC_FUNC)\((?:__imp__)?(sub_[0-9A-Fa-f]{8})\)')
INS = re.compile(r'^\s*// ([a-z][a-z0-9.+_-]*)\s+(.*?)\s*$')

funcs = {}
for path in sorted(glob.glob(os.path.join(gen, '*.cpp'))):
    cur = None
    for line in open(path, encoding='utf-8', errors='replace'):
        m = FUNC.match(line)
        if m:
            cur = 'sub_' + m.group(1)[4:].upper()
            funcs.setdefault(cur, [])
            continue
        if cur:
            m = INS.match(line)
            if m:
                funcs[cur].append((m.group(1), m.group(2)))
print('functions read: %d' % len(funcs))
if not funcs:
    sys.exit('no functions found: wrong folder, or the comment format is different')

def callees(name):
    out = []
    for mn, ops in funcs.get(name, []):
        if mn == 'bl':
            m = re.match(r'0x([0-9a-fA-F]+)', ops)
            if m:
                out.append('sub_%08X' % int(m.group(1), 16))
    return out

callers = collections.defaultdict(set)
for n in funcs:
    for c in callees(n):
        callers[c].add(n)

def has_li(name, value):
    for mn, ops in funcs[name]:
        if mn in ('li', 'addi'):
            m = re.match(r'r\d+,\s*(?:r0,\s*)?(-?(?:0x[0-9a-fA-F]+|\d+))\s*$', ops)
            if m and int(m.group(1), 0) == value:
                return True
    return False

def show(name, limit=220):
    print('\n----- %s (%d instructions) -----' % (name, len(funcs[name])))
    for mn, ops in funcs[name][:limit]:
        print('   %s %s' % (mn, ops))
    if len(funcs[name]) > limit:
        print('   ... (%d more)' % (len(funcs[name]) - limit))

# DetermineStreamingSections loads the section numbers 2500, 2400, 2600
dss = [n for n in funcs if all(has_li(n, v) for v in (2500, 2400, 2600))]
print('\nSTEP 1 - functions that load 2500, 2400 and 2600: %s' % (dss or 'none'))
if not dss:
    part = [(n, sum(has_li(n, v) for v in (2500, 2400, 2600))) for n in funcs]
    print('   with two of the three: %s' % [n for n, k in part if k >= 2][:10])

gpz = set()
for d in dss:
    print('\nDetermineStreamingSections candidate %s' % d)
    print('   first callees : %s' % callees(d)[:5])
    print('   callers       : %s' % sorted(callers[d]))
    for dcz in sorted(callers[d]):
        print('   DetermineCurrentZones candidate %s, callees: %s' % (dcz, callees(dcz)))
        for c in callees(dcz):
            if c not in funcs or c in gpz:
                continue
            k = collections.Counter(mn for mn, _ in funcs[c])
            score = (k['fsqrts'] > 0) + (k['fdivs'] > 0) + (k['fcmpu'] > 0) + (k['fmadds'] > 0)
            print('      callee %s: %d instr, score %d/4' % (c, len(funcs[c]), score))
            if score >= 3 and len(funcs[c]) < 400:
                gpz.add(c)

print('\nSTEP 2 - GetPredictedZone candidates: %s' % (sorted(gpz) or 'none'))
for g in sorted(gpz):
    print('   callers of %s: %s' % (g, sorted(callers[g])))
    print('   callees of %s: %s' % (g, callees(g)))
    show(g)

if not gpz:
    print('\nSTEP 3 - fallback scan')
    for n, ins in funcs.items():
        if 40 < len(ins) < 400 and has_li(n, 6) and has_li(n, 0):
            k = collections.Counter(mn for mn, _ in ins)
            if k['fsqrts'] and k['fdivs']:
                print('   possible GetPredictedZone:', n, 'callees', callees(n))
print('\nDone.')