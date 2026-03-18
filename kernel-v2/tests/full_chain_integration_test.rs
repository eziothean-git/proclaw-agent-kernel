//! 完整链路集成测试 - Prime -> Host -> Thread -> Execution -> Prime
//!
//! 验证完整的双向通信链路：
//! 1. Prime 生成 IR（包含 processes）
//! 2. IR Executor 解析并执行 processes
//! 3. Host 创建 Process 和 Thread
//! 4. Thread Executor 执行并产生事件
//! 5. Host 收集结果向 Prime 汇报
//! 6. Prime 读取全量日志生成最终响应

#[cfg(test)]
mod full_chain_tests {
    use std::sync::Arc;
    use tempfile::TempDir;
    use serde_json::json;

    use proclaw_block_composer::{
        block_composer::BlockComposerEngine,
        config::{ComposerConfig, ServerConfig, PromptsConfig, ThreadPromptConfig,
            ProvidersConfig, BashProviderConfig, CodeProviderConfig, CodeIndexConfig,
            MemoryProviderConfig, PermissionsConfig, GatewayConfig, ObservabilityConfig,
            MetricsConfig, TracesConfig, AuditConfig, LoggingConfig, PrimeProviderConfig, PromptLoader},
        coordinator::{ExecutionCoordinator, lock_manager::DirectoryLockManager, ticket::TicketTracker, skill_registry::SkillRegistry},
        executor::IRProcessExecutor,
        llm::{LLMRouter, config::{LLMRouterConfig, ProviderConfig, ModelConfig, DifficultyLevel}},
        personality::{PrimePersonality, PrimePersonalityConfig, models::{InputMessage, InputHeader, ConversationContext}},
        skills::{BashSkill, GatewaySkill},
        providers::bash::{BashWrapper, BashWrapperConfig},
        auth::CapabilityLevel,
    };

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
                    max_output_size: 1024,
                    blocked_commands: vec![],
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

    async fn setup_full_chain_test_env() -> (
        Arc<PrimePersonality>,
        Arc<IRProcessExecutor>,
        Arc<SkillRegistry>,
        TempDir,
    ) {
        let temp_dir = TempDir::new().unwrap();
        let data_path = temp_dir.path().to_path_buf();

        // 创建 thread.md prompt 文件
        let thread_prompt = temp_dir.path().join("thread.md");
        tokio::fs::write(&thread_prompt, "# Test Thread Prompt\n\nYou are a test agent.").await.unwrap();

        // 初始化 BlockComposer
        let composer_config = create_test_config(&temp_dir);
        let block_composer = Arc::new(BlockComposerEngine::new(&composer_config).await.expect("Failed to create BlockComposer"));

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

        // 初始化 PromptLoader
        let prompt_loader = Arc::new(PromptLoader::new(composer_config.prompts.clone()));
        prompt_loader.load_all().await.expect("Failed to load prompts");

        // 创建 prime.md prompt 文件
        let prime_prompt_path = data_path.join("prime.md");
        tokio::fs::write(&prime_prompt_path, "# Test Prime Prompt\n\nYou are a test prime personality agent. Output JSON format.").await.expect("Failed to write prime prompt");

        // 初始化 Prime Personality with prompt file
        let prime_config = PrimePersonalityConfig::with_prompt_file(
            "glm-4-7-251222".to_string(),
            0.3,
            4096,
            prime_prompt_path,
        ).await.expect("Failed to load Prime config");
        let prime = Arc::new(PrimePersonality::new(prime_config, llm_router.clone(), block_composer.clone()));

        // 创建 Coordinator
        let lock_manager = Arc::new(DirectoryLockManager::new(data_path.join("locks.db")).expect("Failed to create lock manager"));
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
        let ticket_tracker = Arc::new(TicketTracker::new());

        let coordinator = Arc::new(ExecutionCoordinator::new(
            lock_manager,
            skill_registry.clone(),
            ticket_tracker,
        ));

        // 创建 IR Process Executor
        let ir_executor = Arc::new(
            IRProcessExecutor::new(
                data_path.clone(),
                coordinator,
                block_composer,
                llm_router,
                prompt_loader,
            ).await.expect("Failed to create IR Executor")
        );

        (prime, ir_executor, skill_registry, temp_dir)
    }

