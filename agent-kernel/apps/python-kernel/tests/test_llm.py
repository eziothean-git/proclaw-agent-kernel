"""
Test LLM Integration - Verify LLM client works with different providers

Usage:
    export LLM_PROVIDER=kimi
    export KIMI_API_KEY="your-key"
    python tests/test_llm.py

Or for OpenAI:
    export LLM_PROVIDER=openai
    export OPENAI_API_KEY="your-key"
    python tests/test_llm.py
"""
import asyncio
import os
import sys

sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')

import structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

from llm_client import get_llm_client, LLMConfig


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(title):
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{title.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")


def print_success(msg):
    print(f"{Colors.GREEN}✓{Colors.END} {msg}")


def print_error(msg):
    print(f"{Colors.RED}✗{Colors.END} {msg}")


def print_info(msg):
    print(f"{Colors.BLUE}ℹ{Colors.END} {msg}")


async def test_llm_connection():
    """Test LLM connection and generation"""
    print_header("LLM INTEGRATION TEST")
    
    # Load config from environment
    print("1. Loading configuration from environment...")
    config = LLMConfig.from_env()
    
    print_info(f"Provider: {config.provider}")
    print_info(f"Model: {config.model}")
    print_info(f"Base URL: {config.base_url or 'default'}")
    print_info(f"API Key: {'*' * 10}{config.api_key[-4:] if config.api_key else 'NOT SET'}")
    
    if not config.api_key:
        print_error("No API key configured!")
        print("\nPlease set one of:")
        print("  export KIMI_API_KEY='your-key'")
        print("  export OPENAI_API_KEY='your-key'")
        print("  export CUSTOM_API_KEY='your-key'")
        return False
    
    print()
    
    # Initialize client
    print("2. Initializing LLM client...")
    client = get_llm_client()
    
    success = client.initialize(
        system_prompt="You are a helpful assistant for software development tasks."
    )
    
    if not success:
        print_error("Failed to initialize LLM client!")
        return False
    
    print_success("LLM client initialized successfully")
    print()
    
    # Test simple generation
    print("3. Testing simple generation...")
    try:
        prompt = """Generate a simple YAML structure for a tool call.

Available tools:
- fs-skill.read_file: Read file contents
- fs-skill.write_file: Write file contents

User request: Read the file '/tmp/test.txt'

Respond with only the YAML:
"""
        
        result = await client.generate(prompt)
        
        print_success("Generation successful!")
        print("\nGenerated output:")
        print("-" * 70)
        print(result[:500] if len(result) > 500 else result)
        print("-" * 70)
        
        # Check if output looks reasonable
        if "yaml" in result.lower() or "tool" in result.lower() or "skill" in result.lower():
            print_success("Output appears to be valid")
        else:
            print_error("Output may not be in expected format")
            print("This might be OK depending on the model")
        
    except Exception as e:
        print_error(f"Generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # Test with system prompt
    print("4. Testing with system prompt context...")
    try:
        prompt = "What phase should I transition to after gathering enough information?"
        
        result = await client.generate(prompt)
        
        print_success("Context-aware generation successful!")
        print(f"Response: {result[:200]}...")
        
    except Exception as e:
        print_error(f"Context generation failed: {e}")
        return False
    
    print()
    
    # Show model info
    print("5. Model information:")
    info = client.get_model_info()
    for key, value in info.items():
        print_info(f"  {key}: {value}")
    
    print()
    print_header("✓ ALL TESTS PASSED!")
    
    return True


async def test_kimi_specific():
    """Test Kimi-specific features"""
    print_header("KIMI CODEPLAN SPECIFIC TEST")
    
    # Force Kimi configuration
    os.environ["LLM_PROVIDER"] = "kimi"
    
    if not os.environ.get("KIMI_API_KEY"):
        print_error("KIMI_API_KEY not set!")
        print("Set it with: export KIMI_API_KEY='your-key'")
        return False
    
    from llm_client import configure_llm
    
    print("Testing explicit Kimi configuration...")
    client = configure_llm(
        provider="kimi",
        api_key=os.environ["KIMI_API_KEY"],
        model="kimi-k2.5",
        temperature=0.7,
        max_tokens=2000,
    )
    
    success = client.initialize()
    if not success:
        print_error("Failed to initialize Kimi client")
        return False
    
    print_success("Kimi client initialized")
    
    # Test code generation
    print("\nTesting code-related generation...")
    prompt = """Parse this task and determine the intent:
Task: "Read the main.py file and analyze its structure"

Respond in YAML format:
intent: [read_file|analyze_code|refactor|other]
file: filename or null
reasoning: brief explanation
"""
    
    try:
        result = await client.generate(prompt)
        print_success("Code task parsing successful!")
        print(f"Result: {result[:300]}...")
        return True
    except Exception as e:
        print_error(f"Code task parsing failed: {e}")
        return False


async def main():
    """Run all tests"""
    # Test 1: General LLM connection
    success1 = await test_llm_connection()
    
    # Test 2: Kimi specific (only if provider is kimi)
    provider = os.environ.get("LLM_PROVIDER", "openai")
    if provider == "kimi":
        success2 = await test_kimi_specific()
    else:
        print_info(f"\nSkipping Kimi-specific tests (provider={provider})")
        success2 = True
    
    # Summary
    print("\n" + "="*70)
    if success1 and success2:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ ALL TESTS PASSED!{Colors.END}")
        print(f"\nYour LLM ({provider}) is properly configured and working.")
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ SOME TESTS FAILED{Colors.END}")
        print(f"\nPlease check your configuration and try again.")
    print("="*70 + "\n")


if __name__ == "__main__":
    # Check if running with default (no env vars set)
    provider = os.environ.get("LLM_PROVIDER", "")
    kimi_key = os.environ.get("KIMI_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    
    if not provider and not kimi_key and not openai_key:
        print("\n" + "="*70)
        print("WARNING: No LLM configuration detected!")
        print("="*70)
        print("\nPlease set environment variables before running:")
        print("\nFor Kimi CodePlan:")
        print("  export LLM_PROVIDER=kimi")
        print("  export KIMI_API_KEY='sk-kimi-...'")
        print("\nFor OpenAI:")
        print("  export LLM_PROVIDER=openai")
        print("  export OPENAI_API_KEY='sk-...'")
        print("\n" + "="*70 + "\n")
    
    asyncio.run(main())
