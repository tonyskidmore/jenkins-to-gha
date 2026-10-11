# Reproduces captures/parts-2-4.txt: the three commands from examples/000/README.md Parts 2 to 4 (local, free).
# Run from the repo root with Docker running and the harness images built (uv run j2gha docker build).
step 'uv run j2gha analyze 000'
step 'uv run j2gha convert 000'
step 'uv run j2gha validate 000'
