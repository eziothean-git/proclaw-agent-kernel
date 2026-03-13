use std::io::Result;

fn main() -> Result<()> {
    // Compile protobuf files
    // Output goes to OUT_DIR by default (target/debug/build/.../out/)
    tonic_build::configure()
        .build_server(true)
        .build_client(true)
        .compile(
            &[
                "proto/block_composer.proto",
                "proto/agent_kernel.proto",
                "proto/prime_personality.proto",
            ],
            &["proto"],
        )?;

    Ok(())
}
