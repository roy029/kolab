import sys
import collections
import pegtree as pg
from pegtree.visitor import ParseTreeVisitor
import random
# from . import verb
import verb

# オプション

OPTION = {
    '--random': True,
    '--single': False, # ひとつしか選ばない (DAはオフ)
    '--order': False, # 順序も入れ替える
    '--short': False # 短い類義語を選ぶ
}

def verb_emit(base, vpos=None, mode=0):
    if vpos is None:
        base, vpos, mode = verb_parse(base)
    return verb.emit_impl(base, vpos, mode)

def verb_parse(s):
    vpos, base, prefix = verb.detect_vpos(s)
    if vpos is not None:
        mode = verb.detect_mode(s[len(prefix):])
        print(s, '=>', verb_emit(prefix+base, vpos, mode))
        return prefix+base, vpos, mode
    return s, None, None

EMPTY = tuple()
DEBUG = False


# 異音同義語

def filter_synonym_annotation(s):
        return s.split('@')[0] if '@' in s else s

def decode_synonyms(value):
    values = []
    for s in value.split('|'):
        if '@' in s:
            s, n = s.split('@')
            for i in range(int(n)):
                values.append(s)
        else:
            values.append(s)
    return values

def encode_synonyms(values):
    count = collections.Counter(values)
    a=[]
    for key in count.keys():
        a.append(f'{key}@{count[key]}')
    return '|'.join(a)

def update_synonyms(synonyms, key, value):
    values = decode_synonyms(value) 
    if key in synonyms:
        values.extend(decode_synonyms(synonyms[key]))
    key2 = filter_synonym_annotation(key)
    if key2 not in values:
        values.append(key2)
    synonyms[key] = encode_synonyms(values)

RandomIndex = 0

def randomize():
    global RandomIndex
    if OPTION['--random']:
        RandomIndex = random.randint(1, 1789)
    else:
        RandomIndex = 0


def random_index(arraysize: int, seed):
    if OPTION['--random']:
        return (RandomIndex + seed) % arraysize
    return 0

def choice(ss: list):
    return ss[random_index(len(ss), 17)]


def alt(s: str):
    if '|' in s:
        ss = decode_synonyms(s)
        if OPTION['--random']:
            return choice(ss)
        if OPTION['--short']:
            ss.sort(key=lambda x: len(x))
            return ss[0]
        return ss[0]
    return s

# NExpr

def identity(e):
    return e

class NExpr(object):
    subs: tuple
    def __init__(self, subs=EMPTY):
        self.subs = tuple(NWord(s) if isinstance(s, str) else s for s in subs)

    def apply(self, dict_or_func=identity):
        if len(self.subs) > 0:
            (e.apply(dict_or_func) for e in self.subs)
        return self

    def src(self):
        '''
        Tokibi形式で再出力する
        '''
        buffers = []
        self.emit_src(buffers)
        s = ''.join(buffers)
        return s

    def emit_src(self, buffers):
        buffers.append(str(self))

    def generate(self):
        ss = []
        c = 0
        while c < 5:
            randomize()
            buffers = []
            self.emit(buffers)
            s = ''.join(buffers)
            if s not in ss:
                ss.append(s)
            else:
                c += 1
        if OPTION['--single'] and len(ss) > 0:
            ss = [ss[0]]
        return ss

class NWord(NExpr):
    w: str

    def __init__(self, w):
        NExpr.__init__(self)
        self.w = str(w)

    def __repr__(self):
        # if DEBUG:
        #     return f'NWord({self.w})'
        if '|' in self.w:
            return '[' + self.w + ']'
        return self.w

    def apply(self, dict_or_func=identity):
        if not isinstance(dict_or_func, dict):
            return dict_or_func(self)
        return self

    def emit(self, buffers):
        buffers.append(alt(self.w))

class NVerb(NExpr):
    w: str
    vpos: str
    mode: int
    synonym: str

    def __init__(self, w, mode=0, synonym=None):
        NExpr.__init__(self)
        self.w = str(w)
        self.mode = mode
        self.synonym = synonym

    def __repr__(self):
        if DEBUG:
            return f'NVerb({self.w},{self.mode})'
        mode = self.mode
        if self.synonym is not None:
            w = '|'.join([verb_emit(w, mode) for w in self.synonym.split('|')])
            return f'[{w}]'
        return verb_emit(self.w, mode)

    def apply(self, dict_or_func=identity):
        if not isinstance(dict_or_func, dict):
            return dict_or_func(self)
        return self

    def emit(self, buffers):
        w = self.w
        mode = self.mode
        if self.synonym is not None:
            w = alt(self.synonym)
        buffers.append(verb_emit(w, self.mode))


