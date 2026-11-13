"""A dynamic driver + car model of qualifying pace.

For driver ``i`` in session ``s`` of season ``y`` driving for team-season ``c``::

    gap[s, i] = session[s] + car[c] + skill[i, y] + noise

* ``gap``   : Q1 lap, % slower than the session's fastest (see data.py).
* ``car``   : one effect per team-season. A car is rebuilt every year, so there is
              no link between seasons (that is the regulation-change drift we
              evaluate in cv.py).
* ``skill`` : one effect per driver-season that follows a *random walk*:
              ``skill[i, y] = skill[i, y-1] + N(0, tau_walk^2 * years_between)``.
              This is the temporal part: skill can rise and fall over a career,
              and an estimate is pulled toward the driver's neighbouring seasons,
              not toward a career constant.
* ``session``: absorbs weather and track evolution, which move every car at once.

Fitting
-------
All priors are Gaussian, so the posterior is Gaussian and the MAP estimate is a
single linear solve (a Kalman smoother in matrix form). The noise level differs a
lot between a dry session and a wet one, so each session gets its own noise sd,
re-estimated from its robust residual spread (a few iterations). The same
matrix gives each effect a posterior standard deviation.

Identification: a car and a driver are only separated through teammates (two
drivers, one car) and through drivers who change team. Priors regularise the rest.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse


@dataclass(frozen=True)
class Hyper:
    tau_car: float = 1.5  # sd of a car effect, % of lap
    tau_driver0: float = 0.6  # sd of a driver's first-season skill
    tau_walk: float = 0.2  # sd of yearly skill change
    tau_session: float = 1.5  # sd of a session intercept (weak prior)
    car_carry: float = 0.5  # rho: correlation between a team's car effect and its previous season's


class SkillModel:
    def __init__(self, hyper: Hyper | None = None, n_iter: int = 3):
        self.h = hyper or Hyper()
        self.n_iter = n_iter

    # ------------------------------------------------------------------ fit
    def fit(self, df: pd.DataFrame) -> "SkillModel":
        d = df.dropna(subset=["gap"]).reset_index(drop=True)
        if d.empty:
            raise ValueError("no rows to fit")
        sessions = sorted(d["session"].unique())
        cars = sorted(d["team_season"].unique())
        dys = sorted(set(zip(d["driver_id"], d["year"])))
        self._s_idx = {k: i for i, k in enumerate(sessions)}
        self._c_idx = {k: i for i, k in enumerate(cars)}
        self._d_idx = {k: i for i, k in enumerate(dys)}
        S, C, D = len(sessions), len(cars), len(dys)
        self._offsets = (0, S, S + C)
        p = S + C + D

        n = len(d)
        si = d["session"].map(self._s_idx).to_numpy()
        ci = d["team_season"].map(self._c_idx).to_numpy() + S
        di = np.array([self._d_idx[k] for k in zip(d["driver_id"], d["year"])]) + S + C
        rows = np.repeat(np.arange(n), 3)
        cols = np.stack([si, ci, di], axis=1).ravel()
        X = sparse.csr_matrix((np.ones(3 * n), (rows, cols)), shape=(n, p))
        y = d["gap"].to_numpy(float)

        P = self._prior_precision(S, C, dys)

        w = np.full(n, 1.0 / max(y.var(), 1e-6))
        theta = np.zeros(p)
        for _ in range(self.n_iter):
            XtW = X.T.multiply(w).tocsr()
            A = (XtW @ X).toarray() + P
            theta = np.linalg.solve(A, XtW @ y)
            resid = y - X @ theta
            w, self.sigma, self.session_sd = self._session_weights(d["session"].to_numpy(), resid)
        self.theta = theta
        self._cov_diag = np.diag(np.linalg.inv(A))
        self.session_mean = float(theta[:S].mean())
        self._dys_by_driver: dict[str, list[tuple[int, int]]] = {}
        for (drv, yr), i in self._d_idx.items():
            self._dys_by_driver.setdefault(drv, []).append((yr, i))
        for v in self._dys_by_driver.values():
            v.sort()
        return self

    def _prior_precision(self, S: int, C: int, dys: list[tuple[str, int]]) -> np.ndarray:
        h = self.h
        p = S + C + len(dys)
        P = np.zeros((p, p))
        P[np.arange(S), np.arange(S)] = 1.0 / h.tau_session**2
        P[np.arange(S, S + C), np.arange(S, S + C)] = 1.0 / h.tau_car**2
        prev: dict[str, tuple[int, int]] = {}
        for k, (drv, yr) in enumerate(dys):  # dys is sorted by (driver, year)
            j = S + C + k
            if drv in prev:
                pyr, pj = prev[drv]
                prec = 1.0 / (h.tau_walk**2 * (yr - pyr))
                P[j, j] += prec
                P[pj, pj] += prec
                P[j, pj] -= prec
                P[pj, j] -= prec
            else:
                P[j, j] += 1.0 / h.tau_driver0**2
            prev[drv] = (yr, j)
        return P

    @staticmethod
    def _session_weights(sessions: np.ndarray, resid: np.ndarray, floor: float = 0.15):
        """Per-row precision 1/sd^2 from each session's robust residual spread, shrunk to the global one."""
        glob = max(1.4826 * np.median(np.abs(resid - np.median(resid))), floor)
        sd = {}
        for s in np.unique(sessions):
            r = resid[sessions == s]
            mad = 1.4826 * np.median(np.abs(r - np.median(r)))
            k = len(r)
            sd[s] = max(np.sqrt((k * mad**2 + 5 * glob**2) / (k + 5)), floor)
        return np.array([1.0 / sd[s] ** 2 for s in sessions]), glob, sd

    # -------------------------------------------------------------- predict
    def _car_effect(self, row) -> tuple[float, float]:
        i = self._c_idx.get(row.team_season)
        if i is not None:
            S = self._offsets[1]
            return self.theta[S + i], self._cov_diag[S + i]
        prev = self._c_idx.get(f"{row.constructor_id}:{row.year - 1}")
        if prev is not None:
            # AR(1) across seasons: new = rho * last + N(0, tau^2 (1 - rho^2))
            S = self._offsets[1]
            rho = self.h.car_carry
            return rho * self.theta[S + prev], rho**2 * self._cov_diag[S + prev] + self.h.tau_car**2 * (1 - rho**2)
        return 0.0, self.h.tau_car**2

    def _skill_effect(self, driver: str, year: int) -> tuple[float, float]:
        i = self._d_idx.get((driver, year))
        base = self._offsets[2]
        if i is not None:
            return self.theta[base + i], self._cov_diag[base + i]
        earlier = [(yr, j) for yr, j in self._dys_by_driver.get(driver, []) if yr < year]
        if earlier:  # random walk forecast: carry the last value, widen the variance
            yr, j = earlier[-1]
            return self.theta[base + j], self._cov_diag[base + j] + self.h.tau_walk**2 * (year - yr)
        return 0.0, self.h.tau_driver0**2

    def predict(self, df: pd.DataFrame, return_sd: bool = False):
        mu = np.empty(len(df))
        var = np.empty(len(df))
        for k, row in enumerate(df.itertuples(index=False)):
            c, cv = self._car_effect(row)
            s, sv = self._skill_effect(row.driver_id, row.year)
            mu[k] = self.session_mean + c + s
            var[k] = self.sigma**2 + cv + sv
        return (mu, np.sqrt(var)) if return_sd else mu

    # --------------------------------------------------------------- tables
    def driver_table(self) -> pd.DataFrame:
        base = self._offsets[2]
        rows = [
            {"driver_id": drv, "year": yr, "skill": self.theta[base + i], "sd": float(np.sqrt(self._cov_diag[base + i]))}
            for (drv, yr), i in self._d_idx.items()
        ]
        return pd.DataFrame(rows).sort_values(["driver_id", "year"]).reset_index(drop=True)

    def car_table(self) -> pd.DataFrame:
        base = self._offsets[1]
        rows = [
            {"team_season": k, "car": self.theta[base + i], "sd": float(np.sqrt(self._cov_diag[base + i]))}
            for k, i in self._c_idx.items()
        ]
        return pd.DataFrame(rows).sort_values("team_season").reset_index(drop=True)
