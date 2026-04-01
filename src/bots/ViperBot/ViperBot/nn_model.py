"""Neural network model for ViperBot.

Actor  (PokerNet):  Input -> Dense(64, ReLU) -> Dense(32, ReLU) -> Dense(6, Softmax)
Critic (ValueNet):  Input -> Dense(32, ReLU) -> Dense(1)
Optimizer:          Adam
Training:           A2C  — advantage = G - V(s), lower variance than raw REINFORCE
"""
import pickle
import numpy as np

NUM_ACTIONS = 6   # FOLD, CALL, RAISE_T, RAISE_H, RAISE_P, ALL_IN


# ── Critic ────────────────────────────────────────────────────────────────────

class ValueNet:
    """State-value function V(s) — learned baseline that kills REINFORCE variance."""

    def __init__(self, n_features: int, hidden: int = 32, lr: float = 1e-3):
        self.n_features = n_features
        self.hidden     = hidden
        self.lr         = lr

        def _w(fin, fout):
            lim = np.sqrt(6.0 / (fin + fout))
            return np.random.uniform(-lim, lim, (fin, fout)).astype(np.float32)

        self.W1 = _w(n_features, hidden)
        self.b1 = np.zeros(hidden, dtype=np.float32)
        self.W2 = _w(hidden, 1)
        self.b2 = np.zeros(1, dtype=np.float32)

        self.t  = 0
        self._params = [self.W1, self.b1, self.W2, self.b2]
        self.m  = [np.zeros_like(p) for p in self._params]
        self.v  = [np.zeros_like(p) for p in self._params]

    def forward(self, x: np.ndarray) -> float:
        h1 = np.maximum(0.0, x @ self.W1 + self.b1)
        return float((h1 @ self.W2 + self.b2)[0])

    def _grads(self, x: np.ndarray):
        """Gradient of V(s) w.r.t. all parameters."""
        h1_pre = x @ self.W1 + self.b1
        h1     = np.maximum(0.0, h1_pre)
        dW2    = np.outer(h1, np.ones(1, dtype=np.float32))
        db2    = np.ones(1, dtype=np.float32)
        dh1    = self.W2[:, 0].copy()
        dh1p   = dh1 * (h1_pre > 0)
        dW1    = np.outer(x, dh1p)
        db1    = dh1p.copy()
        return [dW1, db1, dW2, db2]

    def _adam_step(self, accum, scale, beta1=0.9, beta2=0.999, eps=1e-8):
        self.t += 1
        for i, p in enumerate(self._params):
            g         = accum[i] * scale
            self.m[i] = beta1 * self.m[i] + (1.0 - beta1) * g
            self.v[i] = beta2 * self.v[i] + (1.0 - beta2) * g ** 2
            m_hat     = self.m[i] / (1.0 - beta1 ** self.t)
            v_hat     = self.v[i] / (1.0 - beta2 ** self.t)
            p        += self.lr * m_hat / (np.sqrt(v_hat) + eps)


# ── Actor ─────────────────────────────────────────────────────────────────────

