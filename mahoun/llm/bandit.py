
import random
import logging

logger = logging.getLogger(__name__)

class BanditController:
    def __init__(self, models):
        self.models = models
        self.rewards = {m: 1.0 for m in models}  # optimistic init

    def choose(self):
        # epsilon-greedy
        epsilon = 0.1
        if random.random() < epsilon:
            choice = random.choice(self.models)
            logger.debug(f"Bandit (Explore): {choice}")
            return choice
        
        choice = max(self.rewards, key=self.rewards.get)
        logger.debug(f"Bandit (Exploit): {choice} (Reward: {self.rewards[choice]:.2f})")
        return choice

    def update(self, model_name: str, reward: float):
        self.rewards[model_name] = (
            0.8 * self.rewards[model_name] + 0.2 * reward
        )
