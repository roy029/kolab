
import sys
import random
from pegtree.visitor import ParseTreeVisitor
from pegtree import ParseTree
import pegtree as pg

from pj import lemma, Lemma

from logging import getLogger
logger = getLogger(__name__)

EMPTY = tuple()

# オプション

ReversePolish = True  # 膠着語の場合はTrue
EnglishFirst = True
RandomIndex = 0
ShuffleSynonym = True  # NChoiceの表現をシャッフルする
MultipleSentence = True  # 複数行モード
ShuffleOrder = True  # まだ未実装

VERBOSE = True  # デバッグ用出力


def randomize():
    global RandomIndex
    if ShuffleSynonym:
        RandomIndex = random.randint(1, 1789)


def random_index(arraysize: int, seed):
    return (RandomIndex + seed) % arraysize


def alt(s: str):
    if '|' in s:
        ss = s.split('|')
        if EnglishFirst:
            return ss[-1]  # 最後が英語
        return ss[random_index(len(ss), len(s))]
    return s


def shuffle(x, y):
    if ShuffleSynonym:
        return x if random.random() < 0.6 else y
    return x

# 自然言語フレーズ


RESULT = 'P結果'
EOS = 'E。'


class NExpr(object):

    def asType(self, typefix):
        return self

    def apply(self, mapped):
        return self

    def __repr__(self):
        return str(self)


class NChoice(NExpr):
    choices: tuple

    def __init__(self, *choices):
        self.choices = choices

    def asType(self, typefix):
        return NChoice(*[c.asType(typefix) for c in self.choices])

    def apply(self, mapped):
        return NChoice(*[c.apply(mapped) for c in self.choices])

    def __str__(self):
        return '[' + '|'.join(map(str, self.choices)) + ']'

    def emit(self, typefix, buffer=None):
        if ShuffleSynonym:
            index = random.randrange(0, len(self.choices))
            return self.choices[index].emit(typefix, buffer)
        return self.choices[0].emit(typefix, buffer)


class NPiece(NExpr):
    piece: str

    def __init__(self, piece):
        self.piece = piece

    def asType(self, typefix):
        return NPred(self.piece, typefix)

    def __str__(self):
        return self.piece

    def emit(self, typefix, buffer=None):
        return self.piece


class NPred(NExpr):
    lemma: Lemma
    typefix: str

    def __init__(self, verb, typefix=''):
        self.lemma = lemma(verb)
        self.typefix = typefix

    def asType(self, typefix):
        self.typefix = typefix
        return self

    def __str__(self):
        if self.typefix == '':
            return str(self.lemma)
        return f'{self.lemma} as {self.typefix}'

    def emit0(self, typefix, buffer=None):
        if typefix != EOS and self.lemma.lemmatype == 'N':
            return str(self.lemma)
        if typefix == EOS:
            return self.lemma.emit(typefix)
        if len(self.typefix)+1 > len(typefix):
            typefix = typefix[0] + alt(self.typefix)
        return self.lemma.emit(typefix)

    def emit(self, typefix, buffer=None):
        s = self.emit(typefix, buffer)
        print(self.lemma, typefix, s)
        return s


class NLiteral(NExpr):
    value: str
    ret: str

    def __init__(self, value: str, ret=None):
        self.value = value
        if ret is None:
            if value.startswith('"') or value.startswith("'"):
                ret = 'str'
            elif value.isdigit():
                ret = 'int'
        self.ret = ret

    def __str__(self):
        return self.value

    def emit(self, typefix, buffer=None):
        if not typefix.startswith('P') or typefix == RESULT:
            return self.value
        prefix = typefix[1:]
        if prefix in ['結果', '値']:
            return self.value
        return f'{prefix} {self.value}'


class NParam(NExpr):
    symbol: str
    index: int
    typefix: str
    bound: NExpr

    def __init__(self, symbol, index, typefix='', bound=None):
        self.symbol = symbol
        self.index = index
        self.typefix = typefix
        self.bound = bound

    def apply(self, mapped):
        if self.index in mapped:
            bound = mapped[self.index]
            return NParam(self.symbol, self.index, self.typefix, bound)
        return self

    def __str__(self):
        return ALPHA[self.index]

    def emit(self, typefix, buffer=None):
        if self.bound is None:
            return self.symbol
        typefix = RESULT if self.typefix == '' else 'P' + self.typefix
        return self.bound.emit(typefix, buffer)