class PokerNet:
    """Policy network trained with A2C (actor-critic)."""

    def __init__(self, n_features: int, hidden1: int = 64, hidden2: int = 32, lr: float = 3e-4):
        self.n_features = n_features
        self.hidden1    = hidden1
        self.hidden2    = hidden2
        self.lr         = lr

        def _w(fin, fout):
            lim = np.sqrt(6.0 / (fin + fout))
            return np.random.uniform(-lim, lim, (fin, fout)).astype(np.float32)

        self.W1 = _w(n_features, hidden1)
        self.b1 = np.zeros(hidden1, dtype=np.float32)
        self.W2 = _w(hidden1, hidden2)
        self.b2 = np.zeros(hidden2, dtype=np.float32)
        self.W3 = _w(hidden2, NUM_ACTIONS)
        self.b3 = np.zeros(NUM_ACTIONS, dtype=np.float32)

        self.t       = 0
        self._params = [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]
        self.m       = [np.zeros_like(p) for p in self._params]
        self.v       = [np.zeros_like(p) for p in self._params]

    # ── forward ──────────────────────────────────────────────────────────────

    def _relu(self, x): return np.maximum(0.0, x)

    def _softmax(self, x):
        e = np.exp(x - x.max()); return e / e.sum()

    def forward(self, x: np.ndarray):
        h1_pre = x @ self.W1 + self.b1;  h1 = self._relu(h1_pre)
        h2_pre = h1 @ self.W2 + self.b2; h2 = self._relu(h2_pre)
        logits = h2 @ self.W3 + self.b3
        return self._softmax(logits), (h1_pre, h1, h2_pre, h2)

    def get_action_probs(self, features, legal_mask: np.ndarray) -> np.ndarray:
        x     = np.array(features, dtype=np.float32)
        probs, _ = self.forward(x)
        probs = probs * legal_mask
        total = probs.sum()
        return probs / total if total > 1e-9 else legal_mask / legal_mask.sum()

    # ── gradients ────────────────────────────────────────────────────────────

    def _log_policy_grads(self, x: np.ndarray, action_idx: int):
        probs, (h1_pre, h1, h2_pre, h2) = self.forward(x)
        d_logits              = -probs.copy()
        d_logits[action_idx] += 1.0          # d log π(a|s) / d logits

        dW3 = np.outer(h2, d_logits);  db3 = d_logits.copy()
        d_h2     = d_logits @ self.W3.T
        d_h2_pre = d_h2 * (h2_pre > 0)
        dW2 = np.outer(h1, d_h2_pre);  db2 = d_h2_pre.copy()
        d_h1     = d_h2_pre @ self.W2.T
        d_h1_pre = d_h1 * (h1_pre > 0)
        dW1 = np.outer(x, d_h1_pre);   db1 = d_h1_pre.copy()
        return [dW1, db1, dW2, db2, dW3, db3]

    # ── A2C update ───────────────────────────────────────────────────────────

    def update_a2c(
        self,
        trajectory,       # list of (features, action_idx, legal_mask)
        G: float,         # Monte-Carlo return for the episode (chip_delta / BB)
        value_net: ValueNet,
        beta1=0.9, beta2=0.999, eps=1e-8,
    ):
        """Update actor and critic together using advantage A_t = G - V(s_t).

        Critic  : MSE regression → V(s) learns to predict G
        Actor   : policy gradient scaled by advantage (lower variance than REINFORCE)
        """
        if not trajectory:
            return

        n           = len(trajectory)
        actor_acc   = [np.zeros_like(p) for p in self._params]
        critic_acc  = [np.zeros_like(p) for p in value_net._params]

        for features, action_idx, _ in trajectory:
            x         = np.array(features, dtype=np.float32)
            advantage = G - value_net.forward(x)   # how much better than expected

            # Actor: ∇ log π(a|s) * advantage
            for i, g in enumerate(self._log_policy_grads(x, action_idx)):
                actor_acc[i] += g * advantage

            # Critic: gradient of V(s) scaled by advantage (= ∇ MSE)
            for i, g in enumerate(value_net._grads(x)):
                critic_acc[i] += g * advantage

        scale = 1.0 / n

        # Adam — actor
        self.t += 1
        for i, p in enumerate(self._params):
            g         = actor_acc[i] * scale
            self.m[i] = beta1 * self.m[i] + (1.0 - beta1) * g
            self.v[i] = beta2 * self.v[i] + (1.0 - beta2) * g ** 2
            m_hat     = self.m[i]  / (1.0 - beta1 ** self.t)
            v_hat     = self.v[i]  / (1.0 - beta2 ** self.t)
            p        += self.lr * m_hat / (np.sqrt(v_hat) + eps)

        # Adam — critic
        value_net.t += 1
        for i, p in enumerate(value_net._params):
            g                = critic_acc[i] * scale
            value_net.m[i]   = beta1 * value_net.m[i] + (1.0 - beta1) * g
            value_net.v[i]   = beta2 * value_net.v[i] + (1.0 - beta2) * g ** 2
            m_hat            = value_net.m[i] / (1.0 - beta1 ** value_net.t)
            v_hat            = value_net.v[i] / (1.0 - beta2 ** value_net.t)
            p               += value_net.lr * m_hat / (np.sqrt(v_hat) + eps)

    # ── weight management ────────────────────────────────────────────────────

    def copy_weights_from(self, other: 'PokerNet'):
        for dst, src in zip(
            [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3],
            [other.W1, other.b1, other.W2, other.b2, other.W3, other.b3],
        ):
            dst[:] = src
        self._params = [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]

    def save(self, path: str, value_net: ValueNet = None):
        d = dict(
            W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2, W3=self.W3, b3=self.b3,
            n_features=self.n_features, hidden1=self.hidden1, hidden2=self.hidden2,
            lr=self.lr, t=self.t, m=self.m, v=self.v,
        )
        if value_net is not None:
            d.update(vW1=value_net.W1, vb1=value_net.b1,
                     vW2=value_net.W2, vb2=value_net.b2,
                     v_n=value_net.n_features, v_h=value_net.hidden,
                     v_lr=value_net.lr, v_t=value_net.t,
                     v_m=value_net.m,  v_v=value_net.v)
        with open(path, 'wb') as f:
            pickle.dump(d, f)

    @classmethod
    def load(cls, path: str):
        with open(path, 'rb') as f:
            d = pickle.load(f)
        net         = cls(d['n_features'], d.get('hidden1', 64), d.get('hidden2', 32), d.get('lr', 3e-4))
        net.W1, net.b1 = d['W1'], d['b1']
        net.W2, net.b2 = d['W2'], d['b2']
        net.W3, net.b3 = d['W3'], d['b3']
        net.t, net.m, net.v = d['t'], d['m'], d['v']
        net._params = [net.W1, net.b1, net.W2, net.b2, net.W3, net.b3]

        val = None
        if 'vW1' in d:
            val         = ValueNet(d['v_n'], d['v_h'], d['v_lr'])
            val.W1, val.b1 = d['vW1'], d['vb1']
            val.W2, val.b2 = d['vW2'], d['vb2']
            val.t, val.m, val.v = d['v_t'], d['v_m'], d['v_v']
            val._params = [val.W1, val.b1, val.W2, val.b2]

        return net, val
