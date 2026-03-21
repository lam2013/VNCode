
import re
from typing import List, Tuple, Optional, NamedTuple, Set

class Token(NamedTuple):
    type: str
    value: str
    start: int
    end: int

KEYWORDS = {
    'if', 'else', 'for', 'while', 'def', 'return', 'class', 'import', 'from', 'as',
    'True', 'False', 'None', 'print', 'and', 'or', 'not', 'in', 'is', 'lambda'
}

TOKEN_PATTERNS = [
    (r'[ \t]+',                 'space'),
    (r'\n',                     'newline'),
    (r'#.*',                    'comment'),
    (r'\b(?:' + '|'.join(re.escape(k) for k in KEYWORDS) + r')\b', 'keyword'),
    (r'[a-zA-Z_][a-zA-Z0-9_]*', 'identifier'),
    (r'\d+(?:\.\d*)?(?:[eE][+-]?\d+)?', 'number'),
    (r'"(?:[^"\\]|\\.)*"',      'string'),
    (r"'(?:[^'\\]|\\.)*'",      'string'),
    (r'\.',                     'dot'),
    (r'[+\-*/%=&|!<>^]',        'operator'),
    (r'[(){}\[\],:;]',          'punct'),
    (r'.',                      'unknown'),
]

C_CPP_VARIBLE_SYNTAX = ["int", "float", "char", "bool", "void"]

TOKEN_REGEX = [(re.compile(pat), typ) for pat, typ in TOKEN_PATTERNS]

def tokenize(text: str) -> List[Token]:
    tokens: List[Token] = []
    pos = 0
    while pos < len(text):
        matched = False
        for regex, typ in TOKEN_REGEX:
            m = regex.match(text, pos)
            if m:
                value = m.group(0)
                tokens.append(Token(typ, value, pos, pos + len(value)))
                pos += len(value)
                matched = True
                break
        if not matched:
            tokens.append(Token('unknown', text[pos], pos, pos + 1))
            pos += 1
    return tokens

def get_context_at_position(text: str, cursor_pos: int) -> Tuple[Optional[Token], str, List[Token]]:
    tokens = tokenize(text)
    prev_token: Optional[Token] = None
    current_prefix = ""
    recent_tokens: List[Token] = []

    for tok in tokens:
        if tok.end <= cursor_pos:
            prev_token = tok
            recent_tokens.append(tok)
            if len(recent_tokens) > 8:
                recent_tokens.pop(0)
        elif tok.start < cursor_pos < tok.end:
            current_prefix = text[tok.start:cursor_pos]
            if recent_tokens:
                prev_token = recent_tokens[-1]
            break
        else:
            break

    if prev_token is None and recent_tokens:
        prev_token = recent_tokens[-1]

    return prev_token, current_prefix, recent_tokens[-5:]

def get_suggestions(
    text: str,
    cursor_pos: int,
    variables: Set[str],
    functions: Set[str] = None,
) -> List[str]:
    if functions is None:
        functions = set()

    prev_token, prefix, recent = get_context_at_position(text, cursor_pos)

    suggestions = set()

    if prev_token and prev_token.type == 'dot':
        if len(recent) >= 2 and recent[-2].type == 'identifier':
            obj_name = recent[-2].value
            fake_attrs = {
                'print': ['__call__', 'args'],
                'list': ['append', 'pop', 'remove', 'clear', 'extend'],
                'str': ['upper', 'lower', 'strip', 'split', 'replace'],
                'dict': ['get', 'keys', 'values', 'items'],
            }.get(obj_name, [])
            for a in fake_attrs:
                if a.startswith(prefix):
                    suggestions.add(a)

    else:
        for k in KEYWORDS:
            if k.startswith(prefix):
                suggestions.add(k)
        for v in variables:
            if v.startswith(prefix):
                suggestions.add(v)
        for f in functions:
            if f.startswith(prefix):
                suggestions.add(f)

    return sorted(suggestions)