class NChoice(NExpr):
    def __init__(self, *subs):
        NExpr.__init__(self, subs)

    def __repr__(self):
        if DEBUG:
            return f'NChoice{repr(self.subs)}'
        ss = []
        for p in self.subs:
            ss.append(repr(p))
        return '{' + '|'.join(ss) + '}'

    def apply(self, dict_or_func=identity):
        return NChoice(*(e.apply(dict_or_func) for e in self.subs))

    def emit(self, buffers):
        choice(self.subs).emit(buffers)

class NPhrase(NExpr):
    def __init__(self, *subs):
        NExpr.__init__(self, subs)

    def __repr__(self):
        if DEBUG:
            return f'NPhrase{repr(self.subs)}'
        ss = []
        for p in self.subs:
            ss.append(grouping(p))
        return ' '.join(ss)

    def apply(self, dict_or_func=identity):
        # if isinstance(dict_or_func, dict):
        #     print('@debug', dict_or_func)
        return NPhrase(*(e.apply(dict_or_func) for e in self.subs))

    def emit(self, buffers):
        for p in self.subs:
            p.emit(buffers)

def grouping(e):
    if isinstance(e, NPhrase):
        return '{' + repr(e) + '}'
    return repr(e)

class NOrdered(NExpr):
    def __init__(self, *subs):
        NExpr.__init__(self, subs)

    def __repr__(self):
        if DEBUG:
            return f'NOrdered{repr(self.subs)}'
        ss = []
        for p in self.subs:
            ss.append(grouping(p))
        return '/'.join(ss)

    def apply(self, dict_or_func=identity):
        return NOrdered(*(e.apply(dict_or_func) for e in self.subs))

    def emit(self, buffers):
        subs = list(self.subs)
        if OPTION['--order']:
            random.shuffle(subs)
        for p in subs:
            p.emit(buffers)


class NClause(NExpr):  # 名詞節　〜する(verb)＋名詞(noun)

    def __init__(self, verb, noun):
        NExpr.__init__(self, (verb,noun))

    def __repr__(self):
        if DEBUG:
            return f'NClause{repr(self.subs)}'
        return grouping(self.subs[0]) + grouping(self.subs[1])

    def apply(self, dict_or_func=identity):
        return NClause(*(e.apply(dict_or_func) for e in self.subs))

    def emit(self, buffers):
        verb = self.subs[0]
        noun = self.subs[1]
        verb.emit(buffers)
        noun.emit(buffers)

class NSuffix(NExpr):
    suffix: str

    def __init__(self, *ws):
        NExpr.__init__(self, ws[:-1])
        self.suffix = str(ws[-1])

    def __repr__(self):
        if DEBUG:
            return f'NSuffix({repr(self.subs[-1])},{repr(self.suffix)})'
        return ''.join(grouping(t) for t in self.subs) + self.suffix

    def apply(self, dict_or_func=identity):
        return NSuffix(*(e.apply(dict_or_func) for e in self.subs), self.suffix)

    def emit(self, buffers):
        for p in self.subs:
            p.emit(buffers)
        buffers.append(self.suffix)

class NLiteral(NExpr):
    w: str

    def __init__(self, w):
        NExpr.__init__(self)
        self.w = str(w)

    def __repr__(self):
        if DEBUG:
            return f'NLiteral({repr(self.w)})'
        return self.w

    def apply(self, dict_or_func=identity):
        if not isinstance(dict_or_func):
            return dict_or_func(self)

    def emit(self, buffers):
        buffers.append(self.w)


class NSymbol(NExpr):
    index: int
    w: str

    def __init__(self, index, w):
        NExpr.__init__(self)
        self.index = index
        self.w = str(w)
    
    def __repr__(self):
        if DEBUG:
            return f'NSymbol({self.w})'
        return self.w

    def apply(self, dict_or_func=identity):
        if isinstance(dict_or_func, dict):
            mapped = self
            if self.index in dict_or_func:
                mapped = dict_or_func[self.index]
            elif self.w in dict_or_func:
                mapped = dict_or_func[self.w]
            if not isinstance(mapped, NExpr):
                mapped = NWord(str(mapped))
            return mapped
        else:
            return dict_or_func(self)

    def emit(self, buffers):
        buffers.append(self.w)

