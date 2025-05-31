from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime
from config import supabase_client
from typing import Optional
import jwt

router = APIRouter()

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
    title: Optional[str] = None
    description: Optional[str] = None
    event_name: Optional[str] = None
    event_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    location_capacity: Optional[int] = None
    location_latitude: Optional[float] = None
    location_longitude: Optional[float] = None
    forum_text: Optional[str] = None
    subject_id: Optional[int] = None


@router.post("/create_forum")
async def create_forum(data: ForumInput, user_id: int = Depends(get_current_user)):
    print("📦 Data Masuk:", data)
    now = datetime.utcnow().isoformat()

    try:
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

        new_forum = supabase_client.table("msforum").insert({
            "user_id": user_id,
            "created_at": now,
            "description": data.description,
            "title": data.title,
            "event_id": None,
            "subject_id": data.subject_id  # ADDED SUBJECT ID
        }).execute()
        post_id = new_forum.data[0]['post_id']

        # Convert time inputs to full datetime
        start_datetime = f"{data.event_date}T{data.start_date}:00Z" if data.start_date else None
        end_datetime = f"{data.event_date}T{data.end_date}:00Z" if data.end_date else None

        new_event = supabase_client.table("msevent").insert({
            "event_name": data.event_name,
            "event_date": data.event_date,
            "start_date": start_datetime,
            "end_date": end_datetime,
            "related_post_id": post_id,
            "created_at": now,
            "location_id": location_id,
            "created_by": user_id
        }).execute()
        event_id = new_event.data[0]['event_id']

        supabase_client.table("msforum").update({"event_id": event_id}).eq("post_id", post_id).execute()

        supabase_client.table("msisi_forum").insert({
            "forum_text": data.forum_text,
            "user_id": user_id,
            "post_id": post_id,
            "attachment": ""
        }).execute()

        return {"message": "Forum created successfully", "post_id": post_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")



@router.get("/list-forums")
async def get_forums(limit: int = Query(10), offset: int = Query(0)):
    try:
        response = supabase_client.table("msforum").select("""
        *,
        msuser(username, profile_picture),
        mssubject(subject_name),
        msevent!fk_forum_event(
        event_name,
        event_date,
        start_date,
        end_date,
        location:mslocation(location_name)
        )""").order("created_at", desc=True).range(offset, offset + limit - 1).execute()

        forum_data = response.data

        return {"data": forum_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
    
class ReplyInput(BaseModel):
    post_id: int
    reply_text: str
    parent_reply_id: Optional[int] = None
    attachment: Optional[str] = ""


@router.post("/reply_forum")
async def reply_forum(data: ReplyInput, user_id: int = Depends(get_current_user)):
    try:
        post_id = data.post_id

        forum_check = supabase_client.table("msisi_forum").select("post_id").eq("post_id", post_id).execute()
        
        if not forum_check.data:
            raise HTTPException(status_code=404, detail="Forum not found with the given post_id")

        parent_reply_id = data.parent_reply_id if data.parent_reply_id else None

        new_reply = supabase_client.table("msforum_reply").insert({
            "post_id": post_id,
            "user_id": user_id,
            "reply_text": data.reply_text,
            "parent_reply_id": parent_reply_id,
            "attachment": data.attachment or ""
        }).execute()

        return {"message": "Reply inserted", "reply_id": new_reply.data[0]["reply_id"]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.get("/forum_replies/{post_id}")
async def get_forum_replies(post_id: int):
    try:
        result = supabase_client.table("msforum_reply") \
            .select("reply_id, parent_reply_id, reply_text, created_at, user_id") \
            .eq("post_id", post_id) \
            .order("created_at", desc=False) \
            .execute()

        replies = result.data

        if not replies:
            return {"post_id": post_id, "replies": []}

        reply_map = {}

        for reply in replies:
            reply["children"] = []
            reply_map[reply["reply_id"]] = reply

        structured_replies = []

        for reply in replies:
            parent_id = reply.get("parent_reply_id")
            if parent_id:
                parent = reply_map.get(parent_id)
                if parent:
                    parent["children"].append(reply)
            else:
                structured_replies.append(reply)

        return {"post_id": post_id, "replies": structured_replies}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.get("/list-events")
async def list_events(limit: int = Query(10), offset: int = Query(0)):
    try:
        response = supabase_client.table("msevent").select("""
            event_name,
            event_date,
            start_date,
            end_date,
            mslocation(location_name, capacity)
        """).order("event_date", desc=True).range(offset, offset + limit - 1).execute()

        return {"events": response.data}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.delete("/delete-forum/{post_id}")
async def delete_forum(post_id: int, user_id: int = Depends(get_current_user)):
    try:
        forum = supabase_client.table("msforum").select("*").eq("post_id", post_id).maybe_single().execute()
        if not forum.data:
            raise HTTPException(status_code=404, detail="Forum tidak ditemukan")
        if forum.data['user_id'] != user_id:
            raise HTTPException(status_code=403, detail="Bukan pemilik forum")

        event_id = forum.data.get("event_id")  # <-- Dapatkan event_id dulu sebelum di-null-kan

        # Hapus semua reply
        supabase_client.table("msforum_reply").delete().eq("post_id", post_id).execute()

        # Hapus isi forum
        supabase_client.table("msisi_forum").delete().eq("post_id", post_id).execute()

        # Ambil location_id dulu sebelum hapus event
        location_id = None
        if event_id:
            event = supabase_client.table("msevent").select("location_id").eq("event_id", event_id).maybe_single().execute()
            location_id = event.data.get("location_id") if event.data else None

            # Hapus event
            supabase_client.table("msevent").delete().eq("event_id", event_id).execute()

        # Hapus forum terakhir (sekarang baru null-kan event_id, tapi udah telat buat kasus kamu, jadi langsung hapus)
        supabase_client.table("msforum").delete().eq("post_id", post_id).execute()

        # Hapus lokasi jika tidak dipakai oleh event lain
        if location_id:
            used_elsewhere = supabase_client.table("msevent").select("event_id").eq("location_id", location_id).execute()
            events_with_same_location = used_elsewhere.data or []  # ⬅️ Pastikan selalu list
            if len(events_with_same_location) == 0:
                supabase_client.table("mslocation").delete().eq("location_id", location_id).execute()


        return {"detail": "Forum berhasil dihapus"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

