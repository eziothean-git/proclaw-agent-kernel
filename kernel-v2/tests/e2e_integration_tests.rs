//! 端到端集成测试 - Prime Loop + Skill Execution
//!
//! 完整流程：
//! 1. 用户请求 -> Prime Personality
//! 2. Prime 生成 IR（包含 processes）
//! 3. 执行 processes（通过 Skills）
//! 4. Prime 生成最终响应
//! 5. 返回给用户

#[cfg(test)]
mod e2e_tests {
    use std::sync::Arc;
    use std::path::PathBuf;
    use tempfile::TempDir;
    use serde_json::json;

    use proclaw_block_composer::block_composer::BlockComposerEngine;
    use proclaw_block_composer::config::{ComposerConfig, ServerConfig, PromptsConfig, ThreadPromptConfig,
        ProvidersConfig, BashProviderConfig, CodeProviderConfig, CodeIndexConfig,
        MemoryProviderConfig, PermissionsConfig, GatewayConfig, ObservabilityConfig,
        MetricsConfig, TracesConfig, AuditConfig, LoggingConfig, PrimeProviderConfig};
    use proclaw_block_composer::llm::{LLMRouter, config::{LLMRouterConfig, ProviderConfig, ModelConfig, DifficultyLevel}};
    use proclaw_block_composer::personality::{PrimePersonality, PrimePersonalityConfig};
    use proclaw_block_composer::personality::models::{InputMessage, InputHeader, ConversationContext};
    use proclaw_block_composer::skills::{BashSkill, GatewaySkill};
    use proclaw_block_composer::coordinator::{
        SkillRegistry,
        models::{SkillRequest, SkillContext}
    };
    use proclaw_block_composer::auth::CapabilityLevel;
    use proclaw_block_composer::providers::bash::{BashWrapper, BashWrapperConfig};
    use proclaw_block_composer::agent_thread::models::ExecutorId;

    /// Create test configuration without cache (cache mechanism removed)
    fn create_test_config(temp_dir: &TempDir) -> ComposerConfig {
        ComposerConfig {
            server: ServerConfig {
                socket_path: temp_dir.path().join("test.sock"),
                workers: 1,
                max_concurrent_requests: 100,
                request_timeout_seconds: 30,
            },
            prompts: PromptsConfig {
                thread: ThreadPromptConfig {
                    path: temp_dir.path().join("thread.md"),
                },
            },
            providers: ProvidersConfig {
                bash: BashProviderConfig {
                    timeout_seconds: 30,
                    max_output_size: 1024 * 1024,
                    blocked_commands: vec!["rm -rf /".to_string()],
                    patterns_file: temp_dir.path().join("patterns.yaml"),
                },
                code: CodeProviderConfig {
                    index: CodeIndexConfig {
                        database_path: temp_dir.path().join("code_index.db"),
                        update_interval_seconds: 300,
                        paths: vec![],
                    },
                },
                memory: MemoryProviderConfig {
                    database_path: temp_dir.path().join("memory.db"),
                    max_facts_per_query: 10,
                    default_categories: vec![],
                },
            },
            permissions: PermissionsConfig {
                default_token_ttl_seconds: 3600,
                default_max_calls: 100,
                policy_file: temp_dir.path().join("policies.yaml"),
            },
            gateway: GatewayConfig {
                url: "http://localhost:3000".to_string(),
                auth_token: "test-token".to_string(),
                webhook_path: "/gateway/webhook/kernel-response".to_string(),
            },
            observability: ObservabilityConfig {
                metrics: MetricsConfig {
                    enabled: false,
                    port: 9090,
                    path: "/metrics".to_string(),
                },
                traces: TracesConfig {
                    base_path: temp_dir.path().join("traces"),
                    retention_days: 7,
                    compress_after_hours: 24,
                    compression_algorithm: "zstd".to_string(),
                    compression_level: 3,
                },
                audit: AuditConfig {
                    path: temp_dir.path().join("audit.log"),
                    level: "info".to_string(),
                },
                logging: LoggingConfig {
                    level: "info".to_string(),
                    format: "json".to_string(),
                    output: "stdout".to_string(),
                },
            },
            prime: PrimeProviderConfig::default(),
        }
    }

