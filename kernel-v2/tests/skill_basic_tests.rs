//! OS Interface Skill 和 Scheduler Skill 基础测试
//!
//! 验证 Control Plane 技能的基础功能：
//! - OS Interface Skill (P0): create_process, list_sessions
//! - Scheduler Skill (P1): create_thread, list_threads
//! - 权限检查: P3 不能访问 P0/P1 技能

#[cfg(test)]
mod skill_tests {
    use std::sync::Arc;
    use tempfile::TempDir;
    use serde_json::json;
    
    use proclaw_block_composer::skills::{BashSkill, GatewaySkill};
    use proclaw_block_composer::coordinator::{
        SkillRegistry, 
        models::{SkillRequest, SkillContext}
    };
    use proclaw_block_composer::auth::CapabilityLevel;
    use proclaw_block_composer::agent_thread::models::ExecutorId;
    use proclaw_block_composer::providers::bash::{BashWrapper, BashWrapperConfig};

    async fn create_test_registry() -> Arc<SkillRegistry> {
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
        
        Arc::new(SkillRegistry::new(bash_skill, gateway_skill))
    }

    fn create_context(level: CapabilityLevel) -> SkillContext {
        SkillContext {
            thread_id: "test-thread".to_string(),
            session_id: "test-session".to_string(),
            executor_id: ExecutorId("test-executor".to_string()).0,
            capability_level: level,
            working_dirs: vec![],
        }
    }

    #[tokio::test]
    async fn test_bash_skill_basic() {
        println!("\n=== Test: Bash Skill Basic ===");
        
        let registry = create_test_registry().await;
        
        let request = SkillRequest {
            request_id: "test-001".to_string(),
            skill_name: "bash".to_string(),
            tool_name: "execute".to_string(),
            parameters: json!({
                "command": "pwd",
            }),
            context: create_context(CapabilityLevel::Agent),
        };
        
        let result = registry.execute_agent(request).await.unwrap();
        
        println!("Result: {:?}", result);
        assert!(result.success);
        
        let stdout = result.result
            .as_ref()
            .and_then(|r| r.get("stdout"))
            .and_then(|v| v.as_str())
            .unwrap_or("");
        
        assert!(!stdout.is_empty());
        println!("✅ Bash skill works! Output: {}", stdout.trim());
    }

    #[tokio::test]
    async fn test_os_interface_permission_denied() {
        println!("\n=== Test: OS Interface Permission Check ===");
        
        let registry = create_test_registry().await;
        
        let request = SkillRequest {
            request_id: "test-002".to_string(),
            skill_name: "os_interface".to_string(),
            tool_name: "list_sessions".to_string(),
            parameters: json!({}),
            context: create_context(CapabilityLevel::Agent),
        };
        
        let result = registry.execute_control(request, CapabilityLevel::Agent).await.unwrap();
        
        println!("Result: {:?}", result);
        assert!(!result.success);
        assert!(result.error.as_ref().unwrap().contains("Permission denied"));
        println!("✅ Permission check works! Agent cannot access OS Interface");
    }

    #[tokio::test]
    async fn test_scheduler_permission_denied() {
        println!("\n=== Test: Scheduler Permission Check ===");
        
        let registry = create_test_registry().await;
        
        let request = SkillRequest {
            request_id: "test-003".to_string(),
            skill_name: "scheduler".to_string(),
            tool_name: "list_threads".to_string(),
            parameters: json!({}),
            context: create_context(CapabilityLevel::Agent),
        };
        
        let result = registry.execute_control(request, CapabilityLevel::Agent).await.unwrap();
        
        println!("Result: {:?}", result);
        assert!(!result.success);
        assert!(result.error.as_ref().unwrap().contains("Permission denied"));
        println!("✅ Permission check works! Agent cannot access Scheduler");
    }

    #[tokio::test]
    async fn test_bash_read_test_file() {
        println!("\n=== Test: Read Test File ===");
        
        let registry = create_test_registry().await;
        let test_file = "/home/eziothean/ProClaw/test_data/os_interface_test/README.md";
        
        let request = SkillRequest {
            request_id: "test-004".to_string(),
            skill_name: "bash".to_string(),
            tool_name: "execute".to_string(),
            parameters: json!({
                "command": format!("cat {}", test_file),
            }),
            context: create_context(CapabilityLevel::Agent),
        };
        
        let result = registry.execute_agent(request).await.unwrap();
        
        println!("Result success: {}", result.success);
        assert!(result.success);
        
        let stdout = result.result
            .as_ref()
            .and_then(|r| r.get("stdout"))
            .and_then(|v| v.as_str())
            .unwrap_or("");
        
        println!("File content preview: {}...", &stdout[..stdout.len().min(100)]);
        assert!(stdout.contains("测试文档"));
        println!("✅ Successfully read test file!");
    }
}
