import numpy as np
import itertools as it
import time, copy, math

import Database as db

class MultiIndex :

    def __init__(self, idxs=[]) :
        self.d = len(idxs)
        self.idxs = idxs

    def __getitem__(self, i) :
        return self.idxs[i]

    def asList(self) :
        return self.idxs

    def print(self) :
        print(self.idxs)

class MultiIndexCompressed :

    def __init__(self, ilist=[]) :
        self.d = len(ilist)
        self.nzs = it.filterfalse(lambda x : x[1]==0, enumerate(ilist)) #TODO binary search tree

    def __getitem__(self, i) :
        if i == -1 :
            return self.nzs[-1][1] if self.nzs[-1][0] == self.de else 0
        return next((nz[1] for nz in self.nzs if nz[0] == i), 0)

    def asList(self) :
        l = [0] * self.d
        for nz in self.nzs :
            l[nz[0]] = nz[1]
        return l

    def print(self) :
        print(self.asList())

# ---------- Indexsets --------------------

class MultiIndexSet :

    def __init__(self, *, name, dim, save=True, verbose=False) :
        start = time.process_time()
        self.name = name
        self.idxs = []
        self.dim = dim
        self.maxOrders = [0] * self.dim
        self.verbose = verbose
        self.setup()
        self.maxDegree = max(self.maxOrders)
        self.cardinality = len(self.idxs)

        if save :
            self.dbo.ctime = time.process_time() - start
            self.dbo.size = self.cardinality
            self.dbo.save()

    def setup1d(self, k) :
        if self.verbose : print('setup 1D')
        assert(len(self.idxs) == 0)
        for idx in range(k+1) :
            self.add(MultiIndex([idx]))

    def __getitem__(self, i) : return self.idxs[i]

    def add(self, idx: MultiIndex) :
        self.idxs.append(idx)
        self.maxOrders = [max(i, j) for i, j in zip(self.maxOrders, idx)]

    def size(self) : return len(self.idxs)

    def asLists(self) : return [i.asList() for i in self.idxs]

    def print(self) :
        for idx in self.idxs :
            idx.print()

    def deleteDbo(self) :
        if hasattr(self, 'dbo') : self.dbo.delete_instance()


class TensorProductSet(MultiIndexSet) :

    def __init__(self, *, dim, order, save=True, verbose=False) :
        self.order = order
        if save :
            self.dbo, _ = db.MultiIndexSetDBO.get_or_create(dim=dim, mode='tensorproduct', order=order)
        MultiIndexSet.__init__(self, name='tensorproduct', dim=dim, save=save, verbose=verbose)

    def setup(self) :
        if self.verbose : print('setup TensorProductSet')
        assert(len(self.idxs) == 0)
        for idx in it.product(range(self.order+1), repeat=self.dim) :
            self.add(MultiIndex(idx))


class TotalDegreeSet(MultiIndexSet) :

    def __init__(self, *, dim, order, save=True, verbose=False) :
        self.order = order
        if save :
            self.dbo, _ = db.MultiIndexSetDBO.get_or_create(dim=dim, mode='totaldegree', order=order)
        MultiIndexSet.__init__(self, name='totaldegree', dim=dim, save=save, verbose=verbose)

    def setup(self) :
        if self.verbose : print('setup TotalDegreeSet')
        assert(len(self.idxs) == 0)
        for idx in it.filterfalse(lambda x : sum(x) > self.order,
                                  it.product(range(self.order+1), repeat=self.dim)) :
            self.add(MultiIndex(idx))


