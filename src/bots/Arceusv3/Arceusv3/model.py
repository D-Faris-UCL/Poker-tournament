import torch
import torch.nn as nn
import torch.nn.functional as F

def layer_init(layer, std=1.0, bias_const=0.0):
    """Standard PPO initialization for stable gradients."""
    torch.nn.init.orthogonal_(layer.weight, std)
    torch.nn.init.constant_(layer.bias, bias_const)
    return layer

class SubModel(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            layer_init(nn.Linear(input_dim, hidden_dim)),
            nn.ReLU(),
            layer_init(nn.Linear(hidden_dim, output_dim)),
            nn.LayerNorm(output_dim)
        )

    def forward(self, x):
        return self.net(x)

class PokerPPOAgent(nn.Module):
    def __init__(self):
        super().__init__()
        
        self.hist_model = SubModel(430, 128, 64)
        
        self.shared_trunk = nn.Sequential(
            layer_init(nn.Linear(144, 256)),
            nn.LayerNorm(256),  # CRITICAL FIX: Normalize base_state before FiLM multiplier
            nn.ReLU(),
        )
        
        self.film_gen = nn.Sequential(
            layer_init(nn.Linear(256, 256)),
            nn.LayerNorm(256),
            nn.ReLU(),
        )
        
        self.film_head = nn.Linear(256, 512) 
        
        # Initialize to zero so the network starts with zero modification
        torch.nn.init.zeros_(self.film_head.weight)
        torch.nn.init.zeros_(self.film_head.bias)
        # REMOVED: .fill_(1.0) because we calculate it dynamically in forward()
        
        self.actor_branch = nn.Sequential(
            layer_init(nn.Linear(256, 128)),
            nn.ReLU(),
            layer_init(nn.Linear(128, 128)),
            nn.ReLU(),
            layer_init(nn.Linear(128, 10), std=0.01) 
        )
        
        self.critic_branch = nn.Sequential(
            layer_init(nn.Linear(256, 128)),
            nn.ReLU(),
            layer_init(nn.Linear(128, 64)),
            nn.ReLU(),
            layer_init(nn.Linear(64, 1))
        )

    def forward(self, main_data, opp_data, hist_data, main_drop_p=0.0, opp_drop_p=0.0, hist_drop_p=0.0):
        hist_feat = self.hist_model(hist_data)
        
        main_feat = F.dropout(main_data, p=main_drop_p, training=self.training)
        hist_feat = F.dropout(hist_feat, p=hist_drop_p, training=self.training)
        opp_data_dropped = F.dropout(opp_data, p=opp_drop_p, training=self.training)
        
        combined = torch.cat([main_feat, hist_feat], dim=-1)
        base_state = self.shared_trunk(combined)
        
        film_features = self.film_gen(opp_data_dropped)
        film_params = self.film_head(film_features)
        
        gamma_delta, beta = film_params.chunk(2, dim=-1)
        
        # CRITICAL FIX: Bound the multiplier to prevent explosion. 
        # Using tanh strictly caps the multiplier between 0.0 and 2.0 (Starts at 1.0)
        gamma = 1.0 + torch.tanh(gamma_delta) 
        
        unified_state = (gamma * base_state) + beta
        unified_state = F.relu(unified_state) 
        
        logits = self.actor_branch(unified_state)
        value = self.critic_branch(unified_state)
        
        return logits, value

    def get_action_and_value(self, main_data, opp_data, hist_data, action=None, action_mask=None, main_drop_p=0.0, opp_drop_p=0.0, hist_drop_p=0.0):
        """Standard PPO helper for sampling and log_probs."""
        logits, value = self.forward(main_data, opp_data, hist_data, main_drop_p, opp_drop_p, hist_drop_p)
        
        # Mask illegal actions with -infinity so they have 0 probability
        if action_mask is not None:
            logits = torch.where(action_mask, logits, torch.tensor(-1e9).to(logits.device))
            
        probs = torch.distributions.Categorical(logits=logits)
        
        if action is None:
            action = probs.sample()
            
        return action, probs.log_prob(action), probs.entropy(), value