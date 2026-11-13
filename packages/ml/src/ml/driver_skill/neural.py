"""A small neural comparison (PyTorch, optional).

Same inputs as the linear model, but the effects are learned embeddings combined by
an MLP, with a per-driver experience feature as a crude temporal signal. It exists
to answer "would deep learning do better here?" with a measured answer, not to
replace the Gaussian model. With ~8,600 rows and a noise floor around 0.4% of the
lap, we expect it not to; the point is to check.

Early stopping uses the *last 10% of training sessions* (a temporal hold-out), so
it never sees the test period.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import torch
    from torch import nn
except ImportError:  # pragma: no cover
    torch = None


class _Net(nn.Module if torch else object):
    def __init__(self, n_drv: int, n_car: int, n_ses: int, dim: int = 6):
        super().__init__()
        self.drv = nn.Embedding(n_drv + 1, dim, padding_idx=0)
        self.car = nn.Embedding(n_car + 1, dim, padding_idx=0)
        self.ses = nn.Embedding(n_ses + 1, 1, padding_idx=0)
        self.mlp = nn.Sequential(nn.Linear(2 * dim + 1, 16), nn.Tanh(), nn.Linear(16, 1))

    def forward(self, d, c, s, exp):
        h = torch.cat([self.drv(d), self.car(c), exp.unsqueeze(1)], dim=1)
        w = self.ses.weight[:, 0]
        off = torch.where(s == 0, w[1:].mean(), w[s])  # index 0 = an unseen session: use the average offset
        return self.mlp(h).squeeze(1) + off


class NeuralSkill:
    name = "Neural (embeddings + MLP)"

    def __init__(self, epochs: int = 400, lr: float = 0.02, weight_decay: float = 1e-3, seed: int = 0):
        if torch is None:
            raise RuntimeError("torch is not installed")
        self.epochs, self.lr, self.wd, self.seed = epochs, lr, weight_decay, seed

    def _tensors(self, d: pd.DataFrame, fit: bool):
        di = d["driver_id"].map(self._drv).fillna(0).astype(int).to_numpy()
        ci = d["team_season"].map(self._car).fillna(0).astype(int).to_numpy()
        si = d["session"].map(self._ses).fillna(0).astype(int).to_numpy()
        exp = (d["year"] - d["driver_id"].map(self._debut).fillna(d["year"])).clip(lower=0).to_numpy() / 10.0
        return tuple(torch.tensor(a) for a in (di, ci, si)) + (torch.tensor(exp, dtype=torch.float32),)

    def fit(self, df: pd.DataFrame):
        torch.manual_seed(self.seed)
        d = df.dropna(subset=["gap"]).sort_values("session").reset_index(drop=True)
        self._drv = {k: i + 1 for i, k in enumerate(sorted(d["driver_id"].unique()))}
        self._car = {k: i + 1 for i, k in enumerate(sorted(d["team_season"].unique()))}
        self._debut = d.groupby("driver_id")["year"].min().to_dict()
        sessions = sorted(d["session"].unique())
        val_sessions = set(sessions[int(len(sessions) * 0.9):])
        # only training sessions get an offset; the temporal hold-out sessions stay 'unseen', like the test period
        self._ses = {k: i + 1 for i, k in enumerate(s for s in sessions if s not in val_sessions)}
        is_val = d["session"].isin(val_sessions).to_numpy()
        self.net = _Net(len(self._drv), len(self._car), len(self._ses))
        opt = torch.optim.AdamW(self.net.parameters(), lr=self.lr, weight_decay=self.wd)
        T = self._tensors(d, True)
        y = torch.tensor(d["gap"].to_numpy(), dtype=torch.float32)
        tr, va = torch.tensor(~is_val), torch.tensor(is_val)
        best, best_state, bad = np.inf, None, 0
        for _ in range(self.epochs):
            self.net.train()
            opt.zero_grad()
            loss = ((self.net(*(t[tr] for t in T)) - y[tr]) ** 2).mean()
            loss.backward()
            opt.step()
            self.net.eval()
            with torch.no_grad():
                v = float(((self.net(*(t[va] for t in T)) - y[va]) ** 2).mean())
            if v < best - 1e-5:
                best, bad = v, 0
                best_state = {k: x.clone() for k, x in self.net.state_dict().items()}
            else:
                bad += 1
                if bad >= 40:
                    break
        self.net.load_state_dict(best_state)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        d = df.copy()
        # an unseen team-season falls back to last year's embedding of the same constructor
        prev = (d["constructor_id"] + ":" + (d["year"] - 1).astype(str)).map(self._car)
        known = d["team_season"].map(self._car)
        d["team_season"] = np.where(known.isna() & prev.notna(), d["constructor_id"] + ":" + (d["year"] - 1).astype(str), d["team_season"])
        self.net.eval()
        with torch.no_grad():
            return self.net(*self._tensors(d, False)).numpy()
