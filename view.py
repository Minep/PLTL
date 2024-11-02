import itertools, textwrap

def emph(s, no_reset=False):
    return f"\x1b[1;4m{s}" + ("\x1b[0m" if not no_reset else "")

def bold(s, no_reset=False):
    return f"\x1b[1m{s}" + ("\x1b[0m" if not no_reset else "")

def it(s, no_reset=False):
    return f"\x1b[3m{s}" + ("\x1b[0m" if not no_reset else "")


class Formatter:
    INDENT = "    "
    def __init__(self, width, pad, level, buffer = []):
        self.__p = pad
        self.__l = level
        self.__w_org = width
        self.__buffer = buffer
        self.__w = width - pad * 2 - level * len(Formatter.INDENT)

        self.__fmt = (" "*pad) + "%s" + (" "*pad)
        self.__ind = Formatter.INDENT * level

    def append(self, s = "", offset=0):
       self.__buffer.append(self.__ind + Formatter.INDENT * offset + s)


    def appends(self, strs, offset=0):
       off = Formatter.INDENT * offset
       for s in strs:
           self.__buffer.append(self.__ind + off + s)

    def width(self, offset=0):
        return self.__w - offset * len(Formatter.INDENT)
    
    def next_level(self):
        return Formatter(self.__w_org, self.__p, self.__l + 1, self.__buffer)
    
    def get_output(self):
        r = []
        for s in self.__buffer:
            r.append(self.__fmt%(s))
        return r

def render_panel(panel, formatter, cols=3):
    pairs = list(panel.groups.items())

    col_w = formatter.width() // cols - 3
    for i in range(0, len(pairs), cols):
        grps = [x for x in pairs[i:i + cols] if x]
        if len(grps) == 0:
            continue

        titles = [x for x, _ in grps]
        vals =   [x for _, x in grps]

        actual_col_w = len(grps)
        fmt = ("\x1b[30;43m{:^%d}\x1b[0m | "%(col_w)) * actual_col_w
        formatter.append(fmt.format(*titles))

        for el in itertools.zip_longest(*vals):
            row = sum([([[e.type], e.forms] if e else ['', []]) for e in el], [])
            fmt_entry = "{:<%d}{:<%d} | "%(15 + 8, col_w - 15 + 10)
            fmt_entry = fmt_entry * (actual_col_w)

            for r in itertools.zip_longest(*row):
                l = []
                for i, component in enumerate(r):
                    if not component:
                        l.append(it("") if i % 2 == 0 else emph(""))
                        continue
                    if isinstance(component, str):
                        l.append(it(component))
                        continue
                    
                    stem, inflect, append = component
                    l.append(f"{stem}{emph(inflect)} {append}".strip())

                formatter.append(fmt_entry.format(*l))

def render_table(tab, formatter):
    fmt = "\x1b[39;41m{:^%d}\x1b[0m"%(formatter.width() + 1)
    for title, panel in tab.planes.items():
        formatter.append()

        formatter.append(fmt.format(bold(title, no_reset=True)))
        render_panel(panel, formatter)

        formatter.append()

def render_conjug(conj, formatter):
    for title, tab in conj.items():
        if not tab:
            continue
        formatter.append()
        formatter.append(bold(title.upper(), no_reset=True))
        render_table(tab, formatter.next_level())

def render_entry(entry, formatter):
    word = entry.meaning

    # banner
    fmt = "{:^20}{:^%d}{:^20}"%(formatter.width() - 40)
    lem_var = "%s(%s)"%(word.lemma.upper(), '000' if not entry.variant() else entry.variant())
    formatter.append(fmt.format(lem_var, "PULVERIS LUNARIS THESAURUS LATINUS", lem_var))
    formatter.append()
    formatter.append()

    formatter.append(bold("LEMMA"))
    formatter.append()
    formatter.append(f"{bold(word.lemma)} - {it(word.gramma)}", offset=1)
    formatter.append()

    formatter.append(bold("DESCRIPTION"))
    formatter.append()
    for m in word.meanings:
        formatter.append(f"* {m}", offset=1)
    formatter.append()

    explain = entry.explaination()
    if explain:
        render_expl_entry(explain, formatter)
        formatter.append()

    formatter.append(bold("SEE ALSO"))
    for m in entry.similars():
        formatter.append(
            f"* {emph(m.word)}({m.lctx.variant}) - {it(m.property)} : {m.explain}", offset=1
        )
    formatter.append()

    formatter.append(bold("FLEXIONS"))
    render_conjug(entry.flexions(), formatter.next_level())
    formatter.append()


def render_reverse_ent(i, ent, formatter, render_explain=None):
    formatter.append(bold("LEMMA"))
    formatter.append()

    formatter.append(ent.lemma, offset=1)
    formatter.append()

    formatter.append(bold("VARIANTS"))
    formatter.append()

    nextl = formatter.next_level()
    for k, v in ent.gramma.items():
        nextl.append(it(k))
        for w, n in v:
            p = f"* {w}"
            if n:
                p = f"{p} ({n})"
            nextl.append(p, offset=1)

        nextl.append()
        
        if k not in ent.explains:
            continue

        explain = ent.explains[k]
        if explain:
            render_explaination(explain, nextl)
        
        nextl.append()
        
    

def render_reverse(dict, formatter, render_explain=None):
    fmt = "{:^20}{:^%d}{:^20}"%(formatter.width() - 40)
    lem_var = dict.query
    formatter.append(fmt.format(lem_var, "ENGLISH-LATIN LOOKUP", lem_var))
    formatter.append()
    formatter.append()

    for i, ent in enumerate(dict.entries):
        formatter.append(bold(f"MATCH {i + 1}"))
        formatter.append()
        render_reverse_ent(i, ent, formatter.next_level(), render_explain)


def render_expl_entry(ent, formatter):
    formatter.append(bold("GRAMMAR"))
    formatter.append()
    formatter.appends(
        textwrap.wrap(ent.explain_grammar, width=80)
        , offset=1)
    formatter.append()

    formatter.append(bold("SEMANTIC"))
    formatter.append()
    formatter.appends(
        textwrap.wrap(ent.explain_semantic, width=80)
        , offset=1)
    formatter.append()

    formatter.append(bold("NUANCES"))
    formatter.append()
    formatter.appends(
        textwrap.wrap(ent.explain_nuances, width=80)
        , offset=1)
    formatter.append()
    
    # formatter.append(bold("NUANCES"))
    # formatter.append()
    # formatter.appends(
    #     textwrap.wrap(ent.compare, width=80)
    #     , offset=1)
    # formatter.append()

def render_explaination(explain, formatter):
    formatter.append(bold("EXPLAIN"))
    formatter.append()
    nextl = formatter.next_level()
    for entry in explain.entries:
        nextl.append(emph(entry.expression))
        nextl.append()
        render_expl_entry(entry, nextl)
        nextl.append()

    formatter.append()