class SparseSet(MultiIndexSet) :

    def __init__(self, *, weights, threshold, save=True, verbose=False) :
        assert(weights[0] < 1)
        for i in range(len(weights)-1) :
            assert(weights[i] >= weights[i+1])
        self.weights = weights #TODO assert monotonicity?
        self.threshold = threshold
        if save :
            self.dbo, _ = db.MultiIndexSetAnisotropicDBO.get_or_create(
                dim=len(weights), weight=db.to_string(weights), thresh=threshold)
        MultiIndexSet.__init__(self, dim=len(weights), name='sparse', save=save, verbose=verbose)


    @classmethod
    def fromId(self, id) :
        dbo = db.MultiIndexSetAnisotropicDBO.get_by_id(id)
        thresh = None
        if isinstance(dbo.thresh, float) :
            thresh = dbo.thresh
        else :
            thresh = db.fr_string(dbo.thresh)[0]
        return SparseSet(weights=db.fr_string(dbo.weight), threshold=thresh)

    def setup(self) :
        if self.verbose : print('setup SparseSet')
        assert(len(self.idxs) == 0)
        base = np.zeros((len(self.weights),), dtype=np.int64)
        self.add(MultiIndex(base))

        d = 0
        while d < base.size :
            d = 0
            nextIndex = self.getNextIndex(base, d)
            while not self.isFeasible(nextIndex) :
                if base[d] != 0 :
                    base[d] = 0
                    d += 1
                elif np.sum(base) > 0 :
                    d = 0
                    while d < base.size - 1 and base[d] == 0 :
                        d += 1
                else :
                    return

                if d >= base.size :
                    return
                nextIndex = self.getNextIndex(base, d)

            base[d] += 1
            self.add(MultiIndex(nextIndex))

    def isFeasible(self, idx) :
        mapidx = lambda i : self.weights[i[0]]**i[1]
        res = math.prod(map(mapidx  , enumerate(idx)))
        #print(idx, 'res ', res, 'thresh', self.threshold, res > self.threshold)
        return res > self.threshold

    def getNextIndex(self, idx, d) :
        idx = copy.deepcopy(idx)
        idx[d] += 1
        return idx

    @classmethod
    def withSize(cls, *, weights, n, t=1, save=False, verbose=False) :
        tupper = None
        tlower = None
        m = SparseSet(weights=weights, threshold=t, save=False, verbose=verbose)
        niter = 0
        while m.cardinality != n :
            niter += 1
            if niter > 100 :#and m.cardinality > .9 * n and m.cardinality < 1.1 * n :
                break
            if verbose : print(n, m.cardinality, tlower, t, tupper)
            if m.cardinality < n :
                tupper = t
                t = t/2 if tlower == None else (tlower + t)/2
                #m.deleteDbo()
                m = SparseSet(weights=weights, threshold=t, save=False, verbose=verbose)
            elif m.cardinality > n :
                tlower = t
                t = t*2 if tupper == None else (tupper + t)/2
                #m.deleteDbo()
                m = SparseSet(weights=weights, threshold=t, save=False, verbose=verbose)
        #print(m.cardinality, n, t, m.threshold)
        return SparseSet(weights=weights, threshold=t, save=save, verbose=verbose)

# ---------- Trees --------------------

class MultiIndexTreeNode :

    def __init__(self, idx: int, mlist: list) :
        self.idx = idx
        self.val = None
        self.children = []
        if len(mlist[0][1]) > 0 :
            mlist = sorted(mlist, key=lambda l : l[1][-1])
            for i, l in it.groupby(mlist, lambda l : l[1][-1]) :
                self.children.append(MultiIndexTreeNode(i, [(li[0],li[1][:-1]) for li in l]))

        else :
            self.val = mlist[0][0]

    def print(self) :
        print(self.idx, self.val, len(self.children))

class MultiIndexTree :

    def __init__(self, surrogate) :
        self.maxOrders = surrogate.multis.maxOrders
        self.root = MultiIndexTreeNode(None, list(zip(surrogate.coeffs, surrogate.multis.asLists())))
        self.nodes = [[]] * surrogate.multis.dim + [[self.root]]
        for i in range(surrogate.multis.dim, 0, -1) :
            self.nodes[i-1] = [*it.chain.from_iterable([n.children for n in self.nodes[i]])]

    def __getitem__(self, i) :
        return self.nodes[i]


if __name__ == '__main__' :

    m = SparseSet.withSize(weights=[.6], n=5, t=32, save=True)
    assert(m.cardinality == 5)
    m.deleteDbo()

    m = SparseSet.withSize(weights=[.6, .4], n=27, t=60, save=True)
    assert(m.cardinality == 27)
    m.deleteDbo()

    m = SparseSet.withSize(weights=[.6, .4, .1, .01], n=31, t=60, save=True)
    assert(m.cardinality == 31)
    m.deleteDbo()

    m = TensorProductSet(dim=1, order=5, save=True)
    assert(m.cardinality == 6)
    m.deleteDbo()

    m = TensorProductSet(dim=2, order=5)
    assert(m.cardinality == 36)
    m.deleteDbo()

    m = TensorProductSet(dim=3, order=5)
    assert(m.cardinality == 216)
    m.deleteDbo()

    m = TotalDegreeSet(dim=1, order=5)
    assert(m.cardinality == 6)
    m.deleteDbo()

    m = TotalDegreeSet(dim=2, order=5)
    assert(m.cardinality == 21)
    m.deleteDbo()

    m = TotalDegreeSet(dim=3, order=5, save=True)
    assert(m.cardinality == 56)
    m.deleteDbo()