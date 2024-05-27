import math
import numpy as np
from scipy.special import legendre
from numpy.polynomial.legendre import legvander


def get_polys(m) :
    return [legendre(i)*np.sqrt((2*i + 1)/2) for i in range(m)]


def get_integrated_products(m, x) :

    p_x = legvander(np.array([x]), m+2)[0].T
    d_x = np.zeros(p_x.shape)
    d_x[1] = 1
    for n in range(2, len(p_x)) :
        d_x[n] = ((2*n-1) * x * d_x[n-1] - n * d_x[n-2])/(n-1)

    normalization_weights = [np.sqrt((2*i + 1)/2) for i in range(len(p_x))]

    p_x = np.multiply(p_x, normalization_weights)
    d_x = np.multiply(d_x, normalization_weights)

    res = np.zeros((m+1,m+1))
    range_list = np.array([i for i in range(m+1)])

    # fill upper and lower triangle
    for i in range(m+1) :
        res[i,i+1:] = ((1-x**2)
                       * (p_x[i]*d_x[i+1:m+1] - p_x[i+1:m+1]*d_x[i])
                       / (i+range_list[i+1:]+1) / (i-range_list[i+1:]))
        res[i+1:,i] = res[i,i+1:]

    # fill diagonal
    res[0,0] = (x + 1)/2
    res[1,1] = (x**3 + 1)/2
    for i in range(2, m) :
        res[i,i] = (res[i-1,i-1]
                    + res[i+1,i-1] * (i+1) * np.sqrt(2*i - 1) / i / np.sqrt(2*i + 3)
                    - res[i,  i-2] * (i-1) * np.sqrt(2*i + 1) / i / np.sqrt(2*i - 3))

    return p_x[:-1], res[:-1, :-1]


def evaluate_basis(x, multis, mode='') :
    """
    x : np.array with shape=(d,n)
    """

    if mode == 'old' :
        indices = multis.asLists()
        m = multis.size()
        assert m == len(indices)

        van = legvander(x, multis.maxDegree)  # shape = (d, n, max(indices)+1)

        map1 = lambda l : np.sqrt((2*l + 1)/2)  # legvander is normalized to P(1)=1, we need normalization wrt L2
        map2 = lambda q : van[q[0],:,q[1]]

        return np.array([math.prod(map(map1, idx))*math.prod(map(map2, enumerate(idx))) for idx in indices]).T

    I = np.array(multis.asLists())  # shape = (d, n)
    V = legvander(x, multis.maxDegree)  # shape = (d, n, multis.maxDegree+1)
    R = np.prod([V[i,:,I[:,i]] for i in range(multis.dim)], axis=0).T  # shape = (n,m)
    return np.multiply(R, multis.getWeightsForLegendreL2Normalization())
