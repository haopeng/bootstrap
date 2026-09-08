import sys


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "demo"
    if cmd == "demo":
        from ventures.demo import run_all

        run_all()
        return 0
    if cmd == "serve":
        import uvicorn

        port = int(argv[2]) if len(argv) > 2 else 8000
        uvicorn.run("ventures.server:app", host="0.0.0.0", port=port, reload=False)
        return 0
    print("usage: python -m ventures [demo|serve [port]]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
