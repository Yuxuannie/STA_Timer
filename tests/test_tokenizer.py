"""R42: the regex tokenizer in liberty.py emits exactly the stream of the character loop it
replaced (kept below as `_tokenize_reference`, verbatim), on the libraries, on every Liberty
text the existing tests parse, on the tokenizer's own error cases and on random texts; and
tools/bench_parse.py runs."""
import io
import os
import random
import subprocess
import sys
import tempfile
import unittest

from sta_toy import StaError, liberty

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PUNCT = liberty._PUNCT


def _continuation_end(text, i):
    """If text[i] is a backslash ending its line, return the index after the newline."""
    j = i + 1
    while j < len(text) and text[j] in " \t\r":
        j += 1
    if j < len(text) and text[j] == "\n":
        return j + 1
    return None


def _tokenize_reference(text, filename):
    """The P1 character-loop tokenizer, kept verbatim as the reference for R42."""
    tokens = []
    i, line, n = 0, 1, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif c == "\\":
            j = _continuation_end(text, i)
            if j is None:
                raise StaError(filename, line, "unexpected '\\'")
            line += 1
            i = j
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise StaError(filename, line, "unterminated comment")
            line += text.count("\n", i, end)
            i = end + 2
        elif c == '"':
            start = line
            chars = []
            i += 1
            while True:
                if i >= n:
                    raise StaError(filename, start, "unterminated string")
                c = text[i]
                if c == '"':
                    i += 1
                    break
                if c == "\\":
                    j = _continuation_end(text, i)
                    if j is not None:
                        line += 1
                        i = j
                        continue
                if c == "\n":
                    line += 1
                chars.append(c)
                i += 1
            tokens.append(("str", "".join(chars), start))
        elif c in _PUNCT:
            tokens.append((c, c, line))
            i += 1
        else:
            j = i
            while (j < n and not text[j].isspace() and text[j] not in _PUNCT + '"\\'
                   and not text.startswith("/*", j)):
                j += 1
            tokens.append(("word", text[i:j], line))
            i = j
    tokens.append(("eof", "", line))
    return tokens


def _run(tokenize, text):
    """The token list, or the error as (file, line, message)."""
    try:
        return list(tokenize(text, "t.lib"))
    except StaError as e:
        return ("error", e.file, e.line, e.message)


class TokenizerTests(unittest.TestCase):

    def assertSameStream(self, text):
        self.assertEqual(_run(liberty._tokenize, text), _run(_tokenize_reference, text), repr(text[:200]))

    def test_libraries(self):
        paths = [os.path.join(ROOT, "data", n) for n in ("toy.lib", "toy2.lib")]
        with tempfile.TemporaryDirectory() as tmp:
            psff = os.path.join(tmp, "toy2_psff.lib")
            with open(psff, "w") as f:
                subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gen_toy2_lib.py"), "--time", "ps",
                                "--cap", "ff", "--suffix", "_P"], check=True, cwd=ROOT, stdout=f)
            paths.append(psff)
            for p in paths:
                with open(p) as f:
                    text = f.read()
                with self.subTest(lib=os.path.basename(p)):
                    self.assertSameStream(text)
                    self.assertGreater(len(_run(liberty._tokenize, text)), 1000)

    def test_texts_of_the_existing_tests(self):
        # Run the Liberty-parsing test modules with a recorder in place of the tokenizer: every
        # text they parse (their error cases included) is then compared stream for stream.
        import test_graph
        import test_liberty
        import test_lookup
        seen = []
        real = liberty._tokenize

        def record(text, filename):
            seen.append(text)
            return real(text, filename)
        liberty._tokenize = record
        try:
            suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m)
                                       for m in (test_liberty, test_graph, test_lookup))
            result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        finally:
            liberty._tokenize = real
        self.assertTrue(result.wasSuccessful())
        self.assertGreater(len(seen), 10)
        for text in seen:
            self.assertSameStream(text)

    def test_error_cases(self):
        cases = {
            "library (a) { /* never closed\n": (1, "unterminated comment"),
            'library (a) {\n  s : "open\n\n': (2, "unterminated string"),
            "library (a) {\n\n  x : 1 \\ y;\n}": (3, "unexpected '\\'"),
            "a \\": (1, "unexpected '\\'"),
        }
        for text, (line, message) in cases.items():
            with self.subTest(text=text):
                self.assertSameStream(text)
                self.assertEqual(_run(liberty._tokenize, text), ("error", "t.lib", line, message))

    def test_edge_cases(self):
        for text in ["", "\n\n", "a/b c/ d /* x\n y */ e", 'k : "a\\\n b" ;', 'k : "a\\ b" ;',
                     "a \\ \t\r\n b", "a\r\nb", "a\u00a0b\x0bc\x1cd\u2028e", "x/*/y*/z", '"" ""', "é : 1;"]:
            with self.subTest(text=text):
                self.assertSameStream(text)

    def test_random_texts(self):
        pieces = ["a", "b1", "1.5e-3", " ", "\t", "\n", "\r", "(", ")", "{", "}", ":", ";", ",", '"',
                  "\\", "/", "*", "/*", "*/", "\\\n", "\\ \t\n", "\u00a0", "\x0b", "\x85", "é"]
        rng = random.Random(1)
        for _ in range(3000):
            self.assertSameStream("".join(rng.choice(pieces) for _ in range(rng.randint(0, 40))))


class BenchParseTests(unittest.TestCase):

    def test_runs(self):
        out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "bench_parse.py"),
                              os.path.join(ROOT, "data", "toy2.lib"), "--repeat", "2"],
                             check=True, stdout=subprocess.PIPE, universal_newlines=True).stdout
        self.assertRegex(out, r"toy2\.lib: \d+ bytes, 2 runs, best \d+\.\d{3} s, mean \d+\.\d{3} s, peak RSS \d+\.\d MB\n$")


if __name__ == "__main__":
    unittest.main()
