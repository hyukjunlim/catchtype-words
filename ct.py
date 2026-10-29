"""ct: fix Catchtype (Windows) word lists from the terminal.

Catchtype keeps its word lists in %APPDATA%\\Catchtype\\settings.json, in a format with no public spec:
  alwaysConvertedWords  "state\\tkeys\\tunixtime"  always switch these keys to the other language
  undoneWords           "count\\tstate\\tkeys"     how often a conversion of these keys was undone
  learnedWordDates      "state\\tkeys\\tunixtime"  when the keys reached 3 undos and became kept-as-typed
`state` is the input state the keys were typed in (korean/english); `keys` are the physical keys as Latin letters.
Catchtype rewrites the file while it runs, so this tool stops it before editing and starts it again after.
"""

import argparse
import csv
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
SETTINGS = Path(os.environ["APPDATA"]) / "Catchtype" / "settings.json"
DEFAULT_EXE = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Catchtype" / "Catchtype.exe"
SNAPSHOT = REPO / "my-words.json"
CACHE_DIR = REPO / ".cache"
UNDOS_TO_LEARN = 3  # Catchtype: "같은 말을 세 번 되돌리면 다음부터 친 그대로 둬요"
BACKUPS_KEPT = 30
STATE_NAME = {"korean": "한글", "english": "영어"}


class Stop(Exception):
    """Ends the command with a message, leaving the settings untouched."""


# ---------- 2-set (dubeolsik) keyboard ----------

KEY_TO_JAMO = dict(zip("qwertyuiopasdfghjklzxcvbnm", "ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔㅁㄴㅇㄹㅎㅗㅓㅏㅣㅋㅌㅊㅍㅠㅜㅡ"))
KEY_TO_JAMO.update(zip("QWERTOP", "ㅃㅉㄸㄲㅆㅒㅖ"))
JAMO_TO_KEY = {j: k for k, j in KEY_TO_JAMO.items()}
INITIALS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
MEDIALS = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
FINALS = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ",
          "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