def toNExpr(e):
    if isinstance(e, NExpr):
        return e
    if isinstance(e, CValue):
        return NLiteral(e.value)
    return NPiece(str(e))


def NChunk(NExpr):
    pieces: tuple
    suffix: str

    def __init__(self, *pieces):
        self.pieces = [toNExpr(p) for p in pieces[:-1]]
        self.suffix = str(pieces[-1])

    def apply(self, mapped):
        pieces = [e.apply(mapped) for e in self.pieces]
        pieces.append(suffix)
        return NChunk(*pieces)

    def __str__(self):
        ss = []
        for p in self.pieces:
            ss.append(str(p))
        ss.append(self.suffix)
        return ' '.join(ss)

    def emit(self, typefix, buffer=None):
        ss = []
        for p in self.pieces:
            ss.append(p.emit(typefix, buffer))
        ss.append(self.suffix)
        return ' '.join(ss)


class NPhrase(NExpr):
    pieces: tuple
    options: tuple
    ret: str  # 返り値の種類

    def __init__(self, *pieces):
        self.pieces = [toNExpr(p) for p in pieces]
        self.options = EMPTY
        self.ret = None

    def asType(self, ret):
        self.ret = ret
        return self

    def apply(self, mapped):
        pred = NPhrase(*[e.apply(mapped) for e in self.pieces])
        pred.options = mapped.get('options', EMPTY)
        pred.ret = self.ret
        return pred

    def __str__(self):
        ss = []
        for p in self.pieces:
            ss.append(str(p))
        return ' '.join(ss)

    def emit(self, typefix, buffer=None):
        ss = []
        if len(self.options) > 2 and ShuffleOrder:
            os = list(self.options)
            random.shuffle(os)
            self.options = tuple(os)

        for p in self.options:
            if buffer is None:
                ss.append(p.emit(shuffle('T、', 'A、')))
            else:
                buffer.append(p.emit('E。'))

        for p in self.pieces:
            ss.append(p.emit(typefix, buffer))
        return ' '.join(ss)


# コード表現

ALPHA = [chr(c) for c in range(ord('A'), ord('Z')+1)] + ['?']

STATIC_MODULE = {
    'math', 'pd', 'sys', 'os'
}


def toCExpr(value):
    return value if isinstance(value, CExpr) else CValue(value)


class CExpr(object):  # Code Expression
    name: str
    params: tuple

    def __init__(self, name='', params=EMPTY):
        self.name = name
        self.params = params
        self.options = EMPTY

    def format(self, option=True):
        return f'undefined({self.__class__.__name__})'

    def __repr__(self):
        return self.format().format(*(self.params+self.options))

    def __lt__(self, a):
        return id(self) < id(a)

    def __len__(self):
        return len(self.params)

    def __getitem__(self, index):
        return self.params[index]

    def getoption(self, name):
        for option in self.options:
            if name == option.name:
                return option
        return None


class CMetaVar(CExpr):
    index: int
    original_name: str

    def __init__(self, index: int, original_name: str):
        CExpr.__init__(self)
        self.index = index
        self.original_name = original_name

    def format(self, option=True):
        return repr(self)

    def __repr__(self):
        return ALPHA[self.index]


class CValue(CExpr):
    value: object

    def __init__(self, value):
        CExpr.__init__(self)
        self.value = value

    def __repr__(self):
        if isinstance(self.value, str):
            return repr(self.value)  # FIXME
        return str(self.value)

    def format(self, option=True):
        return repr(self)


class CVar(CExpr):

    def __init__(self, name):
        CExpr.__init__(self, name)

    def format(self, option=True):
        return self.name

    def __repr__(self):
        return self.name


class CBinary(CExpr):

    def __init__(self, left, op, right):
        CExpr.__init__(self, op, (toCExpr(left), toCExpr(right)))

    def format(self, option=True):
        return f'{{}} {self.name} {{}}'


class CUnary(CExpr):

    def __init__(self, op, expr):
        CExpr.__init__(self, op, (toCExpr(expr),))

    def format(self, option=True):
        return f'{self.name} {{}}'