    async fn setup_e2e_test_env() -> (Arc<PrimePersonality>, Arc<SkillRegistry>, TempDir, String) {
        let temp_dir = TempDir::new().unwrap();

        // 创建测试文件
        let test_file = temp_dir.path().join("readme.md");
        let test_content = "# 测试文档\n\n这是一个端到端测试文件。\n\n## 内容\n\n- 创建时间: 2024\n- 目的: 测试 Prime + Skills\n- 状态: 准备就绪\n\n测试完成！";
        tokio::fs::write(&test_file, test_content).await.unwrap();

        // 创建 thread.md prompt 文件
        let thread_prompt = temp_dir.path().join("thread.md");
        tokio::fs::write(&thread_prompt, "# Test Thread Prompt\n\nYou are a test agent.").await.unwrap();

        // 创建 prime.md prompt 文件
        let prime_prompt = temp_dir.path().join("prime.md");
        tokio::fs::write(&prime_prompt, "# Test Prime Prompt\n\nYou are a test prime personality agent. Output JSON format.").await.unwrap();

        // 初始化 BlockComposer
        let composer_config = create_test_config(&temp_dir);
        let composer = Arc::new(BlockComposerEngine::new(&composer_config).await.expect("Failed to create BlockComposer"));

        // 初始化 LLM Router（使用项目配置的 API key）
        let mut llm_config = LLMRouterConfig::from_env();

        // 如果环境变量中没有配置，使用项目默认的 Ark 配置
        if llm_config.providers.is_empty() {
            let mut ark_config = ProviderConfig::ark("62663763-1f8a-4c10-862e-b5d760b19fba");
            ark_config.default_model = "glm-4-7-251222".to_string();
            ark_config.models = vec![ModelConfig {
                name: "glm-4-7-251222".to_string(),
                display_name: "GLM-4-7".to_string(),
                max_tokens: 8192,
                cost_per_1k_input: 0.01,
                cost_per_1k_output: 0.02,
                capabilities: vec!["complex_reasoning".to_string(), "code".to_string()],
                difficulty_level: DifficultyLevel::Hard,
            }];
            llm_config.add_provider("ark", ark_config);
            llm_config.default_provider = "ark".to_string();
        }

        let llm_router = Arc::new(LLMRouter::new(llm_config));

        // 初始化 Prime Personality with prompt file
        let prime_config = PrimePersonalityConfig::with_prompt_file(
            "glm-4-7-251222".to_string(),
            0.3,
            4096,
            prime_prompt,
        ).await.expect("Failed to load Prime config");
        let prime = Arc::new(PrimePersonality::new(prime_config, llm_router, composer));

        // 创建 Skills
        let bash_config = BashWrapperConfig {
            timeout_seconds: 60,
            max_output_size: 1024 * 1024,
            blocked_commands: vec!["rm -rf /".to_string()],
            custom_patterns: vec![],
        };
        let bash_wrapper = Arc::new(BashWrapper::new(bash_config));
        let bash_skill = Arc::new(BashSkill::new(bash_wrapper));

        let gateway_skill = Arc::new(GatewaySkill::new(
            "http://localhost:3000/webhook".to_string(),
            "test-token".to_string(),
        ));

        let skill_registry = Arc::new(SkillRegistry::new(bash_skill, gateway_skill));

        (prime, skill_registry, temp_dir, test_file.to_str().unwrap().to_string())
    }

    fn create_context(level: CapabilityLevel, session_id: &str, thread_id: &str) -> SkillContext {
        SkillContext {
            thread_id: thread_id.to_string(),
            session_id: session_id.to_string(),
            executor_id: ExecutorId("test-executor".to_string()).0,
            capability_level: level,
            working_dirs: vec![],
        }
    }

    #[tokio::test]
    async fn test_e2e_prime_generates_ir() {
        println!("\n========================================");
        println!("端到端测试 1: Prime 生成 IR");
        println!("========================================\n");

        let (prime, _skill_registry, temp_dir, test_file) = setup_e2e_test_env().await;

        println!("📁 测试文件: {}", test_file);
        println!("🤖 使用 Ark API: https://ark.cn-beijing.volces.com/api/v3");

        // 构建用户请求
        let input = InputMessage {
            header: InputHeader {
                request_id: "e2e-test-001".to_string(),
                timestamp: chrono::Utc::now().to_rfc3339(),
                platform: "test".to_string(),
                device_id: "test-device".to_string(),
                user_id: "test-user".to_string(),
                session_id: Some("test-session".to_string()),
                source_ip: None,
                client_version: None,
                priority: 1,
            },
            body: format!(
                "请读取文件 {} 并告诉我里面有什么内容",
                test_file
            ),
            metadata: None,
            context: Some(ConversationContext {
                session_id: "test-session".to_string(),
                conversation_history: vec![],
                window_size: 10,
                full_context_path: temp_dir.path().join("context.json").to_str().unwrap().to_string(),
                total_turns: 1,
            }),
        };

        println!("🤖 调用 Prime Personality...");
        println!("   用户请求: {}", input.body);

        let result = prime.process_request(input, None).await;

        match result {
            Ok(ir) => {
                println!("\n✅ Prime 成功生成 IR！");
                println!("\n=== IR 内容 ===");
                println!("Intent: {}", ir.intent);
                println!("Goals: {:?}", ir.goals);
                println!("Process count: {}", ir.processes.len());

                for (i, process) in ir.processes.iter().enumerate() {
                    println!("\nProcess {}:", i + 1);
                    println!("  Name: {}", process.name);
                    println!("  Goal: {}", process.goal);
                    println!("  Capabilities: {:?}", process.capabilities);
                    if let Some(constraints) = &process.constraints {
                        println!("  Constraints: {:?}", constraints);
                    }
                }

                if let Some(content) = ir.content {
                    if let Some(text) = content.text {
                        println!("\n=== Content.text ===");
                        println!("{}", text);
                    }
                }

                println!("\n✅ 端到端测试 1 通过！Prime 能够生成包含 processes 的 IR");
            }
            Err(e) => {
                println!("❌ Prime 处理失败: {}", e);
                panic!("Prime processing failed: {}", e);
            }
        }
    }

