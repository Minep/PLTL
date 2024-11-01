import unicodedata

def remove_accents(text):
    decomposed_text = unicodedata.normalize('NFD', text)
    text_without_accents = ''.join(char for char in decomposed_text if unicodedata.category(char) != 'Mn')
    return text_without_accents

def check_subset(ref, maybe_subset):
    return any([ e in ref for e in maybe_subset ])


def normalize_to_ascii(unicode_string):
    normalized_string = unicodedata.normalize('NFKD', unicode_string)
    ascii_string = normalized_string.encode('ascii', 'ignore').decode('ascii')
    return ascii_string