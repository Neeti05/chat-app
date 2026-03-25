def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b != 0:
        return a / b
    else:
        return "Error: Division by zero"


# User input
a = float(input("Enter first number: "))
b = float(input("Enter second number: "))
op = input("Enter operator (+, -, *, /): ")

# Calling user-defined functions
if op == '+':
    print("Result:", add(a, b))
elif op == '-':
    print("Result:", subtract(a, b))
elif op == '*':
    print("Result:", multiply(a, b))
elif op == '/':
    print("Result:", divide(a, b))
else:
    print("Invalid operator")
