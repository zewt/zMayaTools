#!/usr/bin/python
import math 
from pprint import pprint


#def cholesky(L):
#    L = [[0] * len(L) for _ in range(len(L))]
# 
#    for i in range(len(L)):
#        for j in range(i+1):
#            s = 0;
#
#            for k in range(j):
#                s += L[i][k] * L[j][k]
#            if i == j:
#                v = math.sqrt(L[i][i] - s)
#            else:
#                v = (1.0 / L[j][j] * (L[i][j] - s))
#            L[i][j] = v
# 
#    return L
 
 
#def cholesky(L):
#    L = [[0.0] * len(L) for _ in range(len(L))]
#    for i in range(len(L)):
#        for j in range(i+1):
#            s = sum(L[i][k] * L[j][k] for k in range(j))
#            L[i][j] = math.sqrt(L[i][i] - s) if (i == j) else \
#                      (1.0 / L[j][j] * (L[i][j] - s))
#    return L

class SolveFailedError(ValueError):
    pass

# Ernesto P. Adorio, Ph.D.  ernesto.adorio@gmail.com
# UPDEPP at Clark Field, Pampanga
def Cholesky(L, ztol= 1.0e-5):
    """
    Computes the upper triangular Cholesky factorization of  
    L positive definite matrix L.
    """
    # Forward step for symmetric triangular t.
    t = [[0]*len(L) for _ in range(len(L))]
    for i in range(len(L)):
        s = sum((t[k][i])**2 for k in range(i))
        d = L[i][i] - s
        if abs(d) < ztol:
            d = 0

        try:
            t[i][i] = math.sqrt(d)
        except ValueError:
            raise SolveFailedError('Matrix not positive-definite')

        try:
            for j in range(i+1, len(L)):
                S = sum([t[k][i] * t[k][j] for k in range(i)])
                if abs(S) < ztol:
                    S = 0.0

                t[i][j] = (L[i][j] - S)/t[i][i]
        except ZeroDivisionError:
            raise SolveFailedError('Zero diagonal')
    return t

#def go1():
#    m1 = [[25, 15, 5],
#          [15, 18,  0],
#          [5,  0, 11]]
#    pprint(cholesky(m1))
#    print
#    f()
# 
#    m2 = [[18, 22,  54,  42],
#          [22, 70,  86,  62],
#          [54, 86, 174, 134],
#          [42, 62, 134, 106]]
#    pprint(cholesky(m2), width=120)


def transpose(A):
    C = [[0]*len(A) for _ in range(len(A[0]))]

    for i in range(len(A)):
        for j in range(len(A[i])):
            C[j][i] = A[i][j]

    return C
 
def forward_solve(A, b):
    """Forward solve the lower triangular system Ax = b"""
    x = [0]*len(A)

    for i in range(len(A)):
        x[i] = b[i]

        for k in range(i):
            x[i] -= A[i][k] * x[k]

        try:
            x[i] /= A[i][i]
        except ZeroDivisionError:
            raise SolveFailedError('No solution')

    return x


def backtrack_solve(A, b):
    """Backtrack solve the upper triangular system Ax = b"""
    x = [0]*len(A)

    for i in reversed(range(len(A))):
       x[i] = b[i]

       for k in reversed(range(i+1, len(A))):
           x[i] -= A[i][k] * x[k]

       x[i] /= A[i][i]

    return x

def solve(A, b):
    """
    Solve Ab=x for b, where A is a matrix and b is a vector.
    """
    print_matrix(A)
    upper = Cholesky(A)
    # print 'upper'
    # print_matrix(upper)
    lower = transpose(upper)
    # print 'lower'
    # print_matrix(lower)
    values = forward_solve(lower, b)
    return backtrack_solve(upper, values)

def dot(mat, vec):
    result = [0]*len(mat)
    assert len(mat[0]) == len(vec)
    for values in range(len(mat)):
        for x in range(len(mat[values])):
            result[values] += mat[values][x]*vec[x]
            pass
    return result


def mult(lhs, rhs):
    a = len(lhs)
    b = len(rhs[0])
    result = [[0]*b for _ in range(a)]
    for c in range(a):
        for d in range(b):
            s = 0
            for k in range(len(rhs)):
                s += lhs[c][k]*rhs[k][d]
 
            result[c][d] = s
    return result

def print_matrix(m):
    for row in m:
        for col in row:
            print('%5.1f' % col)

class rbf(object):
    @staticmethod
    def const(v):
        return 1

    @staticmethod
    def linear(r):
        return math.sqrt(r)
    #        pos = (v[0]-center[0], v[1]-center[1], v[2]-center[2])
    #        return math.sqrt(pos[0]*pos[0]+pos[1]*pos[1]+pos[2]*pos[2])

    @staticmethod
    def sq(v):
        return v*v

    @staticmethod
    def gaussian(r):
        return math.exp(-1.0*r)

    @property
    def solvable(self):
        return self.result is not None

    def __init__(self, values, points):
        self.points = points
        #self.func = self.gaussian
        self.func = self.linear
        self.result = None

        assert len(values) == len(points)

        # Solving will always fail if we have less than two values.
        if len(points) <= 1:
            return

        X = []
        for i in range(len(points)):
            item = []
            for j in range(len(points)):
                total_squared = 0
                for channel in range(len(points[i])):
                    delta = points[i][channel] - points[j][channel]
                    total_squared += delta*delta
                item.append(self.func(total_squared))
            X.append(item)
#            print 'append', item

        # print 'X:'
        # print_matrix(X)

        Xt = transpose(X)
        # print 'Xt:'
        # print_matrix(Xt)

        XtX = mult(Xt, X)
        # print 'XtX'
        # print_matrix(XtX)

        Xty = dot(Xt, values)
        # print 'Xty', Xty

        try:
            self.result = solve(XtX, Xty)
            # print 's:', self.result
        except SolveFailedError:
            self.result = None

    def eval(self, t):
        if self.result is None:
            return 0

        out = 0
        for i in range(len(self.result)):
            total_squared = 0
            for channel in range(len(self.points[i])):
                delta = t[channel] - self.points[i][channel]
                total_squared += delta*delta

            out += self.result[i] * self.func(total_squared)

        return out

def xgo():
    points = [(0, 0, 0),]
#    points = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    #values = (0, 90, 180)
#    points = [(0, 1)]
    values = (10,)

    solver = rbf(values, points)
    # print solver.solvable

    print(solver.eval((0, 0, 0)))

if __name__ == "__main__":
    xgo()

# https://github.com/jpaasen/cos/blob/master/framework/cholesky.py
# The MIT License (MIT)
# 
# Copyright (c) 2014 Jon Petter Asen
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
