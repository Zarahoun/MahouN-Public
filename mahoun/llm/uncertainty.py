
import numpy as np

class UncertaintyModel:
    def score(self, text: str):
        # heuristic + GP hook (stub for now)
        # Assuming optimal length around 300 chars for high confidence in this mock
        length = len(text)
        if length == 0:
            return 0.0
        
        # Simple heuristic: penalize very short or extremely long answers slightly
        # Ideally this would use log-probs from the model if available
        confidence = np.exp(-abs(length - 300) / 300)  # normalized confidence (0 to 1)
        return float(confidence)
