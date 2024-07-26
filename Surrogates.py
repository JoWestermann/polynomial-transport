import numpy as np
import time

import util
import MultiIndex as mi
import Database as db
import Densities as de
import Evaluation as ev


class Legendre :
    """ Surrogate $\\tilde f$ of a (unnormalized density) function $f : [-1,1]^d \\to [0,\\infty)$. """

    def __init__(self, *, target: de.TargetDensity, multis: mi.MultiIndexSet, mode='wls', dist='cheby',
                 resample=False, compute_condnr=False, verbose=0, save=False) :
        """
        Parameters:
        -----------
        target : TargetDensity
        multis : MultiIndexSet
            The multi-index set $\\Lambda$ defining the polynomial ansatz space in which the approximation to
            $\\sqrt{f}$ is constructed.
        mode : str
            Approximation method determining the number of support points in terms of m := multis.cardinality.
            Valid choices are
            - 'ip' : interpolation, uses m support points
            - 'wls' : weighted least squares, uses 10 * m * int(log(m)) support points
            - 'ls' : least squares, not recommended since it uses m**2 support points
        dist : str
            Distribution of support points. Valid choices are
            - 'leja' : Deterministic Leja points. Only works with mode='ip'.
            - 'leggaus' : Deterministic Legendre Gauss points. Only works with mode='ip'.
            - 'cheby' : Random points distributed according to the Chebychev measure.
            - 'cheby_ss' : As 'cheby', but the set of points (and thus the number of necessary density evaluations)
                           is reduced via the BSS algorithm (see https://arxiv.org/abs/2202.12625).
                           Requires installation of https://github.com/felixbartel/BSSsubsampling.jl.
                           Only works with mode='wls'.
            - 'christoffel' : Random points distributed according to the Christoffel measure.
                              Construction is computationally expensive.
            - 'uni' : Uniformly distributed points, not recommended.
        resample : bool
            Specifies whether to resample the WLS points until the corresponding Gramian matrix G satisfies ||G-I|| <= .5.
        compute_cond : bool
            Specifies whether to compute the condition number of G-I even if resample==False.
        """
        if verbose > 0: print('\t Surrogate / ', end='')
        util.require.equal(multis.dim, target.dim, 'multis.dim', 'target.dim')
        assert mode in ['ip', 'wls', 'ls']
        assert dist in ['leja', 'leggaus', 'cheby', 'cheby_ss', 'christoffel', 'uni']
        self.multis = multis
        self.target = target
        self.coeffs = None
        self.cond_nr = -1
        self.dim = multis.dim

        if save :
            self.dbo, isnew = db.SurrogateDBO.get_or_create(
                target=target.name, target_id=None if not hasattr(target, 'dbo') else target.dbo.id,
                multis=multis.name, multis_id=multis.dbo.id, mode=mode, dist=dist)
            if not isnew and self.dbo.coeffs is not None :
                if verbose > 0: print('loading / ', end='')
                self.coeffs = db.fr_string(self.dbo.coeffs)

        if self.coeffs is None :
            if verbose > 0: print('computing / ', end='')
            start = time.process_time()

            # Determine number of support nodes
            n = self.multis.cardinality
            if mode == 'wls': n = 10 * n * int(np.log(n))
            if mode == 'ls':  n = n ** 2

            # Setup linear system
            lhs, rhs = self._setup_lhs_rhs(mode, dist, resample, n, verbose)

            # Solve linear system
            self.coeffs, _, _, _ = np.linalg.lstsq(lhs, rhs, rcond=None)
            ctime = time.process_time() - start

            if save :
                if compute_cond and self.cond == -1 :
                    if lhs.size == 0 :
                        self.cond = 0
                    else :
                        self.cond = np.linalg.cond(np.dot(lhs.T, lhs) / lhs.shape[0] - np.eye(multis.cardinality))
                self.dbo.condnr = self.cond
                self.dbo.ctime = ctime
                self.dbo.nevals = n
                self.dbo.coeffs = db.to_string(self.coeffs)
                self.dbo.save()

        util.require.equal(self.coeffs.shape, (multis.cardinality,), 'coeffs.shape', 'len(multis)')

        # L2 norm squared of sqrt(f) and L1 norm of f wrt to the Lebesgue measure
        self.norm_lebesgue = self.coeffs.T.dot(self.coeffs)
        # L2 norm squared of sqrt(f) and L1 norm of f wrt to the uniform measure
        self.norm = 2**(-self.target.dim) * self.norm_lebesgue

        if verbose > 0: print('done.')

    def _setup_lhs_rhs(self, mode, dist, resample, n, verbose) :
        while True :

            # Determine support points and weights
            points, weights = util.points.get_sample_points_and_weights(self.multis, dist, n)

            # Compute LHS and RHS
            lhs = util.legendre.evaluate_basis(points, self.multis, mode='old')
            rhs = np.squeeze(self.target.evalSqrt(points))
            if weights is not None:
                for i in range(lhs.shape[0]):
                    lhs[i, :] *= weights[i]
                    rhs[i] *= weights[i]

            if resample:
                # check matrix
                G_I = np.dot(lhs.T, lhs) / lhs.shape[0] - np.eye(self.multis.cardinality)
                self.cond = 0 if lhs.size == 0 else np.linalg.cond(lhs)
                if verbose > 1 : print(f'\t\t cond = {self.cond}')
                if self.cond <= .5 :
                    break
            else :
                break
        return lhs, rhs

    def evalSqrt(self, x) :
        x = util.points.ensure_shape(x, self.dim)
        basis = util.legendre.evaluate_basis(x, self.multis)
        return np.dot(basis, self.coeffs)

    def evalSqrtNrmd(self, x) :
        if self.norm == 0 : return 0
        return self.evalSqrt(x) / np.sqrt(self.norm)

    def evalNrmd(self, x) :
        return self.eval(x) / self.norm_lebesgue

    def eval(self, x) :
        return self.evalSqrt(x)**2

    def computeError(self, n=100, max_n=1e5, accurc=.01, verbose=False) :
        return ev.SurrogateEvaluation(surrog=self, n=n, max_n=max_n, accurc=accurc, verbose=verbose,
                                   save=hasattr(self, 'dbo'))

    def deleteDbo(self) :
        if hasattr(self, 'dbo') : self.dbo.delete_instance()

    #TODO move legendreutil.evaluate_basis here

