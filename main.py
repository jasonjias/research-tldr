# app/main.py
# FastAPI routes

from fastapi import FastAPI, Request
from datetime import datetime, timedelta
from sqlmodel import Session, select
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
import os

from app.arxiv import fetch_arxiv_papers
from app.db import init_db, save_papers, engine
from app.models import ArxivPaper

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


def current_user(request: Request):
    return request.session.get("user")


@app.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    # store minimal details in session
    request.session["user"] = {
        "sub": userinfo["sub"],
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }
    # return RedirectResponse(url="/")
    return RedirectResponse(url="/?login_success=1")


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")


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
                "user": user,
                "GA_MEASUREMENT_ID": GA_MEASUREMENT_ID,
            },
        )
