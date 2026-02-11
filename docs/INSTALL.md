# N01D Terminal Installation

```bash
git clone https://github.com/bad-antics/n01d-term
cd n01d-term
cargo build --release
sudo cp target/release/n01d-term /usr/local/bin/
```

## Dependencies
- Rust 1.70+
- GTK4 + libadwaita
- VTE4
