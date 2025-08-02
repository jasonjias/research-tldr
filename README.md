# 🧠 Research TLDR

A FastAPI backend for fetching and eventually summarizing the latest research papers from [arXiv.org](https://arxiv.org/). This project is the foundation for building a platform that provides clean, accessible summaries of academic research.

---

## 🚀 Features

- ✅ Query arXiv API for papers submitted within a given date range  
- ✅ Built with FastAPI (async, lightweight, Pythonic)  
- ✅ Designed for future integration with LLM summarization  

---

## 📂 Project Structure

    research-tldr/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py         ← FastAPI app and routes
    │   └── arxiv.py        ← ArXiv fetch logic
    ├── .venv/              ← Python virtual environment
    ├── requirements.txt    ← Project dependencies
    └── README.md           ← You're here!

---

## 🛠️ Getting Started

**1. Clone the repo**

    git clone https://github.com/your-username/research-tldr.git
    cd research-tldr

**2. Set up virtual environment**

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

**3. Run the dev server**

    uvicorn app.main:app --reload

**4. Test the API**

Open in browser: [http://127.0.0.1:8000/arxiv/daily](http://127.0.0.1:8000/arxiv/daily)

---

## 🧪 Example Endpoint

**GET /arxiv/daily**  
Fetches papers submitted in the last 2 days using the `submittedDate` range from arXiv’s API. (Currently returns raw XML.)

---

## 🧱 Dependencies

- FastAPI  
- Uvicorn  
- httpx  
- pydantic  

(Full list available in `requirements.txt`)

---

## 🧩 Coming Soon

- [ ] LLM-powered summaries (GPT or Claude)  
- [ ] Tagging papers by research area  
- [ ] Daily digest generation  
- [ ] Simple dashboard UI  

---

## 📜 License

MIT — free to use, contribute, and modify.

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss.