class COption(CExpr):

    def __init__(self, name: str, value: CExpr):
        CExpr.__init__(self, name, (toCExpr(value),))

    def format(self, option=True):
        return f'{self.name} = {{}}'


class CApp(CExpr):

    def __init__(self, name: str, *es):
        CExpr.__init__(self, name, tuple(toCExpr(e)
                                         for e in es if not isinstance(e, COption)))
        if len(es) != len(self.params):
            self.options = tuple(toCExpr(e)
                                 for e in es if isinstance(e, COption))

    def format(self, option=True):
        ss = []
        ss.append(self.name)
        ss.append('(')
        n = len(self.params)+len(self.options)
        if n > 0:
            ps = [',', '{}'] * (n)
            ss.extend(ps[1:])
        ss.append(')')
        return ' '.join(ss)


class OOP(object):
    pass


class CMethod(CExpr, OOP):

    def __init__(self, name: str, *es):
        CExpr.__init__(self, name, tuple(toCExpr(e)
                                         for e in es if not isinstance(e, COption)))
        if len(es) != len(self.params):
            self.options = tuple(toCExpr(e)
                                 for e in es if isinstance(e, COption))

    def format(self, option=True):
        ss = ['{}', '.']
        ss.append(self.name)
        ss.append('(')
        n = len(self.params)+len(self.options)
        if n > 1:
            ps = [',', '{}'] * (n-1)
            ss.extend(ps[1:])
        ss.append(')')
        return ' '.join(ss)


class CField(CExpr, OOP):

    def __init__(self, recv: CExpr, name: str):
        CExpr.__init__(self, name, (toCExpr(recv),))

    def format(self, option=True):
        return f'{{}} . {self.name}'


class CTuple(CExpr):

    def __init__(self, *es):
        CExpr.__init__(self, "(,)", tuple(toCExpr(e) for e in es))

    def format(self, option=True):
        ss = []
        ss.append('(')
        n = len(self.params)
        if n == 1:
            ss.extend(['{}', ','])
        else:
            ps = [',', '{}'] * (n)
            ss.extend(ps[1:])
        ss.append(')')
        return ' '.join(ss)


class CList(CExpr):

    def __init__(self, *es):
        CExpr.__init__(self, "[,]", tuple(toCExpr(e) for e in es))

    def format(self, option=True):
        ss = []
        ss.append('[')
        n = len(self.params)
        if n > 0:
            ps = [',', '{}'] * (n)
            ss.extend(ps[1:])
        ss.append(']')
        return ' '.join(ss)


class CData(CExpr):

    def __init__(self, *es):
        CExpr.__init__(self, "{,}", tuple(toCExpr(e) for e in es))

    def format(self, option=True):
        ss = []
        ss.append('{')
        for i in range(0, len(self.params), 2):
            ss.extend(['{}', '=', '{}', ','])
        ss.append('}')
        return ' '.join(ss)


class CIndex(CExpr, OOP):

    def __init__(self, recv, index):
        CExpr.__init__(self, "[]", (toCExpr(recv), toCExpr(index)))

    def format(self, option=True):
        return f'{{}} [ {{}} ]'


class CEmpty(CExpr, OOP):

    def __init__(self):
        CExpr.__init__(self, "")

    def format(self, option=True):
        return ''


CEMPTY = CEmpty()


class CSlice(CExpr):

    def __init__(self, recv, start=CEMPTY, stop=CEMPTY, step=CEMPTY):
        CExpr.__init__(self, "[]", (toCExpr(recv),
                                    toCExpr(start),  toCExpr(stop), toCExpr(step)))

    def format(self, option=True):
        return f'{{}} [ {{}} : {{}} : {{}}]'


##
peg = pg.grammar('kotoha.tpeg')
parser = pg.generate(peg)
eparser = pg.generate(peg, start='Snipet')


def symbols(tree):
    ss = []
    for _, child in tree.subs():
        tag = child.getTag()
        if tag == 'Name' or tag == 'Symbol':
            ss.append(str(child))
        if tag == 'Param':
            ss.append(str(child[0]))
    return ss


