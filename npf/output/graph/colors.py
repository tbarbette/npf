def lighter(c, p, n):
    n = n / 255.
    return tuple(min(1,max(0,a * p + (1-p) * n)) for a in c)