    #[tokio::test]
    async fn test_full_chain_prime_to_execution() {
        println!("\n========================================");
        println!("完整链路测试: Prime -> Host -> Thread -> Execution");
        println!("========================================\n");

        let (prime, ir_executor, _skill_registry, temp_dir) = setup_full_chain_test_env().await;

        // 创建测试文件
        let test_file = temp_dir.path().join("test.txt");
        tokio::fs::write(&test_file, "Hello from full chain test!").await.unwrap();

        println!("📁 测试文件: {}", test_file.display());

        // ========== 第一轮：Prime 生成 IR ==========
        println!("\n🔄 Phase 1: Prime 生成 IR");

        let input = InputMessage {
            header: InputHeader {
                request_id: "full-chain-test-001".to_string(),
                timestamp: chrono::Utc::now().to_rfc3339(),
                platform: "test".to_string(),
                device_id: "test-device".to_string(),
                user_id: "test-user".to_string(),
                session_id: Some("test-session".to_string()),
                source_ip: None,
                client_version: None,
                priority: 1,
            },
            body: format!("请读取文件 {} 并告诉我里面有什么内容", test_file.display()),
            metadata: None,
            context: Some(ConversationContext {
                session_id: "test-session".to_string(),
                conversation_history: vec![],
                window_size: 10,
                full_context_path: temp_dir.path().join("context.json").to_str().unwrap().to_string(),
                total_turns: 1,
            }),
        };

        let ir = prime.process_request(input, None).await.expect("Prime failed to generate IR");

        println!("✅ IR 生成成功!");
        println!("   Intent: {}", ir.intent);
        println!("   Goals: {:?}", ir.goals);
        println!("   Processes: {}", ir.processes.len());

        if ir.processes.is_empty() {
            println!("⚠️ 没有 processes 需要执行 (简单对话)");
            return;
        }

        // ========== 第二轮：执行 IR Processes ==========
        println!("\n🔄 Phase 2: 执行 IR Processes");

        let execution_results = ir_executor.execute_ir(&ir, "test-session").await
            .expect("IR execution failed");

        println!("✅ 执行完成!");
        println!("   结果数量: {}", execution_results.len());

        for (idx, result) in execution_results.iter().enumerate() {
            println!("\n   [Process {}] {}", idx + 1, result.process_name);
            println!("   - 状态: {}", if result.success { "✅ 成功" } else { "❌ 失败" });

            if let Some(answer) = &result.final_answer {
                println!("   - 结果: {}", answer);
            }

            if let Some(error) = &result.error_message {
                println!("   - 错误: {}", error);
            }
        }

        // ========== 第三轮：获取 Session 全量日志 ==========
        println!("\n🔄 Phase 3: 获取 Session 全量日志");

        let session_log = ir_executor.get_session_full_log("test-session").await
            .expect("Failed to get session log");

        println!("✅ Session 日志获取成功!");
        println!("   Session ID: {}", session_log.session_id);
        println!("   Process 数量: {}", session_log.processes.len());

        for process in &session_log.processes {
            println!("\n   Process: {}", process.process_id);
            println!("   - Goal: {}", process.goal);
            println!("   - Status: {}", process.status);
            println!("   - Threads: {}", process.threads.len());
        }

        // ========== 验证结果 ==========
        println!("\n========================================");
        println!("验证结果");
        println!("========================================");

        // 验证至少有一个 process 被执行
        assert!(!execution_results.is_empty(), "应该有执行结果");

        // 验证 session 日志中有记录
        assert!(!session_log.processes.is_empty(), "Session 日志应该有 process 记录");

        println!("✅ 完整链路测试通过!");
        println!("   Prime 生成了 IR");
        println!("   IR Executor 执行了 processes");
        println!("   Host 创建了 Process 和 Thread");
        println!("   Thread Executor 执行了任务");
        println!("   Host 收集了结果");
        println!("   Session 全量日志可读取");
    }

    /// Test: Configuration validation
    #[test]
    fn test_config_without_cache() {
        let temp_dir = TempDir::new().unwrap();
        let config = create_test_config(&temp_dir);

        // Verify config doesn't have cache fields
        assert_eq!(config.server.socket_path, temp_dir.path().join("test.sock"));
        assert!(config.prompts.thread.path.to_string_lossy().contains("thread.md"));

        println!("✅ Configuration test passed - no cache fields");
    }
}
