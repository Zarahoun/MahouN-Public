
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class UltraModelLoader:
    def __init__(self, model_dir: str):
        self.model_dir = Path(model_dir)
        self.cache = {}

    def load(self, model_name: str):
        if model_name in self.cache:
            return self.cache[model_name]

        model_path = self.model_dir / model_name
        
        if not model_path.exists():
            # For testing/dev environment where models might not be downloaded yet
            raise FileNotFoundError(f"Model {model_name} not found at {model_path}")

        logger.info(f"Loading Ultra Model: {model_name}...")
        try:
            tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            
            # Determine device map based on availability
            device_map = "auto" if torch.cuda.is_available() else "cpu"
            low_cpu_mem_usage = True if torch.cuda.is_available() else False
            
            model = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map=device_map,
                low_cpu_mem_usage=low_cpu_mem_usage
            )

            # GPU memory sharding (if multiple GPUs exist)
            if torch.cuda.device_count() > 1:
                logger.info(f"Enabling DataParallel for {torch.cuda.device_count()} GPUs")
                model = torch.nn.DataParallel(model)

            self.cache[model_name] = (tokenizer, model)
            logger.info(f"✅ Model {model_name} loaded successfully")
            return tokenizer, model
            
        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            raise
