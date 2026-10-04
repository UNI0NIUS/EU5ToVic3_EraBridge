"""Workbench presentation only: catalogs never alter conversion identifiers or output."""
import json
from pathlib import Path
from string import Formatter

CATALOGS = Path(__file__).with_name('converter_locales')
LANGUAGES = {
    'zh-CN': {'name': '简体中文', 'game': 'simp_chinese'},
    'en': {'name': 'English', 'game': 'english'},
}


def normalize_language(language):
    value = str(language).replace('_', '-').lower()
    if value == 'en' or value.startswith('en-'):
        return 'en'
    return 'zh-CN'


def fields(text):
    return sorted(field for _, field, _, _ in Formatter().parse(text) if field is not None)


class Message(str):
    """A source-language string with formatting arguments retained for the UI.

    JSON, logs, comparisons and existing reports still see exactly the original
    string. Translation happens only at an explicit presentation boundary.
    """
    def __new__(cls, source, *arguments):
        value=source.format(*arguments) if arguments else source
        result=super().__new__(cls,value)
        result.source=source;result.arguments=arguments
        return result

    def __reduce__(self):
        return (Message,(self.source,*self.arguments))


def diagnostic(error):
    if isinstance(error,BaseException):
        if len(error.args)==1 and isinstance(error.args[0],Message):return error.args[0]
        return str(error)
    return error


def diagnostic_payload(error):
    """Optional structured companion to the original worker error string."""
    value=diagnostic(error)
    if not isinstance(value,Message):return None
    return {'source':value.source,'arguments':[
        diagnostic_payload(arg) if isinstance(arg,Message) else str(arg)
        for arg in value.arguments]}


def restore_diagnostic(payload,fallback):
    def decode(value,depth=0):
        if depth>12:raise ValueError('Message nesting too deep')
        if isinstance(value,str):return value
        if not isinstance(value,dict) or set(value)!={'source','arguments'}:raise ValueError('Invalid message')
        if not isinstance(value['source'],str) or not isinstance(value['arguments'],list):raise ValueError('Invalid message')
        return Message(value['source'],*(decode(arg,depth+1) for arg in value['arguments']))
    try:return decode(payload)
    except (ValueError,TypeError,IndexError,KeyError,AttributeError):return fallback


class Translator:
    def __init__(self, language='zh-CN'):
        self.language = normalize_language(language)
        self.messages = {}
        if self.language != 'zh-CN':
            with (CATALOGS / (self.language + '.json')).open(encoding='utf-8') as source:
                self.messages = json.load(source)
            for key, value in self.messages.items():
                if not isinstance(value, str) or fields(key) != fields(value):
                    raise ValueError('Invalid translation placeholders: ' + key)

    def __call__(self, source, *args):
        source=diagnostic(source)
        if isinstance(source,Message):
            args=tuple(self(arg) if isinstance(arg,Message) else arg for arg in source.arguments)
            source=source.source
        result = self.messages.get(source, source)
        return result.format(*args) if args else result


def game_labels(game, mod, language):
    """English fallback, then chosen language; mod and replace override base game.

    Return a separate mapping. Candidate.labels and saved projects stay untouched.
    """
    from build_m3_world import load_localization
    selected = LANGUAGES[normalize_language(language)]['game']
    labels = {}
    for folder in dict.fromkeys(('english', selected)):
        for base in (Path(game) / 'localization', Path(mod) / 'localization',
                     Path(mod) / 'localization/replace'):
            labels.update(load_localization(base / folder))
    return labels
