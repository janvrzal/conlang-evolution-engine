"""Měření Talvery podle oddílů „Co měřit“ a study cases (docs/scenare/talvera.md).

Spuštění: ``python scripts/talvera_measure.py run1.json [run2.json …]``, kde vstupem je export
``cee run docs/scenare/talvera.world.json -o run1.json`` (jiné semínko: pole ``seed``).
Jen standardní knihovna; čte jen export běhu.
"""
import json, sys, math, statistics as st, collections

def lev(a, b):
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (x != y))
    return d[-1]

class Run:
    def __init__(self, path):
        o = json.load(open(path))
        self.o = o
        self.G = {g['id']: g for g in o['groups']}
        self.T = {t['id']: t for t in o['territories']}
        self.lx = o['lexicon']
        self.mem = {g: l for l, gs in o['snapshots'][-1]['languages'].items() for g in gs}
        self.home = [g for g in self.G if self.G[g]['domain'] == 'home' and g in self.lx]

    def region(self, g):
        t = self.T[self.G[g]['territory']]
        while t['level'] != 'region' and t.get('parent') in self.T:
            t = self.T[t['parent']]
        return t['id']

    def villages(self, region, lang=None, settlers=False):
        out = []
        for g in self.home:
            if self.region(g) != region or '>' in g:
                continue
            if ('+' in g) != settlers:
                continue
            if lang and self.G[g]['code_language'] != lang:
                continue
            out.append(g)
        return out

    def dist(self, a, b):
        """(lexikální vzdálenost, hlásková vzdálenost u sdílených kořenů)."""
        A, B = self.lx[a], self.lx[b]
        ks = [k for k in A if k in B]
        if not ks:
            return (float('nan'), float('nan'))
        same = [k for k in ks if A[k]['root'] == B[k]['root']]
        lexical = 1 - len(same) / len(ks)
        phon = st.mean(lev(A[k]['form'], B[k]['form']) / max(len(A[k]['form']), len(B[k]['form']), 1)
                       for k in same) if same else float('nan')
        return (lexical, phon)

    def loan_share(self, g, donor):
        w = self.lx[g]
        return sum(v['language'] == donor for v in w.values()) / len(w)

    def pos(self, g):
        return self.G[g]['position']

def mean(xs):
    xs = [x for x in xs if x == x]
    return st.mean(xs) if xs else float('nan')

def era1(r):
    """Po rozpadu Varadu: vzdálenost serenských obcí přes nové hranice vs uvnitř nástupce."""
    states = {'varadska_obec': [f'm01-0{i}' for i in range(1, 7)],
              'dolni_eren': [f'm02-0{i}' for i in range(1, 5)],
              'brodska_mesta': ['m03-02', 'm03-04']}
    of = {reg: s for s, regs in states.items() for reg in regs}
    gs = [g for reg in of for g in r.villages(reg, 'seren')]
    inside, across = [], []
    for i, a in enumerate(gs):
        for b in gs[i + 1:]:
            ra, rb = r.region(a), r.region(b)
            if ra == rb:
                continue
            km = math.dist(r.pos(a), r.pos(b))
            if km > 25:
                continue
            (inside if of[ra] == of[rb] else across).append(r.dist(a, b)[1])
    return {'uvnitř nástupce': round(mean(inside), 3), 'přes hranici': round(mean(across), 3),
            'párů': (len(inside), len(across))}

def era2(r):
    """Přesídlenci 450 a 525: přežití domácího kódu a přiblížení k sousedům."""
    out = {}
    for reg, lang in [('m05-02', 'seren'), ('m04-05', 'talmur'), ('m05-03', 'talmur')]:
        settlers = [g for g in r.home if r.region(g) == reg and '+' in g]
        own = [g for g in settlers if '>' not in g]
        shifted = [g for g in settlers if '>' in g]
        pop_own = sum(r.G[g]['population'] for g in own)
        pop_shift = sum(r.G[g]['population'] for g in shifted)
        natives = r.villages(reg)
        d = mean([r.dist(s, n)[0] for s in own for n in natives]) if own and natives else float('nan')
        out[reg] = {'kód osadníků': lang, 'mluví ho': pop_own, 'přešlo': pop_shift,
                    'lex. vzdál. od starousedlíků': round(d, 2)}
    return out

