from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import supabase ,verify_connection


from routes import api_router
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up...")
    if verify_connection():
      print("supabase verified")
    else:
      print("supabase not verified")     
    yield
    print("Shutting down...")
app = FastAPI(lifespan=lifespan)#this is because i want to start the checker the moment i boot the server


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
def health_check():
    return {"status": "InboxIQ backend is running"}