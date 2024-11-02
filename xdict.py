import requests, re
from bs4 import BeautifulSoup, Tag, NavigableString
from utils import check_subset, remove_accents

from explainer import explainer

def get_indent(level):
    return " " * (4 * level)

class EntryNotFoundException(Exception):
    def __init__(self, *args):
        super().__init__(*args)

class LookupContext:
    def __init__(self, word, variant = ''):
        self.variant = variant

        key = "parola" if not variant else "lemma"
        self.entry = f"https://www.online-latin-dictionary.com/latin-english-dictionary.php?{key}={word}{variant}"
        self.conj_url = f"https://www.online-latin-dictionary.com/latin-dictionary-flexion.php?{key}={word}{variant}"

    def get_entry(self):
        return LookupContext.get_html_object(self.entry)
    
    def get_flexion(self):
        return LookupContext.get_html_object(self.conj_url)
    
    @staticmethod
    def request(path):
        url = f"https://www.online-latin-dictionary.com/{path}"
        return LookupContext.get_html_object(url) 

    @staticmethod
    def get_html_object(url):
        response = requests.get(url)            
        response.raise_for_status()

        return BeautifulSoup(response.text, 'html.parser')

class WordMeaning:
    def __init__(self, root : Tag):
        self.lemma = root.find("span", class_='lemma').text
        self.gramma = root.find("span", class_='grammatica').text
        self.meanings = []
        
        for span in root.find_all("span", class_="english"):
            self.meanings.append(span.text)

    def pretty_print(self, lvl):
        ids = get_indent(lvl)
        return [f'{ids} ({self.gramma})', 
                f'{ids} {" / ".join(self.meanings)}']

class FlexionEntry:
    def __init__(self, root: Tag):
        ch = [d for d in root.contents if isinstance(d, Tag)]
        if len(ch) == 2:
            forms = ch[1]
            self.type = ch[0].text
            self.type = self.type.strip(': ')
        else:
            forms = ch[0]
            self.type = "Invar."
            
        
        self.forms = []
        self.__parse_forms(forms)

    def __parse_forms(self, root):
        lst = []
        constructs = ['', [], '']
        i = 0

        for el in root.children:
            if isinstance(el, NavigableString):
                if el.strip() == ',':
                    [a, b, c] = constructs
                    lst.append((a, b, c))
                    constructs = ['', [], '']
                    i = 0
                continue

            if el['class'][0] == 'radice':
                if i >= 2:
                    constructs[2] += el.text
                else:
                    constructs[0] = el.text
                i += 1
            if el['class'][0] == 'desinenza':
                constructs[1] = [v.strip('– ') for v in el.text.split(',')]
                i += 1
        
        if constructs[0]:
            [a, b, c] = constructs
            lst.append((a, b, c))

        for (a, b, c) in lst:
            if not b:
                self.forms.append((a, '', ''))

            for inflected in b:
                self.forms.append((a, inflected, c))

    def pretty_print(self, lvl):
        ids = get_indent(lvl)
        return [f'{ids} [{self.type}] ' + ", ".join([f"{a}-{b} {c}" for a, b, c in self.forms])]

class FlexionPlane:
    def __init__(self, plane_tags):
        self.groups = {}

        group_title = "DEFAULT"
        for tag in plane_tags:
            if tag.name != 'div':
                continue
            if tag['class'][0] != "ff_tbl_container":
                group_title = tag.text
            else:
                arr = []
                for el in tag.children:
                    if isinstance(el, str):
                        continue
                    arr.append(FlexionEntry(el))
                self.groups[group_title] = arr
        
    def pretty_print(self, level):
        ids = get_indent(level)

        arr = []
        for title, grp in self.groups.items():
            arr.append(f"{ids}{title}")

            for l in grp:
                 arr += l.pretty_print(level + 1)

        return arr

class FlexionTable:
    def __init__(self, root : Tag):
        self.planes = {}

        title = None
        collects = []

        all_tags = root.find_all('div', class_=lambda t: self.__find_all_stuff(t))
        
        for ch in all_tags:
            classes = ch.get("class", [])
            if "background-red" in classes:
                if collects:
                    self.planes[title] = FlexionPlane(collects)
                    collects.clear()
                title = ch.text
            elif title is not None:
                collects.append(ch)

        if collects:
            self.planes[title] = FlexionPlane(collects)
        
    def __find_all_stuff(self, t):
        classes = set(t.split(' '))
        return check_subset(classes, [
            "background-red", "background-green", 
            "ff_tbl_container"
        ])
    
    def pretty_print(self, level):
        ids = get_indent(level)

        arr = []
        for title, plane in self.planes.items():
            arr.append(f"{ids}{title}")
            arr += plane.pretty_print(level + 1)

        return arr

