def longest_word(sentence):
    words = sentence.split()
    if not words:
        return ""
    long = words[0]
    for w in words[1:]:
        if len(w) > len(long):
            long = w
    return long

s = input("Enter a sentence: ")
lw = longest_word(s)
if lw == "":
    print("No words found")
else:
    print("Longest word:", lw)
    print("Length:", len(lw))