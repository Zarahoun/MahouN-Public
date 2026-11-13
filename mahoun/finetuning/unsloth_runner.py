
"""
Unsloth Runner
==============
Handles the actual fine-tuning process using Unsloth and TRL.
This module isolates the heavy dependencies (torch, unsloth, trl).
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import asdict

# Lazy imports will be handled inside methods to avoid startup crashes if libs are missing
# but for type checking we might need some trickery or just "Any"

from .config import TrainingConfig

logger = logging.getLogger(__name__)

class UnslothRunner:
    """
    Executes fine-tuning using Unsloth.
    """
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.model = None
        self.tokenizer = None
    
    def train(self, train_dataset_path: str, output_dir: str):
        """
        Run the training loop.
        
        Args:
            train_dataset_path: Path to the JSONL training file
            output_dir: Directory to save the model/adapters
        """
        self._check_dependencies()
        import torch
        from unsloth import FastLanguageModel
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import load_dataset
        
        logger.info(f"Loading base model: {self.config.base_model}")
        
        # 1. Load Model & Tokenizer
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name = self.config.base_model,
            max_seq_length = self.config.max_seq_length,
            dtype = None, # Auto detection
            load_in_4bit = self.config.load_in_4bit,
        )
        
        # 2. Add LoRA Adapters
        model = FastLanguageModel.get_peft_model(
            model,
            r = self.config.lora_r,
            target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                              "gate_proj", "up_proj", "down_proj",],
            lora_alpha = self.config.lora_alpha,
            lora_dropout = self.config.lora_dropout,
            bias = "none",
            use_gradient_checkpointing = "unsloth", # optimize VRAM
            random_state = self.config.seed,
            use_rslora = False,
            loftq_config = None, 
        )
        
        self.model = model
        self.tokenizer = tokenizer
        
        # 3. Load Dataset
        logger.info(f"Loading dataset from {train_dataset_path}")
        dataset = load_dataset("json", data_files=train_dataset_path, split="train")
        
        # Format dataset
        # We assume the dataset has 'input' and 'target' fields from our pipeline
        # Unsloth supports various formats, but standard Alpaca/ShareGPT is common.
        # Let's map our generic input/target to a standard prompt structure.
        
        # Standard Alpaca Prompt
        alpaca_prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""

        def formatting_prompts_func(examples):
            instructions = ["Answer the user query based on valid context." for _ in examples["input"]] # Generic instruction
            inputs = examples["input"]
            outputs = examples["target"]
            texts = []
            for instruction, input, output in zip(instructions, inputs, outputs):
                # Must add EOS_TOKEN
                text = alpaca_prompt.format(instruction=instruction, input=input, output=output) + tokenizer.eos_token
                texts.append(text)
            return { "text" : texts }

        dataset = dataset.map(formatting_prompts_func, batched = True)
        
        # 4. Training Arguments
        logger.info("Setting up training arguments...")
        training_args = TrainingArguments(
            per_device_train_batch_size = self.config.batch_size,
            gradient_accumulation_steps = self.config.gradient_accumulation_steps,
            warmup_steps = self.config.warmup_steps,
            max_steps = self.config.max_steps,
            num_train_epochs = self.config.num_train_epochs,
            learning_rate = self.config.learning_rate,
            fp16 = not torch.cuda.is_bf16_supported(),
            bf16 = torch.cuda.is_bf16_supported(),
            logging_steps = self.config.logging_steps,
            optim = self.config.optimizer,
            weight_decay = 0.01,
            lr_scheduler_type = "linear",
            seed = self.config.seed,
            output_dir = output_dir,
            report_to = "none", # Disable wandb for now
        )
        
        # 5. Trainer
        trainer = SFTTrainer(
            model = model,
            tokenizer = tokenizer,
            train_dataset = dataset,
            dataset_text_field = "text",
            max_seq_length = self.config.max_seq_length,
            dataset_num_proc = 2,
            packing = False, # Can set to True for speedup
            args = training_args,
        )
        
        # 6. Train
        logger.info("Starting training...")
        trainer_stats = trainer.train()
        
        logger.info(f"Training complete. Stats: {trainer_stats}")
        
        # 7. Save
        logger.info(f"Saving model to {output_dir}")
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)
        
        # 8. Export to GGUF (multiple quantization levels)
        logger.info("Exporting to GGUF format...")
        self.export_to_gguf(model, tokenizer, output_dir)
        
        return trainer_stats
    
    def export_to_gguf(
        self, 
        model, 
        tokenizer, 
        output_dir: str,
        quantization_methods: List[str] = None
    ):
        """
        Export fine-tuned model to GGUF format with multiple quantization levels.
        
        Args:
            model: The trained model
            tokenizer: The tokenizer
            output_dir: Base output directory
            quantization_methods: List of quantization methods to export
                                 Default: ["q4_k_m", "q5_k_m", "f16"]
        """
        if quantization_methods is None:
            quantization_methods = ["q4_k_m", "q5_k_m", "f16"]
        
        for quant_method in quantization_methods:
            try:
                gguf_dir = f"{output_dir}/gguf_{quant_method}"
                logger.info(f"Exporting GGUF with {quant_method} quantization to {gguf_dir}")
                
                # Unsloth built-in GGUF export
                model.save_pretrained_gguf(
                    gguf_dir,
                    tokenizer,
                    quantization_method=quant_method
                )
                
                logger.info(f"✅ GGUF ({quant_method}) exported successfully")
                
            except Exception as e:
                logger.warning(f"Failed to export GGUF ({quant_method}): {e}")
                # Continue with other quantization methods
                continue
        
        logger.info(f"GGUF export complete. Models saved to {output_dir}/gguf_*")

    def _check_dependencies(self):
        try:
            import unsloth
            import trl
            import torch
        except ImportError as e:
            msg = f"Missing dependency for Unsloth training: {e}. Please install unsloth, trl, and torch."
            logger.error(msg)
            raise ImportError(msg)