class NParam(NExpr):
    unit: str
    def __init__(self, x, unit):
        NExpr.__init__(self, (x,))
        self.unit = unit

    def __repr__(self):
        if DEBUG:
            return f'NParam({repr(self.subs[0])},{repr(self.unit)})'
        return grouping(self.subs[0]) + f'({self.unit})'

    def apply(self, dict_or_func=identity):
        return NParam(self.subs[0].apply(dict_or_func), self.unit)

    def emit(self, buffers):
        inner = self.subs[0]
        if isinstance(inner, NSymbol):
            if len(buffers) == 0: # prefixをつける
                buffers.append(alt(self.unit+'|'))
                inner.emit(buffers)
            else:
                inner.emit(buffers)
        else:
            inner.emit(buffers)


peg = pg.grammar('tokibi.pegtree')
tokibi_parser = pg.generate(peg)

class TokibiReader(ParseTreeVisitor):

    def __init__(self, synonyms=None):
        ParseTreeVisitor.__init__(self)
        self.indexes = {}
        self.synonyms = {} if synonyms is None else synonyms

    def parse(self, s):
        tree = tokibi_parser(s)
        self.indexes = {}
        nexpr = self.visit(tree)
        return nexpr, self.indexes

    def accepterr(self, tree):
        print(str(tree), file=sys.stderr)
        raise RuntimeError()

# [#NPhrase [#NOrdered [#NSuffix [#NSymbol 'str'][# 'が']][#NSuffix [#NSymbol 'prefix'][# 'で']]][#NWord '始まるかどうか']]

    def acceptNChoice(self, tree):
        ne = NChoice(*(self.visit(t) for t in tree))
        return ne

    def acceptNPhrase(self, tree):
        ne = NPhrase(*(self.visit(t) for t in tree))
        if len(ne.subs) == 1:
            return ne.subs[0]
        return ne

    def acceptNClause(self, tree):
        ne = NClause(self.visit(tree[0]), self.visit(tree[1]))
        return ne

    def acceptNParam(self, tree):
        ne = NParam(self.visit(tree[0]), str(tree[1]))
        return ne

    def acceptNOrdered(self, tree):
        ne = NOrdered(*(self.visit(t) for t in tree))
        return ne

    def acceptNSuffix(self, tree):
        ws = [self.visit(t) for t in tree[:-1]] + [str(tree[-1])]
        return NSuffix(*ws)

    def acceptNSymbol(self, tree):
        s = str(tree)
        if s not in self.indexes:
            self.indexes[s] = len(self.indexes)
        return NSymbol(self.indexes[s], s)

    def acceptNLiteral(self, tree):
        s = str(tree)
        return NLiteral(s)

    def acceptNWord(self, tree):
        s = str(tree)
        if '|' in s:
            return NWord(s)
        if s in self.synonyms:
            return NWord(self.synonyms[s])
        return NWord(s)

    def acceptNPiece(self, tree):
        s = str(tree)
        return NWord(s)

tokibi_reader = TokibiReader()

def parse2(s, synonyms=None):
    if synonyms is not None:
        tokibi_reader.synonyms = synonyms
    if s.endswith('かどうか'):
        s = s[:-4]
        e, d = tokibi_reader.parse(s)
        e = NClause(e, NWord('かどうか'))
    else:
        e, d = tokibi_reader.parse(s)
    #print(grouping(e[0]))
    return e, d

def parse(s, synonyms=None):
    return parse2(s, synonyms=synonyms)[0]

def test_parse(s, synonyms=None):
    e = parse(s, synonyms=synonyms)
    e2 = parse(e.src().replace(' ', ''), synonyms=synonyms)
    if e.src() != e2.src():
        print(e2.src())
    return e2

def read_terakoya(filename, data=None):
    if data is None:
        data = []
    with open(filename) as f:
        code = None
        desc = []
        for line in f.readlines():
            line = line.strip()
            if line.startswith('#'):
                continue
            if line == '':
                if code is not None:
                    data.append((code, tuple(desc)))
                code = None
                desc = []
                continue
            if code is None:
                code = line
            else:
                desc.append(line)
        if code is not None:
            data.append((code, tuple(desc)))
    return data

def write_tsv(dataset, file=sys.stdout):
    for code, desc in dataset:
        for d in desc:
            for doc in parse(d).generate():
                print(f'{doc}\t{code}')

if __name__ == '__main__':
    if len(sys.argv) > 1:
        for filename in sys.argv[1:]:
            dataset=[]
            read_terakoya(filename, dataset)
            write_tsv(dataset)
    else:
        # e = parse('{xを/{functionを 適用して}フィルタした}リスト')
        # print(e.src())
        # e = parse('{心が折れた|気持ちが和らぐ}かも知れない')
        # print(e.src())
        # xがy内に
        e = test_parse('xをy個まで購入する')
        print(e.src())


