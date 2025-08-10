# app/main.py
# FastAPI routes

from fastapi import FastAPI, Request, HTTPException, Depends
from datetime import datetime, timedelta
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
import os

from app.arxiv import fetch_arxiv_papers
from app.db import init_db, save_papers, engine
from app.models import ArxivPaper, User, Bookmark, Vote, UserSettings

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


def no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    resp = RedirectResponse(url="/")
    resp.headers["Cache-Control"] = "no-store"
    return resp


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


# def sub = require_user_sub(request)request: Request) -> str:
#     user = request.session.get("user")
#     if not user:
#         raise HTTPException(status_code=401, detail="Login required")
#     return user["sub"]


def require_user_obj(request: Request) -> dict:
    u = request.session.get("user")
    if not u:
        raise HTTPException(status_code=401, detail="Login required")
    return u


def require_user_sub(request: Request) -> str:
    return require_user_obj(request)["sub"]


# --- Bookmarks ---
@app.get("/bookmarks", response_class=HTMLResponse)
def my_bookmarks(request: Request, user_sub: str = Depends(require_user_sub)):
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


# ---- Bookmarks ----
@app.get("/api/papers/{paper_id}/bookmarks")
def get_bookmark_count(paper_id: int, request: Request):
    user = request.session.get("user")
    if not user:
        # not logged in → hide count
        return {"count": 0}

    from sqlalchemy import func

    with Session(engine) as session:
        count = session.exec(
            select(func.count())
            .select_from(Bookmark)
            .where(Bookmark.paper_id == paper_id)
        ).one()
        return {"count": count}


@app.post("/api/papers/{paper_id}/bookmark")
def add_bookmark(paper_id: int, request: Request):
    sub = require_user_sub(request)
    with Session(engine) as session:
        # ensure paper exists
        ok = session.exec(
            select(ArxivPaper.id).where(ArxivPaper.id == paper_id)
        ).first()
        if not ok:
            raise HTTPException(404, "Paper not found")

        # ensure user exists
        u = session.get(User, sub)
        if not u:
            u = User(
                sub=sub,
                name=user.get("name"),
                email=user.get("email"),
                picture=user.get("picture"),
            )
            session.add(u)
            session.commit()

        # insert if not exists
        exists = session.exec(
            select(Bookmark.id).where(
                Bookmark.user_sub == sub, Bookmark.paper_id == paper_id
            )
        ).first()
        if not exists:
            session.add(Bookmark(user_sub=sub, paper_id=paper_id))
            session.commit()
        return {"ok": True}


@app.delete("/api/papers/{paper_id}/bookmark")
def remove_bookmark(paper_id: int, request: Request):
    sub = require_user_sub(request)
    with Session(engine) as session:
        row = session.exec(
            select(Bookmark).where(
                Bookmark.user_sub == sub, Bookmark.paper_id == paper_id
            )
        ).first()
        if row:
            session.delete(row)
            session.commit()
        return {"ok": True}


# ---- Scores / votes ----
@app.get("/api/papers/{paper_id}/score")
def get_paper_score(paper_id: int):
    with Session(engine) as session:
        total = session.exec(select(Vote.value).where(Vote.paper_id == paper_id)).all()
        score = sum(total) if total else 0
        return {"score": score}


@app.post("/api/papers/{paper_id}/vote")
def vote_paper(paper_id: int, body: dict, request: Request):
    sub = require_user_sub(request)  # get logged-in user's sub
    value = int(body.get("value", 0))  # read from request body

    if value not in (-1, 0, 1):
        raise HTTPException(400, "value must be -1 or 1")

    with Session(engine) as session:
        # ensure paper exists
        ok = session.exec(
            select(ArxivPaper.id).where(ArxivPaper.id == paper_id)
        ).first()
        if not ok:
            raise HTTPException(404, "Paper not found")

        # ensure user exists
        u = session.get(User, sub)
        if not u:
            # minimal upsert in case user row not created yet
            u = User(
                sub=sub,
                name=None,  # You can fetch from session if needed
                email=None,
                picture=None,
            )
            session.add(u)
            session.commit()

        # upsert vote (unique on user_sub, paper_id)
        existing = session.exec(
            select(Vote).where(Vote.user_sub == sub, Vote.paper_id == paper_id)
        ).first()
        if existing:
            existing.value = value
        else:
            session.add(Vote(user_sub=sub, paper_id=paper_id, value=value))
        session.commit()

        # return new score
        total = session.exec(select(Vote.value).where(Vote.paper_id == paper_id)).all()
        return {"score": sum(total) if total else 0}



@app.get("/api/user/settings")
def get_user_settings(request: Request):
    sub = require_user_sub(request)
    with Session(engine) as session:
        s = session.get(UserSettings, sub)
        if not s:
            return {"user_sub": sub, "prefs": {}, "updated_at": None}
        return {"user_sub": s.user_sub, "prefs": s.prefs, "updated_at": s.updated_at}


@app.post("/api/user/settings")
def upsert_user_settings(body: dict, request: Request):
    sub = require_user_sub(request)
    prefs = body.get("prefs") or {}
    if not isinstance(prefs, dict):
        raise HTTPException(400, "prefs must be an object")

    with Session(engine) as session:
        s = session.get(UserSettings, sub)
        if s:
            s.prefs = prefs
            s.updated_at = datetime.utcnow()
        else:
            s = UserSettings(user_sub=sub, prefs=prefs)
            session.add(s)
        session.commit()
        return {"ok": True}


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
