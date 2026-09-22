from asr import WordFinalizer

f = WordFinalizer()
assert f.partial("machine") == []
assert f.partial("machine lear") == ["machine"]
assert f.partial("machine learning meta") == ["learning"]
assert f.final("machine learning metaphor") == ["metaphor"]
assert f.emitted == []  # resets after final
print("ok")
