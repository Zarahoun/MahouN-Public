#!/usr/bin/env python3
"""
Download Persian Embedding Model
=================================
Downloads a lightweight, high-quality Persian embedding model.

Recommended: HooshvareLab/paraphrase-multilingual-mpnet-base-v2
- Best balance of speed, size, and accuracy for Persian
- Works well for legal text semantic search
"""

import sys
from pathlib import Path

def download_model(model_name: str = "BAAI/bge-small-en-v1.5"):
    """Download and cache the embedding model."""
    
    print(f"🚀 Downloading Persian embedding model: {model_name}")
    print(f"📦 Estimated size: ~120MB")
    print(f"⏳ This may take 2-5 minutes depending on your internet...")
    print()
    
    try:
        from sentence_transformers import SentenceTransformer
        
        # Download and cache the model
        model = SentenceTransformer(model_name)
        
        # Test the model
        print("✅ Model downloaded successfully!")
        print()
        print("🧪 Testing model...")
        
        test_sentences = [
            "این یک تست برای مدل embedding است",
            "این جمله دوم برای بررسی similarity است",
            "متن حقوقی برای آزمایش سیستم ماهون"
        ]
        
        embeddings = model.encode(test_sentences)
        print(f"✓ Generated {len(embeddings)} embeddings")
        print(f"✓ Embedding dimension: {embeddings.shape[1]}")
        
        # Calculate similarity between first two sentences
        from sklearn.metrics.pairwise import cosine_similarity
        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
        print(f"✓ Similarity between test sentences: {similarity:.3f}")
        
        print()
        print("🎉 Model is ready to use!")
        print()
        print("📝 Usage in your code:")
        print(f"   from sentence_transformers import SentenceTransformer")
        print(f"   model = SentenceTransformer('{model_name}')")
        print(f"   embeddings = model.encode(['متن شما'])")
        
        return model
        
    except ImportError as e:
        print("❌ Error: sentence-transformers not installed")
        print()
        print("🔧 Install with:")
        print("   source venv/bin/activate")
        print("   pip install sentence-transformers")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error downloading model: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Download Persian embedding model")
    parser.add_argument(
        "--model", 
        type=str,
        default="HooshvareLab/paraphrase-multilingual-mpnet-base-v2",
        help="Model name from HuggingFace (default: HooshvareLab/paraphrase-multilingual-mpnet-base-v2)"
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available Persian models"
    )
    
    args = parser.parse_args()
    
    if args.list_models:
        print("Available Persian embedding models:")
        print()
        print("1. BAAI/bge-small-en-v1.5 (⭐ Recommended - Lightweight)")
        print("   - Best for semantic search & RAG")
        print("   - Size: ~120MB (very lightweight)")
        print("   - Fast inference")
        print()
        print("2. BAAI/bge-base-en-v1.5")
        print("   - Better accuracy, larger size")
        print("   - Size: ~440MB")
        print()
        print("3. HooshvareLab/paraphrase-multilingual-mpnet-base-v2")
        print("   - Excellent for Persian semantic similarity")
        print("   - Size: ~420MB")
        print()
        print("4. HooshvareLab/bert-base-parsbert-uncased")
        print("   - General Persian NLP")
        print("   - Size: ~440MB")
        print()
        print("5. sentence-transformers/LaBSE")
        print("   - Multilingual (109 languages)")
        print("   - Size: ~470MB")
        print()
        sys.exit(0)
    
    download_model(args.model)