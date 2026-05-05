# Local CLI Operating Model

Initialize the local workspace:

```bash
cgg init
```

Capture a command:

```bash
cgg run --profile developer --budget 2000 -- make test
```

Pack a file or directory:

```bash
cgg pack --path ./logs --budget 3000
```

Project an existing raw artifact:

```bash
cgg project --artifact ./.cgg/artifacts/raw/example.txt --profile developer
```

Inspect a packet:

```bash
cgg inspect --packet ./.cgg/packets/example.packet.json
```

Generated local outputs:

- `.cgg/artifacts/raw/`
- `.cgg/artifacts/redacted/`
- `.cgg/manifests/`
- `.cgg/packets/`
- `.cgg/receipts/`
- `.cgg/ledger.jsonl`
