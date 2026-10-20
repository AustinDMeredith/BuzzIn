import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Spin up bot players to load-test BuzzIn.")
    parser.add_argument("--url", required=True, help="WebSocket URL, e.g. ws://localhost:8000/ws")
    parser.add_argument("--bots", type=int, default=25, help="Number of bot players to connect")
    args = parser.parse_args()

    # TODO: connect `args.bots` websocket clients to `args.url`, each joins with a
    # generated name, waits for questions, and buzzes after a random delay. Report
    # connections held and confirm each question had exactly one winner.
    print(f"Not yet implemented: would connect {args.bots} bots to {args.url}")


if __name__ == "__main__":
    main()
