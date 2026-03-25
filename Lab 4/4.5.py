def second_smallest(nums):
    unique_nums = sorted(set(nums))
    if len(unique_nums) < 2:
        return None
    return unique_nums[1]

def second_largest(nums):
    unique_nums = sorted(set(nums))
    if len(unique_nums) < 2:
        return None
    return unique_nums[-2]

n = int(input("How many elements? "))
lst = []
for _ in range(n):
    lst.append(int(input("Enter element: ")))

print("List:", lst)

ss = second_smallest(lst)
sl = second_largest(lst)

if ss is None or sl is None:
    print("Need at least two distinct elements")
else:
    print("Second smallest =", ss)
    print("Second largest =", sl)