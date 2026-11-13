# orchestrator/qa/advanced_chatbot.py
"""
Advanced Legal Chatbot with:
- Multi-turn conversation
- Context management
- Citation tracking
- Confidence scoring
- Explanation generation
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import uuid

import chromadb
from chromadb.config import Settings

from pipelines._config import load_config
from mahoun.pipelines._logging import setup_logger

log = setup_logger("advanced_chatbot")


@dataclass
class Message:
    """Chat message"""

    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str
    metadata: Dict = None


@dataclass
class ConversationContext:
    """Conversation state"""

    conversation_id: str
    messages: List[Message]
    retrieved_docs: List[Dict]
    created_at: str
    updated_at: str


class ContextManager:
    """Manage conversation context"""

    def __init__(self, max_history: int = 5):
        self.max_history = max_history
        self.contexts: Dict[str, ConversationContext] = {}

    def create_conversation(self) -> str:
        """Create new conversation"""
        conv_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        self.contexts[conv_id] = ConversationContext(
            conversation_id=conv_id,
            messages=[],
            retrieved_docs=[],
            created_at=now,
            updated_at=now,
        )

        return conv_id

    def add_message(self, conv_id: str, role: str, content: str, metadata: Dict = None):
        """Add message to conversation"""
        if conv_id not in self.contexts:
            raise ValueError(f"Conversation {conv_id} not found")

        ctx = self.contexts[conv_id]

        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {},
        )

        ctx.messages.append(message)
        ctx.updated_at = datetime.now().isoformat()

        # Trim history
        if len(ctx.messages) > self.max_history * 2:  # user + assistant
            ctx.messages = ctx.messages[-(self.max_history * 2) :]

    def get_context(self, conv_id: str) -> Optional[ConversationContext]:
        """Get conversation context"""
        return self.contexts.get(conv_id)

    def get_recent_messages(self, conv_id: str, n: int = 3) -> List[Message]:
        """Get recent messages"""
        ctx = self.get_context(conv_id)
        if not ctx:
            return []
        return ctx.messages[-n:]


class CitationTracker:
    """Track and format citations"""

    @staticmethod
    def extract_citations(retrieved_docs: List[Dict]) -> List[Dict]:
        """Extract citation information"""
        citations = []

        for i, doc in enumerate(retrieved_docs, 1):
            citation = {
                "number": i,
                "id": doc["id"],
                "score": doc.get("score", 0),
                "source": doc.get("metadata", {}).get("source", "Unknown"),
                "category": doc.get("metadata", {}).get("category", "Unknown"),
                "snippet": doc["text"][:200] + "...",
            }
            citations.append(citation)

        return citations

    @staticmethod
    def format_citations(citations: List[Dict]) -> str:
        """Format citations for display"""
        if not citations:
            return ""

        formatted = "\n\n📚 منابع:\n"
        for cite in citations:
            formatted += f"\n[{cite['number']}] {cite['source']}"
            formatted += f"\n    دسته: {cite['category']} | امتیاز: {cite['score']:.3f}"
            formatted += f"\n    {cite['snippet']}\n"

        return formatted


class ConfidenceScorer:
    """Score answer confidence"""

    @staticmethod
    def compute_confidence(retrieved_docs: List[Dict], query: str) -> Tuple[float, str]:
        """
        Compute confidence score and explanation
        Returns: (score, explanation)
        """
        if not retrieved_docs:
            return 0.0, "هیچ سندی یافت نشد"

        # Factors
        top_score = retrieved_docs[0].get("score", 0)
        num_docs = len(retrieved_docs)
        avg_score = sum(d.get("score", 0) for d in retrieved_docs) / num_docs
        score_variance = (
            sum((d.get("score", 0) - avg_score) ** 2 for d in retrieved_docs) / num_docs
        )

        # Weighted confidence
        confidence = (
            0.5 * top_score + 0.3 * min(num_docs / 5, 1.0) + 0.2 * (1 - score_variance)
        )

        # Explanation
        if confidence > 0.8:
            explanation = "اطمینان بالا - منابع متعدد و مرتبط"
        elif confidence > 0.6:
            explanation = "اطمینان متوسط - منابع موجود اما محدود"
        elif confidence > 0.4:
            explanation = "اطمینان پایین - منابع کم یا ارتباط ضعیف"
        else:
            explanation = "اطمینان بسیار پایین - پاسخ ممکن است دقیق نباشد"

        return confidence, explanation


class AdvancedLegalChatbot:
    """Advanced chatbot with full features"""

    def __init__(self, config_path: str = "configs/app.yaml"):
        self.cfg = load_config(config_path)

        # Vector DB
        self.client = chromadb.PersistentClient(
            path=self.cfg.chroma_dir, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            self.cfg.chroma_collection
        )

        # Components
        self.context_manager = ContextManager(max_history=5)
        self.citation_tracker = CitationTracker()
        self.confidence_scorer = ConfidenceScorer()

        log.info("Advanced chatbot initialized")

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """Retrieve relevant documents"""
        results = self.collection.query(query_texts=[query], n_results=top_k)

        docs = []
        for i, (doc_id, doc, dist, meta) in enumerate(
            zip(
                results["ids"][0],
                results["documents"][0],
                results["distances"][0],
                (
                    results["metadatas"][0]
                    if results.get("metadatas")
                    else [{}] * len(results["ids"][0])
                ),
            )
        ):
            docs.append(
                {
                    "id": doc_id,
                    "text": doc,
                    "score": 1 - dist,
                    "rank": i + 1,
                    "metadata": meta,
                }
            )

        return docs

    def generate_answer(
        self,
        query: str,
        context_docs: List[Dict],
        conversation_history: List[Message] = None,
    ) -> Tuple[str, float, str]:
        """
        Generate answer with confidence
        Returns: (answer, confidence, explanation)
        """

        if not context_docs:
            return (
                "متأسفانه اطلاعات کافی برای پاسخ به این سوال یافت نشد. لطفاً سوال خود را با جزئیات بیشتری مطرح کنید.",
                0.0,
                "هیچ سندی یافت نشد",
            )

        # Compute confidence
        confidence, conf_explanation = self.confidence_scorer.compute_confidence(
            context_docs, query
        )

        # Extract citations
        citations = self.citation_tracker.extract_citations(context_docs)

        # Build answer (extractive for now)
        best_doc = context_docs[0]
        snippet = best_doc["text"][:800]

        # Format answer
        answer = f"""بر اساس اسناد موجود:

