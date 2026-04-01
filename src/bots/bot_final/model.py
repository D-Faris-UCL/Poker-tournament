"""ActorCritic network and action space utilities for the RL poker bot."""

from typing import Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

# ── Action space ──────────────────────────────────────────────────────────────
# 7 discrete action buckets shared by pre-training and PPO.
NUM_ACTIONS = 7
# Pot multipliers for raise buckets 2-5
ACTION_POT_MULTIPLIERS = [0.5, 1.0, 2.0, 3.0]

# Action type indices for one-hot encoding in encoder / parser
ACTION_TYPE_TO_IDX = {
    'fold': 0,
    'check': 1,
    'call': 2,
    'raise': 3,
    'all-in': 4,
    'small_blind': 2,  # treat like call
    'big_blind': 3,    # treat like raise
}


# ── Action mask & decode helpers ──────────────────────────────────────────────

def build_action_mask(legal: dict) -> torch.BoolTensor:
    """Convert legal-actions dict from PlayerJudge into a (7,) bool mask.

    True = action is legal and should receive probability mass.
    Fold (idx 0) is masked out when check is available to match the engine's
    auto-correction logic (fold → check when check is legal).
    """
    mask = torch.zeros(NUM_ACTIONS, dtype=torch.bool)
    # Fold only when check is not available
    mask[0] = legal['fold'] and not legal['check']
    # Check or call
    mask[1] = legal['check'] or legal['call']
    # Raise buckets (0.5×, 1×, 2×, 3× pot)
    mask[2] = legal['raise']
    mask[3] = legal['raise']
    mask[4] = legal['raise']
    mask[5] = legal['raise']
    # All-in
    mask[6] = legal['all-in']
    # Safety: ensure at least one action is legal
    if not mask.any():
        mask[1] = True  # default to check/call
    return mask


def decode_action_with_player(
    action_idx: int,
    gamestate,
    legal: dict,
    player_index: int,
) -> Tuple[str, int]:
    """decode_action with explicit player_index (avoids gamestate.current_player)."""
    player_info = gamestate.player_public_infos[player_index]
    stack = player_info.stack
    current_bet_level = gamestate.get_bet_to_call()
    my_current_bet = player_info.current_bet
    pot = gamestate.total_pot

    if action_idx == 0:
        return ('fold', 0)

    if action_idx == 1:
        return ('check', 0) if legal['check'] else ('call', 0)

    if action_idx == 6:
        return ('all-in', stack)

    multiplier = ACTION_POT_MULTIPLIERS[action_idx - 2]
    target_total = int(multiplier * max(pot, 1))

    if current_bet_level == 0:
        amount = max(target_total, legal['min_raise'])
        amount = min(amount, stack)
        if amount >= stack:
            return ('all-in', stack)
        return ('raise', amount)
    else:
        target_additional = target_total - my_current_bet
        min_additional = legal['min_raise'] - my_current_bet
        amount = max(target_additional, min_additional)
        amount = min(amount, stack)
        if amount >= stack:
            return ('all-in', stack)
        return ('raise', amount)


CARD_BLOCK_DIM = 35 + 85 + 4 + 11
STACK_BLOCK_DIM = 6
TABLE_BLOCK_DIM = 22
HISTORY_BLOCK_DIM = 24
META_BLOCK_DIM = 5


class ResidualMLPBlock(nn.Module):
    """LayerNorm + GELU residual block for stable tabular learning."""

    def __init__(self, dim: int, hidden_dim: Optional[int] = None):
        super().__init__()
        hidden_dim = hidden_dim or dim * 2
        self.norm = nn.LayerNorm(dim)
        self.fc1 = nn.Linear(dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, dim)
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x
        x = self.norm(x)
        x = self.act(self.fc1(x))
        x = self.fc2(x)
        return residual + x


class MLPBlock(nn.Module):
    """Linear projection followed by LayerNorm and GELU."""

    def __init__(self, in_dim: int, out_dim: int):
        super().__init__()
        self.fc = nn.Linear(in_dim, out_dim)
        self.norm = nn.LayerNorm(out_dim)
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.act(self.norm(self.fc(x)))


# ── Network ───────────────────────────────────────────────────────────────────

