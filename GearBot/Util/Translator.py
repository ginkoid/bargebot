from parsimonious import ParseError, VisitationError
from pyseeyou import format

from Util import GearbotLogging, Emoji, Utils

LANGS = dict()
LANG_NAMES = dict(en_US= "English")
LANG_CODES = dict(English="en_US")
BOT = None
untranlatable = {None, ''}

async def initialize(bot_in):
    global BOT
    BOT = bot_in
    for lang in LANG_CODES.values():
        load_translations(lang)

def load_translations(lang):
    LANGS[lang] = Utils.fetch_from_disk(f"lang/{lang}")

def translate(key, location, **kwargs):
    lang_key = "en_US"
    translated = key
    if key not in LANGS[lang_key]:
        if key not in untranlatable:
            BOT.loop.create_task(tranlator_log('WARNING', f'Untranslatable string detected in {lang_key}: {key}\n'))
            untranlatable.add(key)
        return key
    try:
        translated = format(LANGS[lang_key][key], kwargs, lang_key)
    except (KeyError, ValueError, ParseError, VisitationError) as ex:
        BOT.loop.create_task(tranlator_log('NO', f'Corrupt translation detected!\n**Lang code:** {lang_key}\n**Translation key:** {key}\n```\n{LANGS[lang_key][key]}```'))
        GearbotLogging.exception("Corrupt translation", ex)
    return translated

def translate_by_code(key, code, **kwargs):
    if key not in LANGS[code]:
        return key
    return format(LANGS[code][key], kwargs, code)

async def tranlator_log(emoji, message, embed=None):
    m = f'{Emoji.get_chat_emoji(emoji)} {message}'
    return await get_translator_log_channel()(m, embed=embed)

def get_translator_log_channel():
    return GearbotLogging.bot_log
