import readline
import re, os, pydoc
import hashlib
import traceback
import textwrap
import itertools

from threading import Lock, Thread
from time import sleep
from xdict import LatinDictEntry, ReverseDict, EntryNotFoundException
from view import Formatter, render_entry, render_reverse, it, bold, render_explaination
from utils import remove_accents
from explainer import explainer

def get_history_key(key):
    d = hashlib.sha256(str.encode(key)).hexdigest()
    return d[:6]

class AsyncProgressDisplayer:
    def __init__(self):
        self.__spinner = ['-', '\\', '|', '/']
        self.__inhibit = Lock()
        self.__inhibit.acquire()

        self.__th = Thread(target=self.__do_printing)
        self.__th.start()
        self.__should_stop = False

    def __do_printing(self):
        i = 0
        while True:
            self.__inhibit.acquire(blocking=True)
            if self.__should_stop:
                return
            
            print("loading...", self.__spinner[i], end='\r')
            i = (i + 1) % 4
            self.__inhibit.release()
            sleep(1)

    def start_wait(self):
        self.__inhibit.release()

    def end_wait(self):
        self.__inhibit.acquire(blocking=True)

    def stop(self):
        self.__should_stop = True
        self.__inhibit.release()
        self.__th.join()


CMD = re.compile(r"^@(?P<cmd>[A-Za-z0-9]+)\s*(?P<arg>.*)?$")
class InteractiveQuery:
    def __init__(self):
        self.__history = {}
        self.__hist_max = 500

        self.__wait_indicator = AsyncProgressDisplayer()

        self.__mode = "latin"
        self.__should_quit = False
        _, self.columns = os.popen('stty size', 'r').read().split()

        self.__cmd_table = {
            "latin": self.__cmd_latin,
            "l":     self.__cmd_latin,
            "eng":   self.__cmd_eng,
            "e":     self.__cmd_eng,
            "quit":  self.__cmd_quit,
            "hist":  self.__cmd_hist,
            "gpt":   self.__cmd_switch_gpt,
            "h":     self.__cmd_help
        }

    def __add_history(self, query, ent):
        if len(self.__history) >= self.__hist_max:
            key = next(self.__history.keys())
            del self.__history[key]
    
        hist_type = "latin"
        key = query
        if isinstance(ent, LatinDictEntry):
            hist_type = "latin"
            key = f"{query}{ent.variant()}"
        elif isinstance(ent, ReverseDict):
            hist_type = "eng"

        _k = get_history_key(f"{hist_type}_{key}")
        self.__history[_k] = ((hist_type, query, ent))

    def __find_histroy(self, mode, key):
        _k = get_history_key(f"{mode}_{key}")
        if _k in self.__history:
            return self.__history[_k]
        return None
    
    def __get_entry(self, entry_class, *args):
        self.__wait_indicator.start_wait()
        try:
            ent = entry_class(*args)
            self.__wait_indicator.end_wait()
        except Exception as e:
            self.__wait_indicator.end_wait()
            raise e

        return ent
    
    def select_ambiguis(self, ent):
        choices = ent.similars()
        print(" Queried lexeme return the following possible lemmas:\n")
        for i, e in enumerate(choices):
            print(f"   {i}. {bold(e.word)}({e.lctx.variant}) - {it(e.property)}")
        print("\n Please select one by typing their number\n")
        selected = None
        while True:
            sel = input(f" Select one lemma [0-{len(choices) - 1}, 'q' for cancel]: ")
            sel = sel.strip()
            if sel == 'q':
                print("abort the selection")
                return None
            try:
                sel = abs(int(sel))
                if sel >= len(choices):
                    continue
                selected = choices[sel]
                break
            except:
                pass
        
        return self.__get_entry(LatinDictEntry, selected.lctx)

    def __cmd_switch_gpt(self, arg):
        """
            [0|1]
            Enable or disable GPT-assists explaination
            Disable it will speed up look up speed significantly
            Enabled by default if a valid apikey is given
        """
        en = arg == 'y'
        explainer.set_enabled(en)

        print("Disabled" if not en else "Enabled", "GPT-assisted explaining")


    def __cmd_latin(self, arg):
        """
            [Latin Word]
            Query the given latin word within all possible inflections
            Switch to latin mode if no parameter is given
        """
        if not arg:
            self.__mode = "latin"
            return
        
        if not isinstance(arg, LatinDictEntry):
            parts = arg.split(',')
            word = parts[0]
            variant = '' if len(parts) == 1 else parts[1]

            record = self.__find_histroy("latin", f"{word}{variant}")
            if not record:
                ent = self.__get_entry(LatinDictEntry, word, variant)

                if ent.require_clarify:
                    ent = self.select_ambiguis(ent)
                    if not ent:
                        return

                self.__add_history(word, ent)

            else:
                _, _, ent = record
        else:
            ent = arg

        formatter = Formatter(int(self.columns), 2, 0, [])
        render_entry(ent, formatter)

        pydoc.pager("\n".join(formatter.get_output()))

    def __cmd_eng(self, arg):
        """
            [English Word]
            Query possible Latins matched with given English
            Switch to english query mode if no parameter
        """
        if not arg:
            self.__mode = "eng"
            return
        
        if not isinstance(arg, LatinDictEntry):
            record = self.__find_histroy("eng", arg)
            if not record:
                ent = self.__get_entry(ReverseDict, arg)
                self.__add_history(arg, ent)
            else:
                _, _, ent = record
        else:
            ent = arg

        formatter = Formatter(int(self.columns), 2, 0, [])
        render_reverse(ent, formatter)

        pydoc.pager("\n".join(formatter.get_output()))

    def __cmd_hist(self, arg):
        """
            [ID]
            Access a cached history search with given ID
            List all cached history searches if no parameter
        """
        if not arg:
            lines = []
            for k, (type_, query, _) in self.__history.items():
                lines.append(f"{k}. {it(type_)}. {bold(query)}")

            pydoc.pager("\n".join(lines))
            return
        
        type_, query, ent = self.__history[arg]
        self.__cmd_table[type_](ent)
        
    def __cmd_quit(self, arg):
        """
            No Parameter
            Quit the dictionary
        """
        self.__should_quit = True

    def __cmd_help(self, arg):
        """
            No Parameter
            Print this help message
        """

        for k, cmd in self.__cmd_table.items():
            docstr = textwrap.dedent(cmd.__doc__.strip())
            strs = []
            for s in docstr.splitlines():
                strs += textwrap.wrap(s.strip(), 70)
            for c1, c2 in itertools.zip_longest([k], strs):
                if c1:
                    c1 = f"@{c1}"
                else:
                    c1 = ""
                    c2 = "   " + c2
                print("  {:<8}  {}".format(c1, c2))
            print()

    def execute_cmd(self, cmdline):
        cmd_m = CMD.match(cmdline)
        if not cmd_m:
            raise ValueError("not a valid command")
        
        cmd_g = cmd_m.groupdict()
        cmd = cmd_g["cmd"]
        arg = cmd_g["arg"]

        if cmd not in self.__cmd_table:
            raise ValueError(f"Command '{cmd}' is not a valid one")
        
        self.__cmd_table[cmd](arg)

    def handle(self):
        cmd = input(f"pulvis:{self.__mode}> ")
        cmd = cmd.strip()
        if cmd.startswith("@"):
            self.execute_cmd(cmd)
            return
        
        self.__cmd_table[self.__mode](cmd)

    def loop(self):
        print()
        print("Welcome to Latin Dictionary by Lunar Dust")
        print("A tool for querying any latin vocabulary")
        print()
        print("Salve ad Thesaurum Latinum Pulveris Lunaris")
        print("Apparatus ad verba latina rogandos")
        print()
        print("   Type the word you want to know and hit enter.")
        print("   Use '@h' for help message.")
        print()

        while not self.__should_quit:
            try:
                self.handle()
            except EntryNotFoundException as e:
                print("Given word can not be found")
            except KeyboardInterrupt as e:
                break
            except Exception:
                print(traceback.format_exc())

        print("\nVale")
        self.__wait_indicator.stop()