WORD_VAR=re.compile(r"^.*\?lemma=(?P<word>[^0-9]+)(?P<var>[0-9]+)$")
EXTRACT=re.compile(r"^\((?P<prop>.+)\)(?P<mean>.*)$")
MAYHAS_PARANTH=re.compile(r"^(\((?P<prop>.+)\))?\s*(?P<mean>.*)$")

class Ambiguity:
    def __init__(self, ent):
        m = WORD_VAR.match(ent.a["href"]).groupdict()
        self.lctx = LookupContext(m["word"], m["var"])
        self.word = ent.a.text
        
        desc = " ".join([v.text.strip() for v in ent.children if v.name != 'a'])
        m2 = EXTRACT.match(desc.strip()).groupdict()
        self.explain = m2["mean"]
        self.property = m2["prop"]

    def __str__(self):
        return f"{self.word}   {self.explain} ({self.property})"
    
    def pretty_print(self, level):
        ids = get_indent(level)
        return f"{ids} {self.word} - {self.explain} ({self.property})"


class LatinDictEntry:
    def __init__(self, word, variant=''):
        if isinstance(word, LookupContext):
            self.__context = word
        else:
            self.__context = LookupContext(word, variant)

        self.__candidates = []
        self.__conj_table = {}
        self.meaning = None
        self.require_clarify = False
        self.__load_entry()

    def __find_disambigua_like(self, t):
        if t == None:
            return False
        classes = set(t.split(' '))
        return check_subset(classes, ["disambigua", "ff_search_container"])

    def __load_entry(self):
        ent = self.__context.get_entry()
        disambigua = ent.find(class_=lambda x: self.__find_disambigua_like(x))
        if disambigua:
            self.__parse_disambigua(disambigua)

        if self.require_clarify:
            return

        body = ent.find(id="myth")
        if not body:
            if not disambigua:
                raise EntryNotFoundException()
            return
        
        self.__parse_entrybody(body)
        self.__parse_flexion()

        words = f"{remove_accents(self.meaning.lemma)} ({self.meaning.gramma})"
        e = explainer.explain([words])
        if e:
            self.__explained = e.entries[0]

    def __parse_flexion(self):
        flexion = self.__context.get_flexion()
        conj = flexion.find('div', class_="conjugation-container")
        if not conj:
            return
        
        t = conj.find('div', recursive=False)
        oppon_conj = None
        if t.text.startswith('ACTIVE'):
            oppon_conj = "passive"
            self.__conj_table["active"] = FlexionTable(conj)
        elif t.text.startswith('PASSIVE'):
            oppon_conj = "active"
            self.__conj_table["passive"] = FlexionTable(conj)
        else:
            self.__conj_table["inflection"] = FlexionTable(conj)
            return
        
        a_tag = conj.find('span', class_=['lnk'], recursive=False)
        a_tag = a_tag.find('a', recursive=False) if a_tag else None
        if not a_tag:
            self.__conj_table[oppon_conj] = None
            return
        
        flex_oppon = LookupContext.request(a_tag['href'])
        conj_oppon = flex_oppon.find('div', class_="conjugation-container")
        self.__conj_table[oppon_conj] = FlexionTable(conj_oppon)


    def __parse_entrybody(self, root:Tag):
        self.meaning = WordMeaning(root)

    def __parse_disambigua(self, root:Tag):
        is_ambig = root.name == 'ul'
        self.require_clarify = not is_ambig
        for li in root.children:
            if not isinstance(li, Tag):
                continue
            if not is_ambig:
                li = li.find_all('div', recursive=False)[1]

            if li.a["href"] == '#':
                continue
            
            am = Ambiguity(li)
            self.__candidates.append(am)

    def flexions(self):
        return self.__conj_table
    
    def similars(self):
        return self.__candidates
    
    def variant(self):
        return self.__context.variant
    
    def explaination(self):
        return self.__explained

    def pretty_print(self, level):
        ids = get_indent(level)

        arr = []
        for k, v in self.__conj_table.items():
            ids2 = get_indent(level + 1)
            arr.append(f"{ids2} {k}")
            if v is not None:
                arr += v.pretty_print(level + 2)
            else:
                arr.append("N/A")

        return [
            f"{ids} Explaination",
            *(self.meaning.pretty_print(level+1) if self.meaning else []),
            f"{ids} Ambiguities",
            *[v.pretty_print(level+1) for v in self.__candidates],
            f"{ids} Conjugate/Inflections",
            *arr
        ]

