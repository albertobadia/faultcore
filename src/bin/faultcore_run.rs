use clap::{Parser, ValueEnum};
use std::collections::HashMap;
use std::os::unix::process::CommandExt;
use std::process::{Command, Stdio};

#[derive(Parser, Debug)]
#[command(name = "faultcore-run")]
#[command(about = "Run Python apps with network fault simulation at OS level")]
struct Args {
    #[arg(short, long, default_value = "none")]
    profile: NetworkProfile,

    #[arg(short, long)]
    latency: Option<u64>,

    #[arg(short, long)]
    packet_loss: Option<f64>,

    #[arg(short, long)]
    bandwidth: Option<u64>,

    #[arg(short, long)]
    jitter: Option<u64>,

    #[arg(trailing_var_arg = true)]
    command: Vec<String>,
}

#[derive(Debug, Clone, ValueEnum)]
enum NetworkProfile {
    None,
    #[clap(name = "3g")]
    ThreeG,
    #[clap(name = "4g-lte")]
    FourGLte,
    #[clap(name = "edge")]
    Edge,
    #[clap(name = "satellite")]
    Satellite,
    #[clap(name = "unstable")]
    Unstable,
    #[clap(name = "offline")]
    Offline,
}

impl NetworkProfile {
    fn to_params(&self) -> (u64, f64, u64, u64) {
        match self {
            NetworkProfile::None => (0, 0.0, 0, 0),
            NetworkProfile::ThreeG => (300, 1.0, 1500, 50),
            NetworkProfile::FourGLte => (50, 0.1, 10000, 10),
            NetworkProfile::Edge => (500, 2.0, 240, 100),
            NetworkProfile::Satellite => (600, 0.5, 2000, 20),
            NetworkProfile::Unstable => (100, 15.0, 1000, 200),
            NetworkProfile::Offline => (0, 100.0, 0, 0),
        }
    }
}

fn build_env_vars(profile: &NetworkProfile, args: &Args) -> HashMap<String, String> {
    let (latency, packet_loss, bandwidth, jitter) = if args.latency.is_some()
        || args.packet_loss.is_some()
        || args.bandwidth.is_some()
        || args.jitter.is_some()
    {
        (
            args.latency.unwrap_or(0),
            args.packet_loss.unwrap_or(0.0),
            args.bandwidth.unwrap_or(0),
            args.jitter.unwrap_or(0),
        )
    } else {
        profile.to_params()
    };

    let mut env = HashMap::new();
    if latency > 0 {
        env.insert("FAULTCORE_LATENCY_MS".into(), latency.to_string());
    }
    if packet_loss > 0.0 {
        env.insert("FAULTCORE_PACKET_LOSS".into(), packet_loss.to_string());
    }
    if bandwidth > 0 {
        env.insert("FAULTCORE_BANDWIDTH_KBPS".into(), bandwidth.to_string());
    }
    if jitter > 0 {
        env.insert("FAULTCORE_JITTER_MS".into(), jitter.to_string());
    }
    env
}

fn preload_lib_name() -> Option<&'static str> {
    if cfg!(target_os = "linux") {
        Some("libfaultcore_preload.so")
    } else if cfg!(target_os = "macos") {
        Some("libfaultcore_preload.dylib")
    } else {
        None
    }
}

fn main() -> std::io::Result<()> {
    let args = Args::parse();

    if args.command.is_empty() {
        eprintln!("Error: No command provided. Use --help for usage information.");
        std::process::exit(1);
    }

    let mut cmd = Command::new("uv");
    cmd.arg("run");
    cmd.args(&args.command);
    cmd.stdin(Stdio::inherit());
    cmd.stdout(Stdio::inherit());
    cmd.stderr(Stdio::inherit());

    let env_vars = build_env_vars(&args.profile, &args);

    if !env_vars.is_empty() {
        for (key, value) in &env_vars {
            cmd.env(key, value);
        }
        println!(
            "[faultcore-run] Applying network profile: {:?}",
            args.profile
        );
        println!("[faultcore-run] Environment variables set:");
        for (key, value) in &env_vars {
            println!("  {}={}", key, value);
        }

        if let Some(preload_lib) = preload_lib_name() {
            let current_path = std::env::current_dir()
                .unwrap_or_default()
                .join("target")
                .join("release")
                .join(preload_lib);

            if current_path.exists() {
                let preload_path = current_path.to_string_lossy();
                if cfg!(target_os = "linux") {
                    cmd.env("LD_PRELOAD", preload_path.as_ref());
                } else if cfg!(target_os = "macos") {
                    cmd.env("DYLD_INSERT_LIBRARIES", preload_path.as_ref());
                    let library_path = std::env::current_dir()
                        .unwrap_or_default()
                        .join("target")
                        .join("release");
                    cmd.env("DYLD_LIBRARY_PATH", library_path);
                }
                println!("[faultcore-run] Preload library: {}", preload_path);
            } else {
                println!(
                    "[faultcore-run] Warning: Preload library not found at {}. Network simulation requires building the shared library.",
                    current_path.display()
                );
                println!(
                    "[faultcore-run] Run: gcc -shared -fPIC -o target/release/libfaultcore_preload.dylib faultcore_preload/src/preload.c -ldl -lpthread"
                );
            }
        }
    }

    let error = cmd.exec();
    Err(error)
}
