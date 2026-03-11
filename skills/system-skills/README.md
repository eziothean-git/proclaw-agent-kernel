# System Skills

Core system skills for Agent Kernel Python Layer.

## Skills

### GatewayCallbackSkill

Sends HTTP callbacks to Gateway when processing is complete.

**Usage:**
```python
from skills.system-skills import get_callback_skill

skill = get_callback_skill()
await skill.send_completion(
    request_id="uuid",
    session_id="uuid",
    output="Hello! How can I help you?",
    actions=[]
)
```

**Environment Variables:**
- `GATEWAY_URL`: Gateway URL (default: http://localhost:3000)

**Features:**
- Automatic retry with exponential backoff
- Failed callback persistence
- Connection pooling for performance

## Architecture

System skills are designed to be:
- **Stateless**: No shared state between requests
- **Idempotent**: Safe to retry
- **Observable**: Full logging and error handling
- **Configurable**: Via environment variables