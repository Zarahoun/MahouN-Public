# MCP Server Configuration
# Production deployment guide

## MANDATORY AI AGENT CONSTITUTIONAL BOOTSTRAP

All AI agents working on MAHOUN MUST perform the following initialization before any analysis, planning, coding, modification, refactoring, testing, or architectural decision.

## Step 1 — Constitutional Loading

The agent MUST read and understand:

`/home/haji/Desktop/KingMahouN/mahoun/constitutional/constitution/CONSTITUTION.md`

This document is the root authority for MAHOUN development governance.

No repository action is authorized before constitutional loading is completed.

## Step 2 — Authority Hierarchy

The following authority hierarchy MUST be respected:

1. Constitutional documents
2. Workflow definitions
3. Agent role instructions
4. Repository implementation details
5. Local tooling and IDE metadata

Lower-level instructions MUST NEVER override higher-level authority.

## Step 3 — Source of Truth

The directory:

`/home/haji/Desktop/KingMahouN/mahoun/constitutional/`

is the single authoritative governance source for:

- Architecture decisions
- Governance boundaries
- Security rules
- API evolution policies
- Workflow execution rules
- Agent behavior constraints

## Step 4 — Forbidden Assumptions

Agents MUST NOT consider the following as architectural authority:

- `.ai/`
- `.cursor/`
- `.vscode/`
- IDE-generated instructions
- Client-specific metadata
- Generated files
- Temporary agent memory
- Previous agent assumptions

These sources may be consulted only when explicitly referenced by constitutional documents.

## Step 5 — Conflict Resolution

If any conflict exists between:

- Agent instructions
- IDE instructions
- Client configuration
- Generated metadata
- Existing implementation

the constitutional documents ALWAYS take precedence.

## Step 6 — Architectural Changes

Before performing any of the following actions, the agent MUST consult relevant constitutional documents:

- Creating new modules
- Moving files
- Changing public APIs
- Modifying governance logic
- Altering contracts/schema
- Changing workflow behavior
- Refactoring core architecture

## Step 7 — Fail Closed Rule

If constitutional documents cannot be accessed, are missing, ambiguous, or contradictory:

The agent MUST NOT proceed with architectural changes.

The agent MUST:

1. Report the conflict.
2. Identify the missing authority source.
3. Request clarification.

Silent assumption is prohibited.

## Final Rule

MAHOUN is governed by constitutional architecture.

Agents are execution units, not architectural authorities.

No agent, model, IDE, plugin, or client configuration may redefine MAHOUN architecture outside the constitutional process.

## Setup

### 1. Install dependencies
```bash
pip install -r mahoun/mcp/requirements.txt
```

### 2. Set environment variables
```bash
# REQUIRED: Set a strong API key
export MCP_API_KEY="your-super-secret-key-change-this"

# OPTIONAL: Neo4j connection (if using GraphTool)
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-neo4j-password"
```

### 3. Run the server
```bash
# Development
uvicorn mahoun.mcp.server:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn mahoun.mcp.server:app --host 0.0.0.0 --port 8000 --workers 4
```

## Security

### API Key Authentication
All requests to `/mcp` endpoint require a valid API key in the `X-API-Key` header.

Example request:
```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-super-secret-key-change-this" \
  -d '{
    "jsonrpc": "2.0",
    "method": "System.health",
    "id": 1
  }'
```

### Rate Limiting
- Default: 100 requests/minute per IP address
- Exceeding limit returns HTTP 429

### Production Checklist
- [ ] Change default API key (never use `dev-key-change-in-production`)
- [ ] Use HTTPS in production (configure reverse proxy)
- [ ] Set up firewall rules
- [ ] Enable logging to file/monitoring system
- [ ] Configure rate limiting for your use case
- [ ] Set up SSL certificates
- [ ] Use environment-specific configs

## Testing

Run tests:
```bash
pytest tests/test_mcp_server.py -v
```

## Monitoring

### Health Check
```bash
curl http://localhost:8000/health
```

### List Available Tools
```bash
curl http://localhost:8000/mcp/tools
```

## Error Codes

| Code | Name | Description |
|------|------|-------------|
| -32700 | Parse error | Invalid JSON |
| -32600 | Invalid Request | Invalid method format |
| -32601 | Method not found | Tool/function not found |
| -32602 | Invalid params | Invalid parameters |
| -32603 | Internal error | Server error |
| -32001 | DB unavailable | Database connection failed |
| -32002 | Timeout | Request timeout |
| -32003 | Unauthorized | Invalid/missing API key |
| -32004 | Rate limited | Too many requests |

## Performance Tips

1. **Use connection pooling** for database tools
2. **Enable caching** for frequently accessed data
3. **Monitor slow queries** and optimize
4. **Scale horizontally** with multiple workers
5. **Use async** whenever possible

## Troubleshooting

### "Missing API key" error
- Ensure `X-API-Key` header is set
- Check `MCP_API_KEY` environment variable

### "Tool not found" error
- Check tool registry in `mahoun/mcp/registry.py`
- Verify tool is properly imported

### Slow responses
- Check database connection
- Monitor with logging
- Consider caching

## Production Deployment

### Using Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
ENV MCP_API_KEY=change-this
CMD ["uvicorn", "mahoun.mcp.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Using systemd
```ini
[Unit]
Description=MAHOUN MCP Server
After=network.target

[Service]
Type=simple
User=mahoun
WorkingDirectory=/opt/mahoun
Environment="MCP_API_KEY=your-secret-key"
ExecStart=/opt/mahoun/venv/bin/uvicorn mahoun.mcp.server:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```
