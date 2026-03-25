def palindrome(s):
    s = s.lower().replace(" ", "")
    return s == s[::-1]

text = input("Enter a string: ")
if palindrome(text):
    print("Palindrome")
else:
    print("Not Palindrome")