VOWEL_PAIRS = {("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ", ("ㅜ", "ㅓ"): "ㅝ",
               ("ㅜ", "ㅔ"): "ㅞ", ("ㅜ", "ㅣ"): "ㅟ", ("ㅡ", "ㅣ"): "ㅢ"}
FINAL_PAIRS = {("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ", ("ㄹ", "ㄱ"): "ㄺ", ("ㄹ", "ㅁ"): "ㄻ",
               ("ㄹ", "ㅂ"): "ㄼ", ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ", ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ",
               ("ㅂ", "ㅅ"): "ㅄ"}
SPLIT = {v: "".join(k) for k, v in {**VOWEL_PAIRS, **FINAL_PAIRS}.items()}


def to_hangul(keys):
    """What `keys` produce when typed in the Korean state."""
    out = []
    cho = jung = None
    jong = ""

    def flush():
        nonlocal cho, jung, jong
        if cho and jung:
            out.append(chr(0xAC00 + (INITIALS.index(cho) * 21 + MEDIALS.index(jung)) * 28 + FINALS.index(jong)))
        else:
            out.extend(x for x in (cho, jung) if x)
        cho = jung = None
        jong = ""

    for key in keys:
        j = KEY_TO_JAMO.get(key) or KEY_TO_JAMO[key.lower()]
        if j in MEDIALS:
            if cho and not jung:
                jung = j
            elif jung and not jong and (jung, j) in VOWEL_PAIRS:
                jung = VOWEL_PAIRS[jung, j]
            elif jong:  # the final consonant moves on to start the next syllable
                stay, move = SPLIT[jong] if jong in SPLIT else ("", jong)
                jong = stay
                flush()
                cho, jung = move, j
            else:
                flush()
                jung = j
        elif cho and jung and not jong and j in FINALS:
            jong = j
        elif jong and (jong, j) in FINAL_PAIRS:
            jong = FINAL_PAIRS[jong, j]
        else:
            flush()
            cho = j
    flush()
    return "".join(out)


def to_keys(hangul):
    """The keys that type `hangul` in the Korean state."""
    keys = []
    for ch in hangul:
        code = ord(ch) - 0xAC00
        parts = [INITIALS[code // 588], MEDIALS[code % 588 // 28], FINALS[code % 28]] if 0 <= code < 11172 else [ch]
        for part in parts:
            keys.extend(JAMO_TO_KEY[jamo] for jamo in SPLIT.get(part, part))
    return "".join(keys)


def parse_word(word):
    """Return (keys, script) for a word given either as Latin keys or as Hangul."""
    word = word.strip()
    if re.fullmatch(r"[A-Za-z]+", word):
        return word, "latin"
    if re.fullmatch(r"[가-힣ㄱ-ㅣ]+", word):
        try:
            return to_keys(word), "hangul"
        except KeyError:
            pass
    raise Stop(f"'{word}': 한글이나 영문 한 가지로, 띄어쓰기 없이 한 낱말만 써 주세요.")


def typed_form(item):
    state, keys = item
    return to_hangul(keys) if state == "korean" else keys


def converted_form(item):
    state, keys = item
    return keys if state == "korean" else to_hangul(keys)


def where(item):
    return f"{STATE_NAME[item[0]]} 상태에서 칠 때"


def particle(word, with_final, without_final):
    """Pick a Korean particle by whether the last syllable ends in a consonant (Latin words count as ending in a vowel)."""
    code = ord(word[-1]) - 0xAC00
    has_final = 0 <= code < 11172 and code % 28 != 0
    if with_final == "으로" and has_final and code % 28 == 8:  # ㄹ final takes 로
        has_final = False
    return word + (with_final if has_final else without_final)


# ---------- Catchtype's own word lists ----------

class Lexicon:
    """Catchtype's built-in English and Korean word lists, read from its executable and cached per version."""

    def __init__(self, exe):
        self.english, self.korean = set(), set()
        if exe.exists():
            st = exe.stat()
            cache = CACHE_DIR / f"lexicon-{st.st_size}-{int(st.st_mtime)}.json"
            if cache.exists():
                data = json.loads(cache.read_text(encoding="utf-8"))
                self.english, self.korean = set(data["english"]), set(data["korean"])
            else:
                self._read(exe.read_bytes())
                CACHE_DIR.mkdir(exist_ok=True)
                cache.write_text(json.dumps({"english": sorted(self.english), "korean": sorted(self.korean)},
                                            ensure_ascii=False), encoding="utf-8")
        self.syllables = set("".join(self.korean))
        self.trigrams = {w[i:i + 3] for w in (f"^{w}$" for w in self.english) for i in range(len(w) - 2)}

    def _read(self, blob):
        # Both lists are stored as long runs of words separated by spaces and newlines.
        for m in re.finditer(rb"(?:[a-z'\-]+[ \n]){200,}[a-z'\-]+", blob):
            self.english.update(m.group().decode().split())
        hangul = rb"(?:[\xea-\xed][\x80-\xbf]{2})+"
        for m in re.finditer(rb"(?:" + hangul + rb"[ \n]){200,}" + hangul, blob):
            words = m.group().decode("utf-8", "ignore").split()
            self.korean.update(w for w in words if re.fullmatch(r"[가-힣]+", w))

    def looks_odd_korean(self, hangul):
        return not re.fullmatch(r"[가-힣]+", hangul) or any(ch not in self.syllables for ch in hangul)

    def looks_odd_english(self, keys):
        word = f"^{keys.lower()}$"
        return any(word[i:i + 3] not in self.trigrams for i in range(len(word) - 2))


def guess_add_target(keys, lex):
    """Which language the user wants these keys to become: 'en', 'ko', or None if unclear."""
    hangul = to_hangul(keys)
    en_known, ko_known = keys.lower() in lex.english, hangul in lex.korean
    if en_known != ko_known:
        return "en" if en_known else "ko"
    if en_known:  # a real word on both sides
        return None
    ko_odd, en_odd = lex.looks_odd_korean(hangul), lex.looks_odd_english(keys)
    if ko_odd != en_odd:
        return "en" if ko_odd else "ko"
    return None


def choose(question, options, guess):
    """Show both readings and let the user confirm one; `guess` (a value or None) is what Enter picks."""
    print(question)
    for i, (label, value) in enumerate(options, 1):
        print(f"  {i}) {label}" + ("   ← 추측 (Enter)" if value == guess else ""))
    prompt = "번호 (Enter = 추측, 그 밖 = 취소): " if guess else "번호 (그 밖 = 취소): "
    try:
        answer = input(prompt).strip()
    except EOFError:  # no one to confirm, so write nothing
        raise Stop("확인을 받지 못해 아무것도 바꾸지 않았어요. --en 또는 --ko를 붙이면 묻지 않아요.")
    if answer == "" and guess:
        return guess
    if answer in {str(i) for i in range(1, len(options) + 1)}:
        return options[int(answer) - 1][1]
    raise Stop("아무것도 바꾸지 않았어요.")


def undo_note(words, item):
    count = words.undone.get(item)
    return f"  (되돌린 기록 {count}번)" if count else ""


# ---------- settings.json ----------

ENTRY = {
    "alwaysConvertedWords": re.compile(r"(korean|english)\t([^\t]+)\t(\d+)"),
    "learnedWordDates": re.compile(r"(korean|english)\t([^\t]+)\t(\d+)"),
    "undoneWords": re.compile(r"(\d+)\t(korean|english)\t([^\t]+)"),
}


class Words:
    """The three word lists, keyed by (state, keys), in file order."""

    def __init__(self, path):
        try:
            self.settings = json.loads(path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            raise Stop(f"{path}이 없어요. Catchtype을 한 번 켠 뒤 다시 해 주세요.")
        except json.JSONDecodeError as e:
            raise Stop(f"{path}을 읽지 못했어요({e}). 아무것도 고치지 않았어요.")
        if not isinstance(self.settings, dict):
            raise Stop(f"{path}의 형식이 예상과 달라 아무것도 고치지 않았어요.")
        self.always, self.learned, self.undone = {}, {}, {}
        for name, pattern in ENTRY.items():
            entries = self.settings.get(name, [])
            if not isinstance(entries, list):
                raise Stop(f"{name}의 형식이 예상과 달라 아무것도 고치지 않았어요. Catchtype 업데이트로 바뀌었을 수 있어요.")
            for entry in entries:
                m = pattern.fullmatch(entry) if isinstance(entry, str) else None
                if not m:
                    raise Stop(f"{name}에 예상과 다른 항목이 있어 아무것도 고치지 않았어요: {entry!r}\n"
                               "Catchtype 업데이트로 형식이 바뀌었을 수 있어요.")
                if name == "undoneWords":
                    self.undone[m[2], m[3]] = int(m[1])
                else:
                    (self.always if name == "alwaysConvertedWords" else self.learned)[m[1], m[2]] = int(m[3])

    def is_kept(self, item):
        return item in self.learned or self.undone.get(item, 0) >= UNDOS_TO_LEARN

    def lists(self):
        return {
            "alwaysConvertedWords": [f"{s}\t{k}\t{t}" for (s, k), t in self.always.items()],
            "learnedWordDates": [f"{s}\t{k}\t{t}" for (s, k), t in self.learned.items()],
            "undoneWords": [f"{c}\t{s}\t{k}" for (s, k), c in self.undone.items()],
        }

    def save(self, path):
        settings = {**self.settings, **self.lists()}
        # Same layout Catchtype writes: sorted keys, two-space indent, "key" : value.
        text = json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True, separators=(",", " : "))
        tmp = path.with_name(path.name + ".ct-tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)


def backup(path):
    folder = path.parent / "ct-backups"
    folder.mkdir(exist_ok=True)
    shutil.copy2(path, folder / f"settings-{datetime.now():%Y%m%d-%H%M%S-%f}.json")
    for old in sorted(folder.glob("settings-*.json"))[:-BACKUPS_KEPT]:
        old.unlink()


def snapshot(words):
    SNAPSHOT.write_text(json.dumps(words.lists(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------- the Catchtype process ----------

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def catchtype_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Catchtype.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, errors="replace").stdout
    return [int(row[1]) for row in csv.reader(out.splitlines()) if len(row) > 1 and row[0].lower() == "catchtype.exe"]


def image_path(pid):
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        return Path(buf.value) if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) else None
    finally:
        kernel32.CloseHandle(handle)


def wait_until(condition, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.2)
    return condition()


def stop_catchtype():
    """Quit Catchtype and return its executable path, or None if it wasn't running."""
    pids = catchtype_pids()
    if not pids:
        return None
    exe = image_path(pids[0]) or DEFAULT_EXE
    # Catchtype ignores a normal close request (tested on 0.3.0-beta.9.1), so end it directly.
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    if not wait_until(lambda: not catchtype_pids(), 5):
        raise Stop("Catchtype을 끄지 못했어요. 메뉴에서 'Catchtype 종료'를 누른 뒤 다시 해 주세요.")
    return exe


def start_catchtype(exe):
    # Launch through explorer so Catchtype isn't tied to this terminal's process tree.
    subprocess.run(["explorer.exe", str(exe)])
    if not wait_until(catchtype_pids, 10):
        print(f"Catchtype을 다시 켜지 못했어요. {exe}를 직접 열어 주세요.", file=sys.stderr)


def change(args, edit):
    """Apply `edit(words) -> messages` with Catchtype stopped. An edit that returns no messages changes nothing."""
    path = Path(args.settings)
    messages = edit(Words(path))
    if not messages:
        return
    exe = None if args.no_restart else stop_catchtype()
    try:
        words = Words(path)  # re-read: Catchtype may have saved on its way out
        messages = edit(words)
        if messages:
            backup(path)
            words.save(path)
            if path == SETTINGS:
                snapshot(words)
    finally:
        if exe:
            start_catchtype(exe)
    print("\n".join(messages))


# ---------- commands ----------

def cmd_add(args):
    keys, _ = parse_word(args.word)
    lex = Lexicon(DEFAULT_EXE)
    target = args.target
    if not target:
        hangul, words = to_hangul(keys), Words(Path(args.settings))
        target = choose(f"'{args.word}'를 어느 쪽으로 늘 바꿀까요?", [
            (f"한글 상태에서 친 {hangul} → {keys}" + undo_note(words, ("korean", keys)), "en"),
            (f"영어 상태에서 친 {keys} → {hangul}" + undo_note(words, ("english", keys)), "ko"),
        ], guess_add_target(keys, lex))
    item = ("korean" if target == "en" else "english", keys)

    def edit(words):
        if item in words.always:
            print(f"이미 늘 바꿀 말이에요: {typed_form(item)} → {converted_form(item)} ({where(item)})")
            return []
        messages = [f"늘 바꿀 말에 더했어요: {typed_form(item)} → {converted_form(item)} ({where(item)})"]
        was_kept = words.is_kept(item)
        if forget_undos(words, item):
            messages.append("  그대로 둘 말에서는 뺐어요." if was_kept else "  되돌린 기록은 지웠어요.")
        words.always[item] = int(time.time())
        return messages + other_language_warning(item, lex)

    change(args, edit)


def forget_undos(words, item):
    """Drop the undo count and learned date of `item`; True if there was either."""
    had_undos = words.undone.pop(item, None) is not None
    had_date = words.learned.pop(item, None) is not None
    return had_undos or had_date


def other_language_warning(item, lex):
    """Catchtype's own caution: the typed form is also a real word in the language it was typed in."""
    typed, converted = typed_form(item), converted_form(item)
    language = {"korean": "한국어", "english": "영어"}[item[0]]
    if typed in lex.korean if item[0] == "korean" else typed.lower() in lex.english:
        return [f"  주의: {particle(typed, '은', '는')} {language} 낱말이기도 해요. "
                f"{language}로 칠 때도 늘 {particle(converted, '으로', '로')} 바뀌어요."]
    return []


def cmd_keep(args):
    keys, script = parse_word(args.word)
    target = args.target
    if not target:
        # Guess the state the user has already been undoing; otherwise keep the word as written.
        hangul, words = to_hangul(keys), Words(Path(args.settings))
        undone = [t for t, s in (("en", "english"), ("ko", "korean")) if (s, keys) in words.undone]
        guess = undone[0] if len(undone) == 1 else ("en" if script == "latin" else "ko")
        target = choose(f"'{args.word}'를 어떻게 그대로 둘까요?", [
            (f"영어 상태에서 친 {particle(keys, '을', '를')} {particle(hangul, '으로', '로')} 안 바꾸기"
             + undo_note(words, ("english", keys)), "en"),
            (f"한글 상태에서 친 {particle(hangul, '을', '를')} {particle(keys, '으로', '로')} 안 바꾸기"
             + undo_note(words, ("korean", keys)), "ko"),
        ], guess)
    item = ("english" if target == "en" else "korean", keys)

    def edit(words):
        if words.is_kept(item) and item not in words.always:
            print(f"이미 그대로 둘 말이에요: {typed_form(item)} ({where(item)})")
            return []
        messages = [f"그대로 둘 말에 더했어요: {converted_form(item)} 대신 {typed_form(item)} 그대로 둬요 ({where(item)})"]
        if words.always.pop(item, None) is not None:
            messages.append("  늘 바꿀 말에서는 뺐어요.")
        words.undone[item] = max(words.undone.get(item, 0), UNDOS_TO_LEARN)
        words.learned.setdefault(item, int(time.time()))
        return messages

    change(args, edit)


def cmd_forget(args):
    keys, _ = parse_word(args.word)

    def edit(words):
        messages = []
        for state in ("korean", "english"):
            item = (state, keys)
            if words.always.pop(item, None) is not None:
                messages.append(f"늘 바꿀 말에서 지웠어요: {typed_form(item)} → {converted_form(item)} ({where(item)})")
            was_kept = words.is_kept(item)
            if forget_undos(words, item):
                kind = "그대로 둘 말" if was_kept else "배우는 중인 말"
                messages.append(f"{kind}에서 지웠어요: {typed_form(item)} ({where(item)})")
        return messages

    before = Words(Path(args.settings))
    if not any((s, keys) in d for s in ("korean", "english") for d in (before.always, before.learned, before.undone)):
        print(f"목록에 없는 말이에요: {args.word} (키: {keys})")
        return
    change(args, edit)


def width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def show(rows):
    column = max((width(left) for left, _ in rows), default=0) + 2
    for left, right in rows:
        print(f"  {left}{' ' * (column - width(left))}{right}")


def cmd_list(args):
    words = Words(Path(args.settings))
    if Path(args.settings) == SETTINGS:
        snapshot(words)
    kept = [item for item in {**words.undone, **words.learned} if words.is_kept(item)]
    learning = [item for item, count in words.undone.items() if count < UNDOS_TO_LEARN and item not in words.learned]

    print(f"늘 바꿀 말 ({len(words.always)})")
    show([(f"{typed_form(i)} → {converted_form(i)}", where(i)) for i in words.always])
    print(f"그대로 둘 말 ({len(kept)})")
    show([(f"{typed_form(i)}  (→ {converted_form(i)} 안 바꿈)", where(i)) for i in kept])
    print(f"배우는 중 ({len(learning)}) - 같은 말을 {UNDOS_TO_LEARN}번 되돌리면 그대로 둘 말이 돼요")
    show([(f"{typed_form(i)} → {converted_form(i)}  ({words.undone[i]}/{UNDOS_TO_LEARN})", where(i)) for i in learning])


EXAMPLES = """\
예:
  ct add 채며쇅       안 바뀐 말을 늘 바꿔요 (ct add coauthor 도 같아요)
  ct keep wls         바뀌면 안 되는 말을 친 그대로 둬요
  ct forget absy      어느 목록에서든 그 말을 지워요 (잘못 배운 말, 잘못 더한 말)
  ct list             지금 목록을 보여 줘요

add와 keep은 두 가지 해석을 보여 주고 추측한 쪽을 Enter로 확인받아요.
--en(영어가 남게) 또는 --ko(한글이 남게)를 붙이면 묻지 않고 바로 써요.
바꿀 때마다 Catchtype을 잠깐 껐다 켜요. 고치기 전 설정은 %APPDATA%\\Catchtype\\ct-backups에 남아요.
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    hidden = argparse.ArgumentParser(add_help=False)
    hidden.add_argument("--settings", default=str(SETTINGS), help=argparse.SUPPRESS)
    hidden.add_argument("--no-restart", action="store_true", help=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(prog="ct", description="Catchtype 단어 목록을 고쳐요.", epilog=EXAMPLES,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", metavar="명령")
    for name, run, help_text, en_help, ko_help in [
        ("add", cmd_add, "바뀌어야 하는데 안 바뀌는 말을 늘 바꿔요",
         "영어로 바뀌게 (한글 상태에서 친 말)", "한글로 바뀌게 (영어 상태에서 친 말)"),
        ("keep", cmd_keep, "바뀌면 안 되는데 바뀌는 말을 친 그대로 둬요",
         "영어 그대로 두기 (영어 상태에서 친 말)", "한글 그대로 두기 (한글 상태에서 친 말)"),
        ("forget", cmd_forget, "어느 목록에서든 그 말을 지워요", None, None),
    ]:
        p = sub.add_parser(name, parents=[hidden], help=help_text, description=help_text)
        p.add_argument("word", metavar="낱말", help="한글 모양(채며쇅)이나 영문 키(coauthor)")
        if en_help:
            target = p.add_mutually_exclusive_group()
            target.add_argument("--en", dest="target", action="store_const", const="en", help=en_help)
            target.add_argument("--ko", dest="target", action="store_const", const="ko", help=ko_help)
        p.set_defaults(run=run, target=None)
    sub.add_parser("list", parents=[hidden], help="지금 목록을 보여 줘요").set_defaults(run=cmd_list)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0
    try:
        args.run(args)
    except Stop as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