{snippet}...

{self.citation_tracker.format_citations(citations[:3])}

⚠️ سطح اطمینان: {confidence:.0%} - {conf_explanation}
"""

        return answer, confidence, conf_explanation

    def chat(
        self, query: str, conversation_id: Optional[str] = None, top_k: int = 5
    ) -> Dict:
        """
        Main chat interface
        """

        # Create or get conversation
        if conversation_id is None:
            conversation_id = self.context_manager.create_conversation()
            log.info(f"New conversation: {conversation_id}")

        # Add user message
        self.context_manager.add_message(conversation_id, "user", query)

        # Get conversation history
        history = self.context_manager.get_recent_messages(conversation_id, n=3)

        # Retrieve
        log.info(f"Retrieving for: {query}")
        context_docs = self.retrieve(query, top_k)

        # Generate answer
        answer, confidence, conf_explanation = self.generate_answer(
            query, context_docs, history
        )

        # Add assistant message
        self.context_manager.add_message(
            conversation_id,
            "assistant",
            answer,
            metadata={"confidence": confidence, "num_sources": len(context_docs)},
        )

        # Update context
        ctx = self.context_manager.get_context(conversation_id)
        ctx.retrieved_docs.extend(context_docs)

        return {
            "conversation_id": conversation_id,
            "query": query,
            "answer": answer,
            "confidence": confidence,
            "confidence_explanation": conf_explanation,
            "sources": context_docs,
            "num_sources": len(context_docs),
            "history_length": len(ctx.messages),
        }

    def get_conversation_history(self, conversation_id: str) -> Optional[Dict]:
        """Get full conversation history"""
        ctx = self.context_manager.get_context(conversation_id)
        if not ctx:
            return None

        return {
            "conversation_id": ctx.conversation_id,
            "created_at": ctx.created_at,
            "updated_at": ctx.updated_at,
            "messages": [asdict(m) for m in ctx.messages],
            "total_messages": len(ctx.messages),
        }


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True, help="User query")
    ap.add_argument("--conversation_id", help="Continue existing conversation")
    ap.add_argument("--top_k", type=int, default=5)
    ap.add_argument("--output", help="Save result to JSON")
    ap.add_argument(
        "--show_history", action="store_true", help="Show conversation history"
    )
    args = ap.parse_args()

    chatbot = AdvancedLegalChatbot()

    result = chatbot.chat(
        args.query, conversation_id=args.conversation_id, top_k=args.top_k
    )

    # Display
    print("\n" + "=" * 80)
    print(f"🗨️  سوال: {result['query']}")
    print("=" * 80)
    print(f"\n🤖 پاسخ:\n{result['answer']}")
    print("\n" + "=" * 80)
    print(f"📊 آمار:")
    print(f"   - شناسه مکالمه: {result['conversation_id']}")
    print(f"   - اطمینان: {result['confidence']:.0%}")
    print(f"   - تعداد منابع: {result['num_sources']}")
    print(f"   - طول تاریخچه: {result['history_length']}")
    print("=" * 80)

    # Show history
    if args.show_history:
        history = chatbot.get_conversation_history(result["conversation_id"])
        if history:
            print("\n📜 تاریخچه مکالمه:")
            for msg in history["messages"]:
                print(f"\n[{msg['role'].upper()}] {msg['timestamp']}")
                print(f"{msg['content'][:200]}...")

    # Save
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log.info(f"Result saved to {args.output}")


if __name__ == "__main__":
    main()