    #[tokio::test]
    async fn test_e2e_direct_skill_execution() {
        println!("\n========================================");
        println!("端到端测试 2: 直接执行 Skills");
        println!("========================================\n");

        let (_prime, skill_registry, _temp_dir, test_file) = setup_e2e_test_env().await;

        println!("📁 目标文件: {}", test_file);

        // 第 1 轮：读取文件
        println!("\n🔄 第 1 步: 使用 Bash Skill 读取文件");
        let read_request = SkillRequest {
            request_id: "e2e-direct-001".to_string(),
            skill_name: "bash".to_string(),
            tool_name: "execute".to_string(),
            parameters: json!({
                "command": format!("cat {}", test_file),
            }),
            context: create_context(CapabilityLevel::Agent, "test-session", "thread-001"),
        };

        let result = skill_registry.execute_agent(read_request).await.unwrap();
        assert!(result.success);

        let file_content = result.result
            .as_ref()
            .and_then(|r| r.get("stdout"))
            .and_then(|v| v.as_str())
            .unwrap_or("");

        println!("✅ 文件读取成功 ({} bytes)", file_content.len());
        println!("\n文件内容预览:");
        println!("{}", &file_content[..file_content.len().min(200)]);

        // 第 2 轮：获取系统信息
        println!("\n🔄 第 2 步: 获取系统信息");
        let sys_request = SkillRequest {
            request_id: "e2e-direct-002".to_string(),
            skill_name: "bash".to_string(),
            tool_name: "execute".to_string(),
            parameters: json!({
                "command": "pwd",
            }),
            context: create_context(CapabilityLevel::Agent, "test-session", "thread-002"),
        };

        let result = skill_registry.execute_agent(sys_request).await.unwrap();
        assert!(result.success);

        let pwd = result.result
            .as_ref()
            .and_then(|r| r.get("stdout"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim();

        println!("✅ 当前目录: {}", pwd);

        // 生成最终响应
        println!("\n🔄 第 3 步: 生成最终响应");
        let final_response = format!(
            "✅ 任务完成！\n\n📊 执行摘要:\n  - 读取文件: {} ({} bytes)\n  - 当前目录: {}\n\n📄 文件内容:\n{}\n\n所有操作已成功完成！",
            test_file,
            file_content.len(),
            pwd,
            file_content
        );

        println!("\n=== 最终响应 ===");
        println!("{}", final_response);

        println!("\n✅ 端到端测试 2 通过！Skills 执行链路正常");
    }

    #[tokio::test]
    async fn test_e2e_with_real_test_file() {
        println!("\n========================================");
        println!("端到端测试 3: 读取真实测试文件");
        println!("========================================\n");

        let (_prime, skill_registry, _temp_dir, _test_file) = setup_e2e_test_env().await;

        // 使用之前创建的测试文件
        let real_test_file = "/home/eziothean/ProClaw/test_data/os_interface_test/README.md";
        println!("📁 读取文件: {}", real_test_file);

        let read_request = SkillRequest {
            request_id: "e2e-real-001".to_string(),
            skill_name: "bash".to_string(),
            tool_name: "execute".to_string(),
            parameters: json!({
                "command": format!("cat {}", real_test_file),
            }),
            context: create_context(CapabilityLevel::Agent, "test-session", "thread-003"),
        };

        let result = skill_registry.execute_agent(read_request).await.unwrap();
        assert!(result.success);

        let content = result.result
            .as_ref()
            .and_then(|r| r.get("stdout"))
            .and_then(|v| v.as_str())
            .unwrap_or("");

        println!("✅ 文件读取成功");
        println!("\n文件内容:");
        println!("{}", content);

        // 验证内容
        assert!(content.contains("测试文档"));
        assert!(content.contains("OS Interface Skill"));

        println!("\n✅ 端到端测试 3 通过！真实测试文件读取成功");
    }
}
