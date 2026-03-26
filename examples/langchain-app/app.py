from evalflow import get_prompt


def main() -> None:
    prompt = get_prompt("assistant")
    print("Reply: The assistant answers using the production prompt body.")
    print(prompt.splitlines()[0])


if __name__ == "__main__":
    main()
