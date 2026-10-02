"""Small read-only scanner for decoded save diagnostics, not a game-script evaluator.

Objects retain source spans instead of materializing the entire save as Python
objects. Duplicate keys and anonymous list entries are preserved by entries().
"""
from dataclasses import dataclass
import re

TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[^\s{}="#]+', re.S)
SKIP = re.compile(r'(?:\s+|\#[^\n]*(?:\n|$))*')
BRACES = re.compile(r'"(?:\\.|[^"\\])*"|\#[^\n]*|[{}]', re.S)


def unquote(value):
    return value[1:-1] if value.startswith('"') and value.endswith('"') else value


@dataclass
class Object:
    source: str
    start: int
    end: int

    def entries(self):
        source, pos = self.source, self.start
        while pos < self.end:
            pos = SKIP.match(source, pos, self.end).end()
            if pos >= self.end:
                return
            key = None
            if source[pos] != '{':
                match = TOKEN.match(source, pos, self.end)
                if match is None:
                    raise ValueError(f'Unexpected syntax at {pos}: {source[pos:pos+60]!r}')
                token = match.group()
                pos = SKIP.match(source, match.end(), self.end).end()
                if pos < self.end and (source[pos] == '=' or source.startswith('?=', pos)):
                    key = unquote(token)
                    width = 2 if source.startswith('?=', pos) else 1
                    pos = SKIP.match(source, pos + width, self.end).end()
                else:
                    yield None, unquote(token)
                    continue
            if pos >= self.end:
                raise ValueError('Missing value')
            if source[pos] == '{':
                start, depth = pos + 1, 1
                for match in BRACES.finditer(source, start, self.end):
                    token = match.group()
                    if token == '{':
                        depth += 1
                    elif token == '}':
                        depth -= 1
                        if depth == 0:
                            yield key, Object(source, start, match.start())
                            pos = match.end()
                            break
                else:
                    raise ValueError('Unclosed object')
            else:
                match = TOKEN.match(source, pos, self.end)
                if match is None:
                    raise ValueError(f'Invalid value at {pos}')
                yield key, unquote(match.group())
                pos = match.end()

    def fields(self):
        result = {}
        for key, value in self.entries():
            if key is not None:
                if key in result:
                    raise ValueError(f'Duplicate key {key!r}; use entries() instead')
                result[key] = value
        return result

    def text(self):
        return self.source[self.start:self.end]


def root(source):
    # Rakaly preserves the SAV container header as a first line.
    start = source.index('\n') + 1 if source.startswith('SAV') else 0
    return Object(source, start, len(source))