class Reader(ParseTreeVisitor):
    rules: dict
    indexes: dict
    newnames: set

    def __init__(self, rules):
        ParseTreeVisitor.__init__(self)
        self.rules = rules
        self.symbols = EMPTY
        self.names = {
            's': '文字列', 'c': '文字',
            'n': '整数', 'f': 'ファイル',
        }
        self.modules = STATIC_MODULE
        self.synonyms = {}
        self.newnames = set()

    def isRuleMode(self):
        return self.symbols is not EMPTY

    def acceptSource(self, tree):
        for t in tree:
            self.visit(t)

    def acceptRule(self, tree):
        code = tree[0]
        doc = tree[1]
        self.symbols = set(symbols(doc))
        self.indexes = {}
        cpat = self.visit(code)
        if str(doc).strip() == 'symbol':
            name = cpat.name
            symbol = str(cpat.params[0])[1:-1]
            self.names[name] = symbol
            return
        if str(doc).strip() == 'module':
            name = cpat.name
            self.modules.add(name)
            return
        pred = self.visit(doc)
        self.add_rule(cpat, len(self.indexes), pred)
        self.symbols = EMPTY

    def add_rule(self, cpat: CExpr, size, pred: NExpr):
        name = cpat.name
        assert name != ''
        if len(cpat.params) > 0 and isinstance(cpat.params[0], CMetaVar):
            ns = cpat.params[0].original_name
            if len(ns) > 1:
                lname = f'{ns}.{name}'
                if lname not in self.rules:
                    self.rules[lname] = []
                self.rules[lname].append((size, cpat, pred))
                if name not in self.rules or ns in self.newnames:
                    self.newnames.add(ns)
                else:
                    # print(f'{lname}のみ登録', cpat, pred)
                    return
        if name not in self.rules:
            self.rules[name] = []
        self.rules[name].append((size, cpat, pred))

    def acceptSymbolDef(self, tree):
        cpat = self.visit(tree[0])
        name = cpat.name
        symbol = str(cpat.params[0])[1:-1]
        self.names[name] = symbol

    def acceptModuleDef(self, tree):
        name = str(tree[0])
        self.modules.add(name)

    def acceptExample(self, tree):
        ce = self.visit(tree[0])
        print('Example', ce)

    def acceptAssignment(self, tree):
        left = self.visit(tree.left)  # xをyとする
        right = self.visit(tree.right)
        return CBinary(left, '=', right)

    def acceptSelfAssignment(self, tree):
        name = str(tree.name)
        left = self.visit(tree.left)
        right = self.visit(tree.right)
        return CBinary(left, name, right)

    def acceptInfix(self, tree):
        name = str(tree.name)
        left = self.visit(tree.left)
        right = self.visit(tree.right)
        return CBinary(left, name, right)

    def acceptUnary(self, tree):
        name = str(tree.name)
        expr = self.visit(tree.expr)
        return CUnary(name, expr)

    def acceptApplyExpr(self, tree):
        name = str(tree.name)
        params = self.visit(tree.params)
        return CApp(name, *params)

    def acceptArguments(self, tree):
        return [self.visit(e) for e in tree]

    def acceptOption(self, tree):
        value = self.visit(tree[1])
        return COption(str(tree[0]), value)

    def acceptMethodExpr(self, tree):
        recv = self.visit(tree.recv)
        name = str(tree.name)
        params = self.visit(tree.params)
        if self.isRuleMode() and isinstance(recv, CVar):
            if recv.name.startswith('_'):
                return CApp(recv.name[1:] + '.' + name, *params)
            if recv.name in self.modules:
                return CApp(recv.name + '.' + name, *params)
        return CMethod(name, *([recv]+params))

    def acceptGetExpr(self, tree):
        recv = self.visit(tree.recv)
        name = str(tree.name)
        if self.isRuleMode() and isinstance(recv, CVar):
            if recv.name.startswith('_'):
                recv.name = recv.name[1:] + '.' + name
                return recv
            if recv.name in self.modules or '.' in recv.name:
                recv.name += '.' + name
                return recv
        return CField(recv, name)  # Fixme

    def acceptIndexExpr(self, tree):
        recv = self.visit(tree.recv)
        index = self.visit(tree.index)
        return CIndex(recv, index)  # Fixme

    def acceptName(self, tree):
        s = str(tree)
        if self.isRuleMode():
            if s in self.symbols:
                if s not in self.indexes:
                    self.indexes[s] = len(self.indexes)
                return CMetaVar(self.indexes[s], s)
        return CVar(s)

    def acceptString(self, tree):
        s = str(tree)
        if s.startswith("'") and s.endswith("'"):
            s = s[1:-1].encode('unicode-escape').decode('unicode-escape')
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1].encode('unicode-escape').decode('unicode-escape')
        return CValue(s)

    def acceptInt(self, tree):
        s = str(tree)
        return CValue(int(s))

    def acceptDouble(self, tree):
        s = str(tree)
        return CValue(float(s))

    def acceptTrueExpr(self, tree):
        return CValue(True)

    def acceptFalseExpr(self, tree):
        return CValue(False)

    def acceptNull(self, tree):
        return CValue(None)

    def acceptList(self, tree):
        es = [self.visit(t) for t in tree]
        return CList(*es)

    def acceptTuple(self, tree):
        es = [self.visit(t) for t in tree]
        return CTuple(*es)

    def acceptList(self, tree):
        es = [self.visit(t) for t in tree]
        return CList(*es)

    def acceptUndefined(self, tree):
        logger.warning(f'@undefined {repr(tree)}')
        s = str(tree)
        return CValue(s)

    def acceptMetaData(self, tree):
        lines = str(tree).split('\n')
        for line in lines:
            ss = line.split()
            if len(ss) > 2:
                # print('#' + ss[1], ss[1:]) #, self.synonyms[ss[1]])
                self.synonyms[ss[1]] = tuple(lemma(t) for t in ss[1:])

    def acceptDocument(self, tree):
        ret = ''
        ss = []
        for t in tree:
            if t.getTag() == 'Return':
                ret = str(t).strip()
            else:
                ss.append(self.visit(t))
        if ret != '' and ret in self.names:
            typefix = self.names[ret]
            if ReversePolish:
                ss[-1] = ss[-1].asType(typefix)
            else:
                ss[0] = ss[0].asType(typefix)
        e = NPhrase(*ss)
        if ret != '':
            e.ret = ret
        return e

    def acceptSymbol(self, tree):
        s = str(tree)
        if s in self.indexes:
            p = NParam(s, self.indexes[s])
            if s[-1].isdigit():
                s = s[:-1]
            if s in self.names:
                p.typefix = alt(self.names[s])
            return p
        return NPiece(s)

    def acceptParam(self, tree):
        piece = self.visit(tree[0])
        typefix = str(tree[1])
        if isinstance(piece, NParam):
            piece.typefix = typefix
            return piece
        return piece

    def acceptSynonyms(self, tree):
        ss = [str(t) for t in tree]
        if len(ss) == 1:
            if ss[0] in self.synonyms:
                ss = [NPiece(str(t)) for t in self.synonyms[ss[0]]]
                return NChoice(*ss)
        return NChoice(*[NPiece(str(t)) for t in ss])

    def acceptLiteral(self, tree):
        symbol = str(tree)
        return NLiteral(symbol)

    def acceptPiece(self, tree):
        s = str(tree)
        if s in self.synonyms:
            ss = [NPiece(str(t)) for t in self.synonyms[s]]
            return NChoice(*ss)
        return NPiece(s)

    def accepterr(self, tree):
        print(repr(tree))
        sys.exit(0)


