def is_prime(n):
    if n <= 1:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True

start = int(input("Enter start of range: "))
end = int(input("Enter end of range: "))

print("Prime numbers between", start, "and", end, "are:")
for num in range(start, end + 1):
    if is_prime(num):
        print(num, end=" ")