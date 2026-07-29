import logging

from graph import build_graph
from learning import record_accepted, record_rejected

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main():
    app, learned_qa, failure_lessons = build_graph()

    print("Memory-graph demo (user_input -> generate_answer). Type 'quit' to exit.\n")
    while True:
        query = input("Your question: ").strip()
        if query.lower() in {"quit", "exit"}:
            break
        if not query:
            continue

        result = app.invoke({"user_input": query})
        answer = result.get("answer", "")
        print(f"\nAnswer: {answer}\n")

        verdict = input("Accept this answer? [y/n/skip]: ").strip().lower()
        if verdict == "y":
            stored = record_accepted(query, answer, learned_qa)
            print("Lesson stored in learned_qa.\n" if stored else "Nothing new to store.\n")
        elif verdict == "n":
            feedback = input("What was wrong with it? ").strip()
            stored = record_rejected(query, answer, feedback, failure_lessons)
            print("Lesson stored in failure_lessons.\n" if stored else "Nothing new to store.\n")
        else:
            print()


if __name__ == "__main__":
    main()
