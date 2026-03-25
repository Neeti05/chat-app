# User-defined function for Simple Interest
def simple_interest(p, r, t):
    return (p * r * t) / 100

# User-defined function for Compound Interest
def compound_interest(p, r, t):
    return p*((1 + r / 100)**t)-p


# User input
principal = float(input("Enter principal amount: "))
rate = float(input("Enter rate of interest: "))
time = float(input("Enter time (in years): "))

# Function calls
si = simple_interest(principal, rate, time)
ci = compound_interest(principal, rate, time)

# Output
print("Simple Interest:", si)
print("Compound Interest:", ci)
