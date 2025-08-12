# word_count.py
def count_words(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    return sum(1 for tok in text.split() if tok.strip())


if __name__ == "__main__":
    file_path = ".test_research_paper.txt"
    count = count_words(file_path)
    print(f"Word count: {count}")