class ActorCritic(nn.Module):
    """Block-wise actor-critic with residual GELU trunk and factorized policy head."""

    INPUT_DIM = 192

    def __init__(self, input_dim: int = 192, num_actions: int = NUM_ACTIONS):
        super().__init__()
        if input_dim != self.INPUT_DIM:
            raise ValueError(f"ActorCritic expects input_dim={self.INPUT_DIM}, got {input_dim}")
        if num_actions != NUM_ACTIONS:
            raise ValueError(f"ActorCritic expects num_actions={NUM_ACTIONS}, got {num_actions}")

        self.card_encoder = nn.Sequential(
            MLPBlock(CARD_BLOCK_DIM, 128),
            ResidualMLPBlock(128),
        )
        self.stack_encoder = nn.Sequential(
            MLPBlock(STACK_BLOCK_DIM, 32),
            ResidualMLPBlock(32),
        )
        self.table_encoder = nn.Sequential(
            MLPBlock(TABLE_BLOCK_DIM, 48),
            ResidualMLPBlock(48),
        )
        self.history_encoder = nn.Sequential(
            MLPBlock(HISTORY_BLOCK_DIM, 48),
            ResidualMLPBlock(48),
        )
        self.meta_encoder = nn.Sequential(
            MLPBlock(META_BLOCK_DIM, 16),
            ResidualMLPBlock(16),
        )

        fusion_dim = 128 + 32 + 48 + 48 + 16
        self.fusion = nn.Sequential(
            MLPBlock(fusion_dim, 256),
            ResidualMLPBlock(256),
            ResidualMLPBlock(256),
        )

        self.actor_body = nn.Sequential(
            MLPBlock(256, 192),
            ResidualMLPBlock(192),
        )
        self.critic_body = nn.Sequential(
            MLPBlock(256, 192),
            ResidualMLPBlock(192),
        )

        # Factorized action head:
        # - type logits: fold / check-call / raise / all-in
        # - size logits: 0.5x / 1x / 2x / 3x pot, only used when type == raise
        self.action_type_head = nn.Linear(192, 4)
        self.raise_size_head = nn.Linear(192, 4)
        self.critic_head = nn.Linear(192, 1)

        self._init_weights()

    def _init_weights(self) -> None:
        """Orthogonal init for all linears; small scale on policy outputs."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                gain = 1.0
                if module in (self.action_type_head, self.raise_size_head):
                    gain = 0.01
                nn.init.orthogonal_(module.weight, gain=gain)
                nn.init.zeros_(module.bias)

    def _split_inputs(self, x: torch.Tensor) -> Tuple[torch.Tensor, ...]:
        card_end = CARD_BLOCK_DIM
        stack_end = card_end + STACK_BLOCK_DIM
        table_end = stack_end + TABLE_BLOCK_DIM
        history_end = table_end + HISTORY_BLOCK_DIM
        return (
            x[:, :card_end],
            x[:, card_end:stack_end],
            x[:, stack_end:table_end],
            x[:, table_end:history_end],
            x[:, history_end:history_end + META_BLOCK_DIM],
        )

    def trunk(self, x: torch.Tensor) -> torch.Tensor:
        """Encode structured feature blocks, then fuse them with residual GELU blocks."""
        card_x, stack_x, table_x, history_x, meta_x = self._split_inputs(x)
        fused = torch.cat([
            self.card_encoder(card_x),
            self.stack_encoder(stack_x),
            self.table_encoder(table_x),
            self.history_encoder(history_x),
            self.meta_encoder(meta_x),
        ], dim=-1)
        return self.fusion(fused)

    def _factorized_policy_logits(self, actor_features: torch.Tensor) -> torch.Tensor:
        type_logits = self.action_type_head(actor_features)
        raise_logits = self.raise_size_head(actor_features)

        logits = actor_features.new_empty(actor_features.size(0), NUM_ACTIONS)
        logits[:, 0] = type_logits[:, 0]  # fold
        logits[:, 1] = type_logits[:, 1]  # check/call
        logits[:, 2:6] = type_logits[:, 2].unsqueeze(1) + raise_logits
        logits[:, 6] = type_logits[:, 3]  # all-in
        return logits

    def policy_logits(self, x: torch.Tensor) -> torch.Tensor:
        """Return unmasked 7-way logits for supervised pre-training."""
        shared = self.trunk(x)
        actor_features = self.actor_body(shared)
        return self._factorized_policy_logits(actor_features)

    def actor(self, features: torch.Tensor) -> torch.Tensor:
        """Compatibility wrapper: project shared features into policy logits."""
        actor_features = self.actor_body(features)
        return self._factorized_policy_logits(actor_features)

    def critic(self, features: torch.Tensor) -> torch.Tensor:
        """Compatibility wrapper: project shared features into state values."""
        critic_features = self.critic_body(features)
        return self.critic_head(critic_features)

    def forward(
        self,
        x: torch.Tensor,
        action_mask: torch.BoolTensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass with legal-action masking."""
        shared = self.trunk(x)
        logits = self.actor(shared)
        logits = logits.masked_fill(~action_mask, -1e9)
        log_probs = F.log_softmax(logits, dim=-1)
        value = self.critic(shared)
        return log_probs, value

    def get_log_prob_entropy(
        self,
        x: torch.Tensor,
        action_mask: torch.BoolTensor,
        actions: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Compute log-probs of taken actions, values, and mean entropy.

        Used during the PPO update step.

        Args:
            x:           (batch, INPUT_DIM)
            action_mask: (batch, NUM_ACTIONS) bool
            actions:     (batch,) int64 — action indices taken during rollout

        Returns:
            action_log_probs: (batch,)
            values:           (batch,)
            entropy:          scalar mean entropy over the batch
        """
        log_probs, value = self.forward(x, action_mask)
        action_log_probs = log_probs.gather(1, actions.unsqueeze(1)).squeeze(1)
        probs = log_probs.exp()
        # Entropy: -Σ p·log(p), ignoring masked (−inf) entries via nan_to_num
        entropy_per_sample = -(probs * log_probs).nan_to_num(0.0).sum(dim=-1)
        entropy = entropy_per_sample.mean()
        return action_log_probs, value.squeeze(1), entropy
