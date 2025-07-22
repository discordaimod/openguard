import logging
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class Config:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.lock = threading.Lock()
        self._data = {}
        self.load_config()

    def load_config(self) -> None:
        try:
            with self.config_path.open("r") as f:
                new_data = yaml.safe_load(f)
            with self.lock:
                self._data = new_data
                self._update_namespaces()
        except (IOError, yaml.YAMLError) as e:
            logger.error("Failed to load or parse config file: %s", e)

    def _update_namespaces(self) -> None:
        for key, value in self._data.items():
            if isinstance(value, dict):
                setattr(self, key, SimpleNamespace(**value))
            else:
                setattr(self, key, value)

        if "Owners" in self._data:
            self.OwnersTuple = tuple(self.Owners.__dict__.values())

    def __getattr__(self, name: str) -> Any:
        with self.lock:
            if name in self.__dict__:
                return self.__dict__[name]
            if name in self._data:
                value = self._data[name]
                if isinstance(value, dict):
                    return SimpleNamespace(**value)
                return value
        raise AttributeError(f"'Config' object has no attribute '{name}'")


class ConfigChangeHandler(FileSystemEventHandler):
    """A robust handler for config file changes that works with various editors."""

    def __init__(self, config: Config):
        self.config = config
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def dispatch(self, event):
        # We only care about events for the config file path.
        if event.src_path == str(self.config.config_path) or getattr(event, "dest_path", None) == str(
            self.config.config_path
        ):
            if event.is_directory:
                return

            with self._lock:
                if self._timer is not None:
                    self._timer.cancel()

                # Use a small delay to debounce in case of multiple events
                self._timer = threading.Timer(0.5, self.config.load_config)
                self._timer.start()


# Path to the configuration file
CONFIG_FILE = Path(__file__).parent / "configs" / "config.yaml"

# Global config instance
config = Config(CONFIG_FILE)
print(CONFIG_FILE)

# Set up watchdog observer
observer = Observer()
observer.schedule(ConfigChangeHandler(config), path=str(CONFIG_FILE.parent), recursive=False)
observer.daemon = True
observer.start()

# To ensure that config changes are reflected, other modules should
# import the 'config' object and access properties from it.
# For example: `from lists import config` and then use `config.Owners`.
# The global assignments that were here previously would not be updated
# on config reload.