class ReverseDictEntry:
    def __init__(self):
        self.lemma = ""
        self.gramma = {}
        self.explains = {}
        self.__recent_gramma = ""

    def set_lemma(self, val):
        self.lemma = val

    def set_grama(self, val):
        self.__recent_gramma = val
        self.gramma[val] = []

    def add_vocab_to_recent(self, val):
        self.gramma[self.__recent_gramma].append(val)

    def update_explaination(self):
        for k, vs in self.gramma.items():
            words = [f"{remove_accents(v)} ({k})" for v,_ in vs]
            self.explains[k] = explainer.explain(words)

    @staticmethod
    def createEntry(stream):
        S_LEMMA=0
        S_GRAMA=1
        S_VOCAB=2
        S_TERMN=3

        ent = ReverseDictEntry()
        state = S_LEMMA
        while state != S_TERMN:
            n  = next(stream)
            l1 = stream.look_ahead(n=1)

            if state == S_LEMMA and n.lemma_token():
                ent.set_lemma(n.value().text)
                state = S_GRAMA
                continue

            if state == S_GRAMA and n.gramma_token():
                ent.set_grama(n.value().text)
                state = S_VOCAB
                continue

            if state == S_VOCAB:
                if not n.vocab_token():
                    raise ValueError(f"conflict state ({n.type()}, {state})")
                
                descs = "|".join([x.strip() for x in n.value().contents if isinstance(x, NavigableString)])
                sps = descs.split(',')

                if len(sps) == 1:
                    sps = sps[0].split('|')

                for t in sps:
                    t = t.strip(" |")
                    if not t:
                        continue

                    m = MAYHAS_PARANTH.match(t)
                    if not m:
                        continue

                    g = m.groupdict()
                    nuance = "" if not g["prop"] else g["prop"]
                    word = g["mean"].strip()
                    ent.add_vocab_to_recent((word.replace('|', ' '), nuance.replace('|', ' ')))
            
                if l1 and l1.gramma_token():
                    state = S_GRAMA
                    continue

            if not l1 or l1.lemma_token():
                if state != S_VOCAB:
                    return None
                
                state = S_TERMN
                continue
        return ent
    

    def pretty_print(self, level):
        ids = get_indent(level)
        ids2 = get_indent(level + 1)
        arr = []
        for k, v in self.gramma.items():
            arr.append(f"{ids} {k}")
            for e, n in v:
                arr.append(f"{ids2} {e} ({n})")
        
        return [ 
            f"{ids} \"{self.lemma}\"",
            *arr
        ]

class ReverseDictToken:
    GRAMMATICA=0
    VOCAB=1
    LEMMA=2
    def __init__(self, type, val):
        self.__type = type
        self.__val  = val

    @staticmethod
    def gramma(val):
        return ReverseDictToken(ReverseDictToken.GRAMMATICA, val)
    
    @staticmethod
    def vocab(val):
        return ReverseDictToken(ReverseDictToken.VOCAB, val)
    
    @staticmethod
    def lemma(val):
        return ReverseDictToken(ReverseDictToken.LEMMA, val)
    
    def gramma_token(self):
        return self.__type == ReverseDictToken.GRAMMATICA
    
    def vocab_token(self):
        return self.__type == ReverseDictToken.VOCAB
    
    def lemma_token(self):
        return self.__type == ReverseDictToken.LEMMA
    
    def value(self):
        return self.__val
    
    def type(self):
        return self.__type

class ReverseDictTokenStream:
    def __init__(self, container: Tag):
        self.__c = container.children
        self.__next = []

    def __find_next(self):
        while True:
            n = next(self.__c)
            if n.name != "span":
                continue
            classes = n.get("class", [])
            if classes == ["grammatica"]:
                return ReverseDictToken.gramma(n)
            if classes == ["english"]:
                return ReverseDictToken.vocab(n)
            if classes == ["lemma"]:
                return ReverseDictToken.lemma(n)

    def __iter__(self):
        return self
    
    def __next__(self):
        if self.__next:
            return self.__next.pop(0)
        return self.__find_next()
    
    def look_ahead(self, n = 1):
        try:
            for _ in range(n):
                nxt = self.__find_next()
                self.__next.append(nxt)
            return self.__next[-1]
        except StopIteration:
            return None



class ReverseDict:
    def __init__(self, word):
        self.query = word
        obj = LookupContext.request(f"english-latin-dictionary.php?parola={word}")
        container = obj.find('div', id="myth")
        if not container:
            raise EntryNotFoundException()
        
        self.entries = []

        tokens = ReverseDictTokenStream(container)
        while True:
            try:
                ent = ReverseDictEntry.createEntry(tokens)
                if not ent:
                    continue
                self.entries.append(ent)
            except StopIteration:
                break

        self.entries[0].update_explaination()
        
    def pretty_print(self, level):
        ids = get_indent(level)
        arr = []
        for x in self.entries:
            arr.append(f"{ids} ENTRY")
            arr += x.pretty_print(level + 1)
        
        return arr