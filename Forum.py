from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime
from config import supabase_client
from typing import Optional
import jwt

router = APIRouter()

# Token configuration
SECRET_KEY = "27aa6d1a-519c-4d88-b265-cda5808c0fe5"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        nim = payload.get("sub")
        if nim is None:
            raise credentials_exception
        return nim
    except jwt.PyJWTError:
        raise credentials_exception


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    nim = verify_token(token, credentials_exception)
    response = supabase_client.table("msuser").select("*").eq("nim", nim).maybe_single().execute()

    if not response.data:
        raise credentials_exception

    return response.data['user_id']


class ForumInput(BaseModel):
    title: str
    description: str
    forum_text: str
    subject_name: str
    event_name: str
    event_date: str  # Format: YYYY-MM-DD
    location_name: str
    location_address: str
    location_capacity: int
    location_latitude: float
    location_longitude: float


@router.post("/create_forum")
async def create_forum(data: ForumInput, user_id: int = Depends(get_current_user)):
    now = datetime.utcnow().isoformat()

    try:
        # === Step 1: Subject ===
        subject = supabase_client.table("mssubject").select("subject_id").eq("subject_name", data.subject_name).execute()
        if not subject.data:
            new_subject = supabase_client.table("mssubject").insert({"subject_name": data.subject_name}).execute()
            subject_id = new_subject.data[0]['subject_id']
        else:
            subject_id = subject.data[0]['subject_id']

        # === Step 2: Location ===
        location = supabase_client.table("mslocation").select("location_id") \
            .eq("location_name", data.location_name) \
            .eq("address", data.location_address) \
            .eq("capacity", data.location_capacity) \
            .eq("latitude", data.location_latitude) \
            .eq("longitude", data.location_longitude) \
            .execute()
        if not location.data:
            new_location = supabase_client.table("mslocation").insert({
                "location_name": data.location_name,
                "address": data.location_address,
                "capacity": data.location_capacity,
                "latitude": data.location_latitude,
                "longitude": data.location_longitude
            }).execute()
            location_id = new_location.data[0]['location_id']
        else:
            location_id = location.data[0]['location_id']

        # === Step 3: Buat Forum terlebih dahulu tanpa event_id ===
        new_forum = supabase_client.table("msforum").insert({
            "user_id": user_id,
            "created_at": now,
            "subject_id": subject_id,
            "description": data.description,
            "title": data.title,
            "event_id": None  # sementara None
        }).execute()
        post_id = new_forum.data[0]['post_id']

        # === Step 4: Buat Event dengan related_post_id = post_id ===
        new_event = supabase_client.table("msevent").insert({
            "event_name": data.event_name,
            "event_date": data.event_date,
            "related_post_id": post_id,
            "created_at": now,
            "location_id": location_id,
            "created_by": user_id
        }).execute()
        event_id = new_event.data[0]['event_id']

        # === Step 5: Update Forum dengan event_id ===
        supabase_client.table("msforum").update({"event_id": event_id}).eq("post_id", post_id).execute()

        # === Step 6: Insert forum_text ke msisi_forum ===
        supabase_client.table("msisi_forum").insert({
            "forum_text": data.forum_text,
            "user_id": user_id,
            "post_id": post_id,
            "attachment": ""  # bisa ditambahkan nanti kalau ada
        }).execute()

        return {"message": "Forum created successfully", "post_id": post_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.get("/list-forums")
async def get_forums(limit: int = Query(10), offset: int = Query(0)):
    try:
        # Pakai relasi fk_forum_event karena msforum.event_id → msevent.event_id
        response = supabase_client.table("msforum").select("""
            *,
            msuser(username, profile_picture),
            mssubject(subject_name),
            msevent!fk_forum_event(event_name, event_date)
        """).order("created_at", desc=True).range(offset, offset + limit - 1).execute()

        return {"data": response.data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")