# Matcher

def cmatch(cpat, code, mapped: dict):
    if cpat.__class__ is not code.__class__:
        return False
    if cpat.name != code.name or len(cpat.params) != len(code.params):
        return False
    for e, e2 in zip(cpat.params, code.params):
        #print(':: ', type(e), e, type(e2), e2)
        if isinstance(e, CMetaVar):
            if e.index in mapped:
                print("#conf", str(mapped[e.index]), str(e2))
                if str(mapped[e.index]) != str(e2):
                    return False
                else:
                    continue
            mapped[e.index] = e2
            continue
        if isinstance(e, CValue) and isinstance(e2, CValue):
            if e.value != e2.value:
                return False
            continue
        if not cmatch(e, e2, mapped):
            return False
    for opat in cpat.options:
        option = code.getoption(opat.name)
        if option is None:
            return False
        if not cmatch(opat, option, mapped):
            return False
    if len(code.options) > 0:
        os = []
        for option in code.options:
            opat = cpat.getoption(option.name)
            if opat is None:
                os.append(option)
        mapped['options'] = os
    return True


def NOption(name, value: NExpr):
    if MultipleSentence:
        return NPhrase(name, 'は', value, 'に', NPred('する'))
    else:
        return NPhrase(name, 'を', value, 'に', NPred('する'))