jokes = (
    "Complaining about the lack of smoking shelters, the nicotine addicted Python programmers said there ought to be 'spaces for tabs'.",
    "Ubuntu users are apt to get this joke.",
    "Obfuscated Reality Mappers (ORMs) can be useful database tools.",
    "Asked to explain Unicode during an interview, Geoff went into detail about his final year university project. He was not hired.",
    "Triumphantly, Beth removed Python 2.7 from her server in 2030. 'Finally!' she said with glee, only to see the announcement for Python 4.4.",
    "An SQL query goes into a bar, walks up to two tables and asks, 'Can I join you?'",
    "When your hammer is C++, everything begins to look like a thumb.",
    "If you put a million monkeys at a million keyboards, one of them will eventually write a Java program. The rest of them will write Perl.",
    "To understand recursion you must first understand recursion.",
    "I suggested holding a 'Python Object Oriented Programming Seminar', but the acronym was unpopular.",
    "'Knock, knock.' 'Who's there?' ... very long pause ... 'Java.'",
    "How many programmers does it take to change a lightbulb? None, that's a hardware problem.",
    "What's the object-oriented way to become wealthy? Inheritance.",
    "Why don't jokes work in octal? Because 7 10 11.",
    "How many programmers does it take to change a lightbulb? None, they just make darkness a standard.",
    "Two bytes meet. The first byte asks, 'Are you ill?' The second byte replies, 'No, just feeling a bit off.'",
    "Two threads walk into a bar. The barkeeper looks up and yells, 'Hey, I want don't any conditions race like time last!'",
    "Old C programmers don't die, they're just cast into void.",
    "Eight bytes walk into a bar. The bartender asks, 'Can I get you anything?' 'Yeah,' replies the bytes. 'Make us a double.'",
    "Why did the programmer quit his job? Because he didn't get arrays.",
    "Why do Java programmers have to wear glasses? Because they don't see sharp.",
    "Software developers like to solve problems. If there are no problems handily available, they will create their own.",
    ".NET was named .NET so that it wouldn't show up in a Unix directory listing.",
    "Hardware: The part of a computer that you can kick.",
    "A programmer was found dead in the shower. Next to their body was a bottle of shampoo with the instructions 'Lather, Rinse and Repeat'.",
    "Optimist: The glass is half full. Pessimist: The glass is half empty. Programmer: The glass is twice as large as necessary.",
    "In C we had to code our own bugs. In C++ we can inherit them.",
    "How come there is no obfuscated Perl contest? Because everyone would win.",
    "If you play a Windows CD backwards, you'll hear satanic chanting ... worse still, if you play it forwards, it installs Windows.",
    "How many programmers does it take to change a lightbulb? Two: one holds, the other installs Windows on it.",
    "What do you call a programmer from Finland? Nerdic.",
    "What did the Java code say to the C code? A: You've got no class.",
    "Why did Microsoft name their search engine BING? Because It's Not Google.",
    "Pirates go 'arg!', computer pirates go 'argv!'",
    "Software salesmen and used-car salesmen differ in that the latter know when they are lying.",
    "Child: Dad, why does the sun rise in the east and set in the west? Dad: Son, it's working, don't touch it.",
    "Why do programmers confuse Halloween with Christmas? Because OCT 31 == DEC 25.",
    "How many Prolog programmers does it take to change a lightbulb? false.",
    "Real programmers can write assembly code in any language.",
    "Waiter: Would you like coffee or tea? Programmer: Yes.",
    "What do you get when you cross a cat and a dog? Cat dog sin theta.",
    "If loving you is ROM I don't wanna read write.",
    "A programmer walks into a foo...",
    "A programmer walks into a bar and orders 1.38 root beers. The bartender informs her it's a root beer float. She says 'Make it a double!'",
    "What is Benoit B. Mandelbrot's middle name? Benoit B. Mandelbrot.",
    "Why are you always smiling? That's just my... regular expression.",
    "ASCII stupid question, get a stupid ANSI.",
    "A programmer had a problem. He thought to himself, 'I know, I'll solve it with threads!'. has Now problems. two he",
    "Why do sin and tan work? Just cos.",
    "Java: Write once, run away.",
    "I would tell you a joke about UDP, but you would never get it.",
    "A QA engineer walks into a bar. Runs into a bar. Crawls into a bar. Dances into a bar. Tiptoes into a bar. Rams a bar. Jumps into a bar.",
    "My friend's in a band called '1023 Megabytes'... They haven't got a gig yet!",
    "I had a problem so I thought I'd use Java. Now I have a ProblemFactory.",
    "QA Engineer walks into a bar. Orders a beer. Orders 0 beers. Orders 999999999 beers. Orders a lizard. Orders -1 beers. Orders a sfdeljknesv.",
    "A product manager walks into a bar, asks for drink. Bartender says no, but will consider adding later.",
    "How do you generate a random string? Put a first year Computer Science student in Vim and ask them to save and exit.",
    "I've been using Vim for a long time now, mainly because I can't figure out how to exit.",
    "How do you know whether a person is a Vim user? Don't worry, they'll tell you.",
    "Waiter: He's choking! Is anyone a doctor? Programmer: I'm a Vim user.",
    "3 Database Admins walked into a NoSQL bar. A little while later they walked out because they couldn't find a table.",
    "How to explain the movie Inception to a programmer? When you run a VM inside another VM, inside another VM ... everything runs real slow!",
    'What do you call a parrot that says "Squawk! Pieces of nine! Pieces of nine!"? A parrot-ey error.',
    "There are only two hard problems in Computer Science: cache invalidation, naming things and off-by-one-errors.",
    "There are 10 types of people: those who understand binary and those who don't.",
    "There are 2 types of people: those who can extrapolate from incomplete data sets...",
    "There are II types of people: Those who understand Roman Numerals and those who don't.",
    "There are 10 types of people: those who understand hexadecimal and 15 others.",
    "There are 10 types of people: those who understand binary, those who don't, and those who were expecting this joke to be in trinary.",
    "There are 10 types of people: those who understand trinary, those who don't, and those who have never heard of it.",
    "What do you call eight hobbits? A hobbyte.",
    "The best thing about a Boolean is even if you are wrong, you are only off by a bit.",
    "A good programmer is someone who always looks both ways before crossing a one-way street.",
    "There are two ways to write error-free programs; only the third one works.",
    "QAs consist of 55% water, 30% blood and 15% Jira tickets.",
    "Sympathy for the Devil is really just about being nice to QAs.",
    "How many QAs does it take to change a lightbulb? They noticed that the room was dark. They don't fix problems, they find them.",
    'A programmer crashes a car at the bottom of a hill, a bystander asks what happened, he says "No idea. Let\'s push it back up and try again".',
    "What do you mean 911 is only for emergencies? I've got a merge conflict.",
    "Writing PHP is like peeing in the swimming pool, everyone did it, but we don't need to bring it up in public.",
    "Why did the QA cross the road? To ruin everyone's day.",
    "Number of days since I have encountered an array index error: -1.",
    "Number of days since I have encountered an off-by-one error: 0.",
    "Speed dating is useless. 5 minutes is not enough to properly explain the benefits of the Unix philosophy.",
    'Microsoft hold a bi-monthly internal "productive week" where they use Google instead of Bing.',
    "Schrodinger's attitude to web development: If I don't look at it in Internet Explorer then there's a chance it looks fine.",
    "Finding a good PHP developer is like looking for a needle in a haystack. Or is it a hackstack in a needle?",
    "Unix is user friendly. It's just very particular about who its friends are.",
    'A COBOL programmer makes millions with Y2K remediation and decides to get cryogenically frozen. "The year is 9999. You know COBOL, right?"',
    "The C language combines all the power of assembly language with all the ease-of-use of assembly language.",
    "An SEO expert walks into a bar, bars, pub, public house, Irish pub, tavern, bartender, beer, liquor, wine, alcohol, spirits...",
    "What does 'Emacs' stand for? 'Exclusively used by middle aged computer scientists.'",
    "What does pyjokes have in common with Adobe Flash? It gets updated all the time, but never gets any better.",
    "Why does Waldo only wear stripes? Because he doesn't want to be spotted.",
    "I went to a street where the houses were numbered 8k, 16k, 32k, 64k, 128k, 256k and 512k. It was a trip down Memory Lane.",
    "!false, (It's funny because it's true)",
    "['hip', 'hip'] (hip hip array!)",
    "Programmer: The ship I boarded crashed and I am dying! Project Manager: Then let's do a quick knowledge transfer session before you go.",
    "Are you a RESTful API? because you GET my attention, PUT some love, POST the cutest smile, and DELETE my bad day.",
    "I used to know a joke about Java, but I run out of memory.",
    "My girlfriend dumped me after I named a class after her. She felt I treated her like an object.",
    "Girl: Do you drink? Programmer: No. Girl: Have Girlfriend? Programmer: No. Girl: Then how do you enjoy life? Programmer: I am Programmer",
    'A Programmer was walking out of door for work, his wife said "while you\'re out, buy some milk" and he never returned.',
    "A: What is your address? Me: 173.168.15.10 A: No, your local address Me: 127.0.0.1 A: I mean your physical address B: 29:01:38:62:31:58",
    "Why do programmers always mix up Halloween and Christmas? Because Oct 31 equals Dec 25.",
    "Programming is 10% science, 20% ingenuity, and 70% getting the ingenuity to work with the science.",
    "There are three kinds of lies: Lies, damned lies, and benchmarks.",
    "All programmers are playwrights, and all computers are lousy actors.",
    "Have you heard about the new Cray super computer? It's so fast, it executes an infinite loop in 6 seconds.",
    "The generation of random numbers is too important to be left to chance.",
    "I just saw my life flash before my eyes and all I could see was a close tag.",
    "The computer is mightier than the pen, the sword, and usually, the programmer",
    "Debugging: Removing the needles from the haystack.",
    "If doctors were like software engineers, they would say things like Have you tried killing yourself and being reborn?",
    "Debugging is like being the detective in a crime drama where you are also the murderer.",
    "The best thing about a Boolean is that even if you are wrong, you are only off by a bit.",
    "If you listen to a UNIX shell, can you hear the C?",
    "Why do Java programmers have to wear glasses? Because they don't C#.",
    "When Apple employees die, does their life HTML5 in front of their eyes?",
    "What did the router say to the doctor? It hurts when IP.",
    "Learning JavaScript is like looking both ways before you cross the street, and then getting hit by an airplane.",
    "I for one am excited for the days when dereferencing a null pointer causes an aneurysm.",
    "Debugging is like an onion. There are multiple layers to it, and the more you peel them back.",
    "When your code does not change color automatically, Something's wrong, I can feel it.",
    "I have a joke on programming but it only works on my computer.",
    "Why do you always use i and j variales in loops? It's the law......",
    "As far as we know, our computer has never had an undetected error.",
    "A user friendly computer first requires a friendly user.",
    "Bug? That's not a bug, that's a feature.",
    "Buy a Pentium 586/200 so you can reboot faster.",
    "Computer analyst to programmer: You start coding. I'll go find out what they want.",
    "Computer programmers do it byte by byte.",
    "Don't compute and drive; the life you save may be your own.",
    "How an engineer writes a program: Start by debugging an empty file...",
    "If at first you don't succeed, call it version 1.0.",
    "I have a dream: 1073741824 bytes free.",
    "I haven't lost my mind; it's backed up on tape somewhere.",
    "Is reading in the bathroom considered Multi-Tasking.",
    "Never say 'OOPS!' always say 'Ah, Interesting!'",
    "One person's error is another person's data.",
    "Press CTRL-ALT-DEL to continue....",
    "Programmer's Time-Space Continuum: Programmers continuously space the time.",
    "Speed Kills! Use Windows.",
    "The box said: 'install on Windows 95, NT 4.0 or better'. So I installed it on Linux.",
    "The program is absolutely right; therefore the computer must be wrong.",
    "There are only 10 types of people in this world: those who understand binary, and those who don't.",
    "There were computers in Biblical times. Eve had an Apple.",
    "Those who can, do. Those who cannot, teach. Those who cannot teach, HACK!",
    "User error: replace user and press any key to continue.",
    "Warning, keyboard not found. Press Enter to continue.",
    "Why do they call this a word processor? It's simple, ... you've seen what food processors do to food, right?",
    "Why do we want intelligent terminals when there are so many stupid users?",
    "Windows is NOT a virus. Viruses DO something.",
    "WINDOWS stands for Will Install Needless Data On Whole System.",
    "You are making progress if each mistake is a new one.",
    "You had mail, but the super-user read it, and deleted it!",
    "You never finish a program, you just stop working on it.",
    "You don't have to know how the computer works, just how to work the computer.",
    "You forgot to do your backup 16 days ago. Tomorrow you'll need that version.",
    "I love pressing the F5 key. It's refreshing.",
    "My favourite computer based band is the Black IPs.",
    "Why was the developer bankrupt? He'd used all his cache.",
    "A friend is in a band called 1023Mb. They haven't had a gig yet.",
    "Apparently my password needs to be capitals only so I've changed it to LONDONMADRIDROME",
    "I changed my password to BeefStew but the computer told me it wasn't Stroganoff.",
    "Changed my password to fortnight but apparently that's two week.",
    "Artificial intelligence usually beats real stupidity.",
    "The Internet: where men are men, women are men, and children are FBI agents.",
    "Bugs come in through open Windows.",
    "Unix is user friendly. It's just selective about who its friends are.",
    "Failure is not an option. It comes bundled with your Microsoft product.",
    "Computers are like air conditioners: they stop working when you open Windows.",
    "Beware of programmers that carry screwdrivers.",
    "I'm not anti-social; I'm just not user friendly.",
    "Hey! It compiles! Ship it!",
    "If Ruby is not and Perl is the answer, you don't understand the question.",
    "My attitude isn't bad. It's in beta.",
    "Programmers are tools for converting caffeine into code.",
    "There are three kinds of people: those who can count and those who can't.",
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "Why was the JavaScript developer sad? Because he didn't Node how to Express himself.",
    "There are 10 kinds of people in this world: those who understand binary, and those who don't, and those who didn't expect a base 3 joke.",
    "Debugging: The process of removing software bugs, which are not to be confused with hardware bugs, which are actual insects.",
    "My code doesn't have bugs, it has random features.",
    "Why do programmers prefer dark chocolate? Because it's byte-sized.",
)
