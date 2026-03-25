def factorial(n):
    fact = 1
    for i in range(1,n+1):
        fact *=i
    return fact

n = int(input("Enter non negative integer: "))
if n<0:
    print ("Factorial not defined for negative numbers")
else:
    print (factorial(n))