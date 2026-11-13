"""
Graph-Enhanced Legal Chatbot
=============================

Advanced chatbot with Knowledge Graph integration.

Features:
- Graph-based context enrichment
- Multi-turn conversations
- Citation tracking
- Confidence scoring
- Document processing integration
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime

# Graph integration — connection obtained via get_connection() at runtime
from graph.services.query_service import QueryService
from graph.services.rag_integration import RAGIntegrationService

# Document processing
from scripts.document_processor.processor import DocumentProcessor
from scripts.document_processor.file_manager import FileManager

# Core components
from mahoun.flows.enhanced_rag import EnhancedRAGPipeline
from mahoun.core.logging import setup_logger

logger = setup_logger(__name__)


@dataclass
class Message:
    """Chat message"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str
    metadata: Dict = None


@dataclass
class GraphContext:
    """Graph-enriched context"""
    related_articles: List[Dict]
    related_verdicts: List[Dict]
    citation_network: List[Dict]
    legal_concepts: List[str]


class GraphEnhancedChatbot:
    """
    Advanced chatbot with Knowledge Graph integration
    
    Combines:
    - RAG pipeline for retrieval
    - Knowledge Graph for context enrichment
    - Document processing for new files
    - Multi-turn conversation management
    """
    
    def __init__(
        self,
        enable_graph: bool = True,
        enable_document_processing: bool = True,
        max_history: int = 5
    ):
        """
        Initialize chatbot
        
        Args:
            enable_graph: Enable graph integration
            enable_document_processing: Enable document processing
            max_history: Maximum conversation history
        """
        self.max_history = max_history
        self.conversations = {}
        
        # Initialize RAG pipeline
        logger.info("Initializing RAG pipeline...")
        self.rag_pipeline = EnhancedRAGPipeline()
        
        # Initialize graph components
        self.enable_graph = enable_graph
        if enable_graph:
            try:
                logger.info("Initializing graph components...")
                # GOVERNANCE: use get_connection() (canonical governed singleton).
                # Direct Neo4jConnection() construction is constitutionally forbidden
                # outside mahoun/graph/neo4j/connection.py.
                from mahoun.graph.neo4j.connection import get_connection
                self.graph_connection = get_connection()
                self.query_service = QueryService(self.graph_connection)
                self.rag_integration = RAGIntegrationService(self.graph_connection)
            except Exception as e:
                logger.warning(f"Graph initialization failed: {e}")
                self.enable_graph = False
        
        # Initialize document processor
        self.enable_document_processing = enable_document_processing
        if enable_document_processing:
            try:
                logger.info("Initializing document processor...")
                self.file_manager = FileManager()
                self.doc_processor = DocumentProcessor(self.file_manager)
            except Exception as e:
                logger.warning(f"Document processor initialization failed: {e}")
                self.enable_document_processing = False
        
        logger.info("Graph-Enhanced Chatbot initialized")
    
    def create_conversation(self) -> str:
        """Create new conversation"""
        conv_id = str(uuid.uuid4())
        self.conversations[conv_id] = {
            'id': conv_id,
            'messages': [],
            'graph_context': None,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
        }
        return conv_id
    
    def add_message(self, conv_id: str, role: str, content: str, metadata: Dict = None):
        """Add message to conversation"""
        if conv_id not in self.conversations:
            raise ValueError(f"Conversation {conv_id} not found")
        
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {}
        )
        
        self.conversations[conv_id]['messages'].append(message)
        self.conversations[conv_id]['updated_at'] = datetime.now().isoformat()
        
        # Trim history
        if len(self.conversations[conv_id]['messages']) > self.max_history * 2:
            self.conversations[conv_id]['messages'] = \
                self.conversations[conv_id]['messages'][-(self.max_history * 2):]
    
    def enrich_with_graph(self, query: str, retrieved_docs: List[Dict]) -> Optional[GraphContext]:
        """
        Enrich results with graph context
        
        Args:
            query: User query
            retrieved_docs: Retrieved documents
        
        Returns:
            Graph context or None
        """
        if not self.enable_graph:
            return None
        
        try:
            # Enrich results with graph
            enriched = self.rag_integration.enrich_results(
                retrieved_docs,
                max_depth=2
            )
            
            # Extract graph context
            related_articles = []
            related_verdicts = []
            citation_network = []
            legal_concepts = set()
            
            for doc in enriched:
                graph_data = doc.get('graph_context', {})
                
                # Collect related articles
                if 'related_articles' in graph_data:
                    related_articles.extend(graph_data['related_articles'])
                
                # Collect related verdicts
                if 'related_verdicts' in graph_data:
                    related_verdicts.extend(graph_data['related_verdicts'])
                
                # Collect citations
                if 'citations' in graph_data:
                    citation_network.extend(graph_data['citations'])
                
                # Extract legal concepts
                if 'concepts' in graph_data:
                    legal_concepts.update(graph_data['concepts'])
            
            return GraphContext(
                related_articles=related_articles[:5],
                related_verdicts=related_verdicts[:5],
                citation_network=citation_network[:10],
                legal_concepts=list(legal_concepts)[:10]
            )
        
        except Exception as e:
            logger.error(f"Graph enrichment failed: {e}")
            return None
    
    def format_response(
        self,
        answer: str,
        retrieved_docs: List[Dict],
        graph_context: Optional[GraphContext],
        confidence: float
    ) -> str:
        """
        Format final response with citations and graph context
        
        Args:
            answer: Generated answer
            retrieved_docs: Retrieved documents
            graph_context: Graph context
            confidence: Confidence score
        
        Returns:
            Formatted response
        """
        response = answer + "\n\n"
        
        # Add citations
        if retrieved_docs:
            response += "📚 **منابع:**\n"
            for i, doc in enumerate(retrieved_docs[:3], 1):
                response += f"{i}. {doc.get('metadata', {}).get('source', 'Unknown')}\n"
                response += f"   امتیاز: {doc.get('score', 0):.2f}\n"
            response += "\n"
        
        # Add graph context
        if graph_context:
            if graph_context.related_articles:
                response += "📖 **مواد مرتبط:**\n"
                for article in graph_context.related_articles[:3]:
                    response += f"- ماده {article.get('number', '?')}\n"
                response += "\n"
            
            if graph_context.related_verdicts:
                response += "⚖️ **آرای مرتبط:**\n"
                for verdict in graph_context.related_verdicts[:3]:
                    response += f"- {verdict.get('id', 'Unknown')}\n"
                response += "\n"
            
            if graph_context.legal_concepts:
                response += f"🔑 **مفاهیم کلیدی:** {', '.join(graph_context.legal_concepts[:5])}\n\n"
        
        # Add confidence
        conf_emoji = "🟢" if confidence > 0.8 else "🟡" if confidence > 0.6 else "🔴"
        response += f"{conf_emoji} **سطح اطمینان:** {confidence:.0%}\n"
        
        return response
    
    def chat(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        top_k: int = 5
    ) -> Dict:
        """
        Main chat interface
        
        Args:
            query: User query
            conversation_id: Conversation ID (creates new if None)
            top_k: Number of documents to retrieve
        
        Returns:
            Response dictionary
        """
        # Create or get conversation
        if conversation_id is None:
            conversation_id = self.create_conversation()
            logger.info(f"New conversation: {conversation_id}")
        
        # Add user message
        self.add_message(conversation_id, "user", query)
        
        # Process new documents if enabled
        if self.enable_document_processing:
            new_files = self.file_manager.get_new_files()
            if new_files:
                logger.info(f"Processing {len(new_files)} new files...")
                self.doc_processor.process_all_new_files()
        
        # Retrieve documents
        logger.info(f"Retrieving for: {query}")
        retrieved_docs = self.rag_pipeline.retrieve(query, top_k=top_k)
        
        # Enrich with graph
        graph_context = self.enrich_with_graph(query, retrieved_docs)
        
        # Generate answer
        answer = self.rag_pipeline.generate_answer(query, retrieved_docs)
        
        # Calculate confidence
        confidence = self._calculate_confidence(retrieved_docs)
        
        # Format response
        formatted_response = self.format_response(
            answer,
            retrieved_docs,
            graph_context,
            confidence
        )
        
        # Add assistant message
        self.add_message(
            conversation_id,
            "assistant",
            formatted_response,
            metadata={
                'confidence': confidence,
                'num_sources': len(retrieved_docs),
                'graph_enriched': graph_context is not None
            }
        )
        
        # Store graph context
        if graph_context:
            self.conversations[conversation_id]['graph_context'] = asdict(graph_context)
        
        return {
            'conversation_id': conversation_id,
            'query': query,
            'answer': formatted_response,
            'confidence': confidence,
            'sources': retrieved_docs,
            'graph_context': asdict(graph_context) if graph_context else None,
            'history_length': len(self.conversations[conversation_id]['messages']),
        }
    
    def _calculate_confidence(self, retrieved_docs: List[Dict]) -> float:
        """Calculate confidence score"""
        if not retrieved_docs:
            return 0.0
        
        top_score = retrieved_docs[0].get('score', 0)
        avg_score = sum(d.get('score', 0) for d in retrieved_docs) / len(retrieved_docs)
        
        confidence = 0.6 * top_score + 0.4 * avg_score
        
        return min(confidence, 1.0)
    
    def get_conversation(self, conversation_id: str) -> Optional[Dict]:
        """Get conversation history"""
        conv = self.conversations.get(conversation_id)
        if not conv:
            return None
        
        return {
            'conversation_id': conv['id'],
            'created_at': conv['created_at'],
            'updated_at': conv['updated_at'],
            'messages': [asdict(m) for m in conv['messages']],
            'graph_context': conv.get('graph_context'),
            'total_messages': len(conv['messages']),
        }
    
    def close(self):
        """Close connections"""
        if self.enable_graph and hasattr(self, 'graph_connection'):
            self.graph_connection.close()


