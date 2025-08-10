# app/main.py
# FastAPI routes

from fastapi import FastAPI, Request, HTTPException, Depends
from datetime import datetime, timedelta
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
import os

from app.arxiv import fetch_arxiv_papers
from app.db import init_db, save_papers, engine
from app.models import ArxivPaper, User, Bookmark, Vote

# --- load env ---
load_dotenv()
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-change-me")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")

templates = Jinja2Templates(directory="templates")
init_db()

# --- Google OAuth setup ---
oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


# --- who am I (for hydration) ---
@app.get("/api/me")
def me(request: Request):
    u = request.session.get("user")
    return {"logged_in": bool(u), "user": u or None}


def current_user(request: Request):
    return request.session.get("user")


@app.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")


# -- after Google callback, upsert the user --
@app.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo", {})
    u = {
        "sub": userinfo["sub"],
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }
    request.session["user"] = u
    # upsert user
    with Session(engine) as s:
        dbu = s.get(User, u["sub"])
        if dbu is None:
            s.add(User(**u))
        else:
            dbu.email, dbu.name, dbu.picture = u["email"], u["name"], u["picture"]
        s.commit()
    return RedirectResponse(url="/?login_success=1")


def require_user(request: Request) -> str:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user["sub"]


# --- Bookmarks ---
@app.post("/api/papers/{paper_id}/bookmark")
def bookmark_paper(paper_id: int, request: Request):
    sub = require_user(request)
    with Session(engine) as s:
        if s.get(ArxivPaper, paper_id) is None:
            raise HTTPException(404, "Paper not found")
        exists = s.exec(
            select(Bookmark).where(
                Bookmark.user_sub == sub, Bookmark.paper_id == paper_id
            )
        ).first()
        if not exists:
            s.add(Bookmark(user_sub=sub, paper_id=paper_id))
            s.commit()
        return {"bookmarked": True}


@app.get("/bookmarks", response_class=HTMLResponse)
def my_bookmarks(request: Request, user_sub: str = Depends(require_user)):
    with Session(engine) as s:
        papers = s.exec(
            select(ArxivPaper)
            .options(selectinload(ArxivPaper.categories))
            .join(Bookmark, Bookmark.paper_id == ArxivPaper.id)
            .where(Bookmark.user_sub == user_sub)  # <-- use the string directly
            .order_by(ArxivPaper.published.desc())
        ).all()

    return templates.TemplateResponse(
        "papers.html",
        {
            "request": request,
            "papers": papers,
            "user": request.session.get("user"),  # pass full session user to template
            "active_view": "bookmarks",
            "GA_MEASUREMENT_ID": GA_MEASUREMENT_ID,
        },
    )


@app.delete("/api/papers/{paper_id}/bookmark")
def unbookmark_paper(paper_id: int, request: Request):
    sub = require_user(request)
    with Session(engine) as s:
        bm = s.exec(
            select(Bookmark).where(
                Bookmark.user_sub == sub, Bookmark.paper_id == paper_id
            )
        ).first()
        if bm:
            s.delete(bm)
            s.commit()
        return {"bookmarked": False}


@app.get("/api/papers/{paper_id}/bookmarks")
def bookmark_count(paper_id: int):
    with Session(engine) as s:
        cnt = s.exec(select(Bookmark).where(Bookmark.paper_id == paper_id)).all()
        return {"count": len(cnt)}


# -------- Votes --------
@app.post("/api/papers/{paper_id}/vote")
def vote_paper(paper_id: int, request: Request, payload: dict):
    """
    payload = {"value": -1|0|1}   0 clears vote
    """
    sub = require_user(request)
    val = int(payload.get("value", 0))
    if val not in (-1, 0, 1):
        raise HTTPException(400, "value must be -1, 0, or 1")
    with Session(engine) as s:
        if s.get(ArxivPaper, paper_id) is None:
            raise HTTPException(404, "Paper not found")
        v = s.exec(
            select(Vote).where(Vote.user_sub == sub, Vote.paper_id == paper_id)
        ).first()
        if v is None:
            v = Vote(user_sub=sub, paper_id=paper_id, value=val)
            s.add(v)
        else:
            v.value = val
        s.commit()
        # return new score
        total = s.exec(select(Vote).where(Vote.paper_id == paper_id)).all()
        score = sum(x.value for x in total)
        return {"score": score, "your_vote": val}


@app.get("/api/papers/{paper_id}/score")
def vote_score(paper_id: int):
    # visible to everyone (even logged-out)
    with Session(engine) as s:
        total = s.exec(select(Vote).where(Vote.paper_id == paper_id)).all()
        return {"score": sum(x.value for x in total)}


@app.get("/arxiv/daily")
async def get_daily_arxiv():
    today = datetime.utcnow()
    yesterday = today - timedelta(days=3)
    start = yesterday.strftime("%Y%m%d0000")
    end = today.strftime("%Y%m%d2359")

    parsed = await fetch_arxiv_papers(start, end)
    save_papers(parsed)
    return {"stored": len(parsed)}


@app.get("/arxiv/show")
def show_papers():
    with Session(engine) as session:
        stmt = select(ArxivPaper).order_by(ArxivPaper.published.desc()).limit(10)
        papers = session.exec(stmt).all()
        return papers


@app.get("/", response_class=HTMLResponse)
def html_view(request: Request):
    with Session(engine) as session:
        stmt = select(ArxivPaper).order_by(ArxivPaper.published.desc()).limit(50)
        papers = session.exec(stmt).all()
        user = request.session.get("user")
        return templates.TemplateResponse(
            "papers.html",
            {
                "request": request,
                "papers": papers,
                "user": request.session.get("user"),
                "active_view": "all",
                "GA_MEASUREMENT_ID": GA_MEASUREMENT_ID,
            },
        )
