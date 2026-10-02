"""Shared display colors for generated and reusable religion definitions."""
import json
import re
from pathlib import Path

POLICY = Path(__file__).resolve().parents[1]/'config/personal/religion_palette.json'


def color(source):
    value = json.loads(POLICY.read_text(encoding='utf-8-sig'))['colors'].get(source)
    if value is None:
        return None
    if not re.fullmatch(r'#[0-9A-Fa-f]{6}', value):
        raise ValueError('Invalid religion palette color: '+source)
    return [round(int(value[i:i+2], 16)/255, 6) for i in (1, 3, 5)]


def apply(source, body):
    rgb = color(source)
    if rgb is None:
        return body
    result, count = re.subn(r'\bcolor\s*=\s*(?:(?:rgb|hsv360|hsv)\s*)?\{[^{}]*\}',
                           'color = { '+' '.join(map(str, rgb))+' }', body)
    if count != 1:
        raise ValueError('Expected one religion color: '+source)
    return result