def main():
    """CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Graph-Enhanced Legal Chatbot')
    parser.add_argument('--query', required=True, help='User query')
    parser.add_argument('--conversation_id', help='Continue conversation')
    parser.add_argument('--top_k', type=int, default=5, help='Number of documents')
    parser.add_argument('--no-graph', action='store_true', help='Disable graph')
    parser.add_argument('--output', help='Save to JSON')
    
    args = parser.parse_args()
    
    # Initialize chatbot
    chatbot = GraphEnhancedChatbot(
        enable_graph=not args.no_graph,
        enable_document_processing=True
    )
    
    try:
        # Chat
        result = chatbot.chat(
            args.query,
            conversation_id=args.conversation_id,
            top_k=args.top_k
        )
        
        # Display
        print("\n" + "="*80)
        print(f"🗨️  سوال: {result['query']}")
        print("="*80)
        print(f"\n{result['answer']}")
        print("\n" + "="*80)
        print(f"📊 آمار:")
        print(f"   - شناسه: {result['conversation_id']}")
        print(f"   - اطمینان: {result['confidence']:.0%}")
        print(f"   - منابع: {len(result['sources'])}")
        print(f"   - گراف: {'✓' if result['graph_context'] else '✗'}")
        print("="*80 + "\n")
        
        # Save
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved to {args.output}")
    
    finally:
        chatbot.close()


if __name__ == '__main__':
    main()
