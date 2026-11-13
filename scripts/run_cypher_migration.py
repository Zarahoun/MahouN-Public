#!/usr/bin/env python3
"""
Neo4j Cypher Migration Runner
=============================
Executes Cypher schema migrations against Neo4j database using governed execution path.
All schema migrations follow MAHOUN governance requirements with proper authorization,
audit trails, and provenance tracking.
"""

import sys
import logging
from pathlib import Path
import os
import uuid
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_cypher_migration(migration_file: str):
    """Execute a Cypher migration file against Neo4j using governed execution path."""
    try:
        from mahoun.core.governance.governance_context import GovernanceContextManager
        from mahoun.core.governance.system_identities import SCHEMA_MIGRATION_ACTOR
        from mahoun.graph.neo4j.connection import Neo4jConnection
        
        # Read migration file
        migration_path = Path(migration_file)
        if not migration_path.exists():
            logger.error(f"Migration file not found: {migration_file}")
            return False
        
        cypher_content = migration_path.read_text(encoding='utf-8')
        logger.info(f"📋 Read migration file: {migration_file}")
        logger.info(f"📝 Migration size: {len(cypher_content)} characters")
        
        # Extract migration identity from filename for audit trail
        migration_id = migration_path.stem
        logger.info(f"🏷️  Migration ID: {migration_id}")
        
        # Generate correlation ID for this migration run
        correlation_id = f"migration_{migration_id}_{uuid.uuid4()}"
        logger.info(f"🔗 Correlation ID: {correlation_id}")
        
        # Get Neo4j connection details from environment
        uri = os.getenv('DB_NEO4J_URI', 'bolt://localhost:7687')
        user = os.getenv('DB_NEO4J_USER', 'neo4j')
        password = os.getenv('DB_NEO4J_PASSWORD', 'dev_password')
        
        logger.info(f"🔌 Connecting to Neo4j at {uri}")
        
        # Create Neo4j connection (uses existing driver ownership)
        connection = Neo4jConnection(uri, user, password)
        
        # Establish governance context with system:schema_migration actor
        ctx = GovernanceContextManager.create_context(
            correlation_id=correlation_id,
            execution_mode="STRICT",
            actor_id=SCHEMA_MIGRATION_ACTOR.id,
        )
        
        logger.info(f"🛡️  Governance context established: {SCHEMA_MIGRATION_ACTOR.id}")
        
        # Execute migration within governance context
        with ctx:
            with connection.governed_session(
                correlation_id=correlation_id,
                actor_id=SCHEMA_MIGRATION_ACTOR.id,
            ) as session:
                logger.info("✅ Governed session established")
                
                # Split into individual statements
                statements = [s.strip() for s in cypher_content.split(';') if s.strip()]
                logger.info(f"🔢 Found {len(statements)} Cypher statements")
                
                # Execute each statement through governed path
                success_count = 0
                fail_count = 0
                
                for i, statement in enumerate(statements, 1):
                    try:
                        logger.info(f"🔄 Executing statement {i}/{len(statements)}")
                        logger.debug(f"Statement: {statement[:100]}...")
                        
                        # Use governed execute_cypher() instead of raw session.run()
                        result = session.execute_cypher(statement)
                        success_count += 1
                        logger.info(f"✅ Statement {i} executed successfully (governed)")
                        
                    except Exception as e:
                        fail_count += 1
                        logger.error(f"❌ Statement {i} failed: {e}")
                        logger.error(f"Statement: {statement[:200]}...")
                
                logger.info(f"\n📊 Migration complete:")
                logger.info(f"   Total statements: {len(statements)}")
                logger.info(f"   Successful: {success_count}")
                logger.info(f"   Failed: {fail_count}")
                logger.info(f"   Governance: All operations audited")
                
                return fail_count == 0
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    migration_file = "/home/haji/Desktop/KingMahouN/data/migrations/v2_temporal_and_authority_schema.cypher"
    
    if len(sys.argv) > 1:
        migration_file = sys.argv[1]
    
    success = run_cypher_migration(migration_file)
    sys.exit(0 if success else 1)