def stem_name(name: str):
    if name[-1].isdigit():
        return stem_name(name[:-1])
    return name


class KotohaModel(object):
    rules: dict
    reader: Reader
    names: dict

    def __init__(self):
        self.rules = {}
        self.reader = Reader(self.rules)
        self.names = {}

    def load(self, *files):
        for file in files:
            with open(file) as f:
                source = f.read()
                tree = parser(source, urn=file)
                self.reader.visit(tree)
        for key in self.rules:
            d = self.rules[key]
            if len(d) > 1:
                self.rules[key] = sorted(d)
        self.names = self.reader.names

    def match(self, ce: CExpr) -> NExpr:
        name = ce.name
        if len(ce.params) > 0:  # レシーバの型を調べる
            recv = self.match(ce.params[0])
            if hasattr(recv, 'ret') and recv.ret is not None:
                lname = f'{recv.ret}.{name}'
                #print('@レシーバの型', recv.ret, lname)
                if lname in self.rules:
                    name = lname
        while name not in self.rules and '.' in name:
            loc = name.find('.')
            name = name[loc+1:]
        if name in self.rules:
            for _, pat, pred in self.rules[name]:
                mapped = {}
                # print('trying .. ', pat, type(ce), ce)
                if cmatch(pat, ce, mapped):
                    for key in mapped.keys():
                        if key == 'options':
                            mapped[key] = [self.match(e) for e in mapped[key]]
                        else:
                            mapped[key] = self.match(mapped[key])
                    return pred.apply(mapped)
            logger.debug('unmatched: ' + str(ce))
        if len(ce.params) > 0:
            logger.debug('undefined? ' + str(type(ce)) + ' ' + str(ce))
        if isinstance(ce, CVar):
            name = str(ce)
            ret = stem_name(name)
            if ret in self.reader.names:
                return NLiteral(name, ret)
            return NLiteral(name)
        if isinstance(ce, CValue):
            return NLiteral(str(ce))
        if isinstance(ce, COption) and ce.name in self.reader.names:
            name = alt(self.reader.names[ce.name])
            return NOption(name, self.match(ce.params[0]))
        return NPiece(str(ce))

    def translate(self, expression, suffix=''):
        tree = eparser(expression)
        code = self.reader.visit(tree)
        #print(type(code), code)
        pred = self.match(code)
        if MultipleSentence:
            buffer = []
            main = pred.emit(suffix, buffer)
            if len(buffer) > 0:
                main += 'そこで、' + (' '.join(buffer))
            return code, main
        return code, pred.emit(suffix)

    def generate(self, tsvfile, *files):
        with open(tsvfile, 'w') as w:
            for file in files:
                with open(file) as f:
                    for line in f.readlines():
                        line = line.strip()
                        if line == '' or line.startswith('#'):
                            continue
                        code, doc = self.translate(line, suffix=EOS)
                        print(code, '\t', doc, file=w)


if __name__ == '__main__':
    model = KotohaModel()
    argv = sys.argv[1:]
    rule_files = []
    input_files = []
    tsvfile = 'corpus.tsv'
    for s in sys.argv[1:]:
        if s.endswith('.py'):
            if s.endswith('rule.py'):
                rule_files.append(s)
            else:
                input_files.append(s)
        if s.endswith('.tsv'):
            tsvfile = s
        if s.endswith('True') or s.endswith('False'):
            exec(s, globals())
    model.load(*rule_files)
    if len(input_files) > 0:
        model.generate(tsvfile, *input_files)
    else:
        import readline
        while True:
            line = input('Expression >>> ')
            if line == '':
                sys.exit(0)
            code, doc = model.translate(line, suffix=EOS)
            print(code, '\t#', doc)