def era3(r):
    """Naret vs vnitrozemí: veretské výpůjčky; ostrovní kapsa m08-08 vs ligový m08-04 od Selvy."""
    nar = r.villages('m09-05', 'idar'); inl = r.villages('m10-06', 'idar')
    selva = r.villages('m07-04', 'veret')
    isl = r.villages('m08-08', 'veret'); lig = r.villages('m08-04', 'veret')
    return {'veretské výpůjčky Naret': round(mean([r.loan_share(g, 'veret') for g in nar]), 3),
            'veretské výpůjčky m10-06': round(mean([r.loan_share(g, 'veret') for g in inl]), 3),
            'vzdál. od Selvy m08-08 (lex/hlás)': tuple(round(mean([r.dist(a, b)[i] for a in isl for b in selva]), 3) for i in (0, 1)),
            'vzdál. od Selvy m08-04 (lex/hlás)': tuple(round(mean([r.dist(a, b)[i] for a in lig for b in selva]), 3) for i in (0, 1))}

def era4(r):
    """Osady věku objevování: velikost, jazyk, vzdálenost od mateřské obce."""
    out = {}
    for reg, origin in [('m12-03', 'm09-04'), ('m09-07', 'm10-04'), ('m09-08', 'm09-05'), ('m09-06', 'm07-06')]:
        st_ = [g for g in r.home if r.region(g) == reg and '+' in g and origin in g]
        rows = []
        for g in st_:
            mother = r.villages(origin)
            d = mean([r.dist(g, m)[1] for m in mother if r.G[m]['code_language'] == r.G[g]['code_language']])
            rows.append((g.split('+')[1], r.G[g]['code_language'], r.G[g]['population'], round(d, 3)))
        out[reg] = rows
    return out

def era5(r):
    """Istren: kořeny od dělníků v talmurském jádru; výslovnost proti Istrenu; slepé údolí."""
    core = r.villages('m05-04', 'talmur') + r.villages('m05-05', 'talmur') + r.villages('m05-06', 'talmur')
    istren = max(r.villages('m05-04', 'talmur'), key=lambda g: r.G[g]['population'])
    lake = [g for reg in ('m05-01', 'm05-02', 'm05-03') for g in r.villages(reg, 'talmur')]
    blind = r.villages('m06-08', 'talmur')
    return {'seren+veret kořeny v jádru': round(mean([r.loan_share(g, 'seren') + r.loan_share(g, 'veret') for g in core]), 3),
            'hlásk. vzdál. jezerních obcí od Istrenu': round(mean([r.dist(g, istren)[1] for g in lake]), 3),
            'slepé údolí m06-08 (jazyk, lidí, vzdál. od Istrenu)': [(r.G[g]['code_language'], r.G[g]['population'], round(r.dist(g, istren)[1], 3)) for g in blind]}

def summary(r):
    langs = [[g for g in gs if g in set(r.home)] for gs in r.o['snapshots'][-1]['languages'].values()]
    langs = [x for x in langs if x]
    return {'jazyků': len(langs), 'jednoskupinových': sum(len(x) == 1 for x in langs),
            'víc regionů': sum(len({r.region(g) for g in x}) > 1 for x in langs)}

def cases(r):
    """Nové study cases: přístavní kreol, posádka na brodu, tvrdá politika a obrození."""
    def langs(reg):
        c=collections.Counter()
        for g in r.home:
            if r.region(g)==reg: c[r.G[g]['code_language']]+=r.G[g]['population']
        return dict(c)
    def loans(reg, donor, lang):
        gs=r.villages(reg, lang)
        return round(mean([r.loan_share(g, donor) for g in gs]),3) if gs else None
    out={}
    out['kreol m12-03/04']={reg:langs(reg) for reg in ('m12-03','m12-04')}
    out['kontrola m12-05/06']={reg:langs(reg) for reg in ('m12-05','m12-06')}
    vg=[g for reg in ('m12-03','m12-04') for g in r.home if r.region(g)==reg and r.G[g]['code_language']=='veret']
    out['idarská slova ve veretštině ostrovů']=round(mean([r.loan_share(g,'idar') for g in vg]),3) if vg else None
    out['talmurská slova m03-06 / m03-07']=(loans('m03-06','talmur','seren'), loans('m03-07','talmur','seren'))
    out['elita m03-06']=[(g,r.G[g]['code_language'],r.G[g]['population']) for g in r.G if g.startswith('m03-06') and ('elite' in g or 'm06-03' in g)]
    out['m05-07 / m05-08 domácí']=(langs('m05-07'), langs('m05-08'))
    return out


if __name__ == '__main__':
    for path in sys.argv[1:]:
        r = Run(path)
        print('====', path, summary(r))
        for name, f in [('I', era1), ('II', era2), ('III', era3), ('IV', era4), ('V', era5), ('study cases', cases)]:
            print(' ', name, f(r))
