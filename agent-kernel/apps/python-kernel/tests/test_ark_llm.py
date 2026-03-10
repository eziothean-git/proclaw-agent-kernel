"""
Test Ark (Volcengine) LLM Integration

Usage:
    python tests/test_ark_llm.py
"""
import asyncio
import os
import sys

sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')

# 配置 Ark 环境变量（如果未设置则使用默认值）
if not os.environ.get("LLM_PROVIDER"):
    os.environ["LLM_PROVIDER"] = "ark"
if not os.environ.get("ARK_API_KEY"):
    os.environ["ARK_API_KEY"] = "62663763-1f8a-4c10-862e-b5d760b19fba"
if not os.environ.get("ARK_BASE_URL"):
    os.environ["ARK_BASE_URL"] = "https://ark.cn-beijing.volces.com/api/v3"
if not os.environ.get("ARK_MODEL"):
    os.environ["ARK_MODEL"] = "doubao-seed-2-0-mini-260215"  # 使用更便宜的模型

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


async def test_ark_connection():
    """Test Ark LLM connection"""
    print_header("ARK (VOLCENGINE) LLM TEST")
    
    # Load config
    print("1. Loading Ark configuration...")
    config = LLMConfig.from_env()
    
    print(f"   Provider: {config.provider}")
    print(f"   Model: {config.model}")
    print(f"   Base URL: {config.base_url}")
    print(f"   API Key: {'*' * 10}{config.api_key[-4:] if config.api_key else 'NOT SET'}")
    
    if not config.api_key:
        print(f"\n   {Colors.RED}✗ No API key configured!{Colors.END}")
        return False
    
    print()
    
    # Initialize client
    print("2. Initializing LLM client...")
    client = get_llm_client()
    
    success = client.initialize(
        system_prompt="You are a helpful assistant for software development tasks."
    )
    
    if not success:
        print(f"   {Colors.RED}✗ Failed to initialize LLM client!{Colors.END}")
        return False
    
    print(f"   {Colors.GREEN}✓ LLM client initialized successfully{Colors.END}")
    print()
    
    # Test simple generation
    print("3. Testing simple generation...")
    try:
        prompt = """Generate a simple YAML structure for a tool call.

Task: "Read the file '/tmp/test.txt'"

Respond with only the YAML:
"""
        
        print("   Sending prompt to Ark API...")
        result = await client.generate(prompt)
        
        print(f"   {Colors.GREEN}✓ Generation successful!{Colors.END}")
        print("\n   Generated output:")
        print("   " + "-" * 66)
        for line in (result[:400] if len(result) > 400 else result).split('\n'):
            print(f"   {line}")
        print("   " + "-" * 66)
        
    except Exception as e:
        print(f"   {Colors.RED}✗ Generation failed: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # Test with code task
    print("4. Testing code task parsing...")
    try:
        prompt = """Parse this task and determine the intent:
Task: "Read the main.py file and analyze its structure"

Respond in YAML format:
intent: [read_file|analyze_code|refactor|other]
file: filename or null
reasoning: brief explanation
"""
        
        result = await client.generate(prompt)
        
        print(f"   {Colors.GREEN}✓ Code task parsing successful!{Colors.END}")
        print(f"\n   Result preview:")
        for line in result[:300].split('\n'):
            print(f"   {line}")
        
    except Exception as e:
        print(f"   {Colors.RED}✗ Code task parsing failed: {e}{Colors.END}")
        return False
    
    print()
    
    # Show model info
    print("5. Model information:")
    info = client.get_model_info()
    for key, value in info.items():
        print(f"   {key}: {value}")
    
    print()
    print_header("✓ ARK LLM TEST PASSED!")
    print(f"\n{Colors.GREEN}Your Ark (Volcengine) LLM is properly configured and working!{Colors.END}\n")
    
    return True


async def main():
    """Run Ark test"""
    try:
        success = await test_ark_connection()
        
        if not success:
            print(f"\n{Colors.RED}Test failed. Please check your configuration.{Colors.END}\n")
            return 1
        
        return 0
        
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
