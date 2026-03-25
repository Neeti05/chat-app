def read_matrix(rows, cols, name):
    print(f"Enter elements of matrix {name}:")
    mat = []
    for i in range(rows):
        row = []
        for j in range(cols):
            val = int(input(f"Element [{i}][{j}]: "))
            row.append(val)
        mat.append(row)
    return mat

def add_matrices(a, b):
    rows = len(a)
    cols = len(a[0])
    result = []
    for i in range(rows):
        row = []
        for j in range(cols):
            row.append(a[i][j] + b[i][j])
        result.append(row)
    return result

def print_matrix(mat):
    for row in mat:
        for val in row:
            print(val, end=" ")
        print()

r = int(input("Enter number of rows: "))
c = int(input("Enter number of columns: "))

m1 = read_matrix(r, c, "A")
m2 = read_matrix(r, c, "B")

sum_mat = add_matrices(m1, m2)

print("Matrix A + B is:")
print_matrix(sum_mat)