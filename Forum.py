from fastapi import APIRouter, HTTPException, Depends, status, Query, UploadFile, File, Form
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime
from config import supabase_client
from typing import Optional
import jwt
import pytz
import cloudinary
import cloudinary.uploader


router = APIRouter()

SECRET_KEY = "27aa6d1a-519c-4d88-b265-cda5808c0fe5"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

cloudinary.config(
    cloud_name = "dr3k8ac6l", 
    api_key = "812158745664199",  
    api_secret="IbFLS26_PFtihZHnm_QkLWTy9ww"
)


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

def to_dict_wo_none(d):
    return {k: v for k, v in d.items() if v is not None}

@router.post("/create_forum")
async def create_forum(
    title: str = Form(...),
    description: str = Form(...),
    forum_text: Optional[str] = Form(" "),
    subject_id: Optional[int] = Form(None),
    event_name: Optional[str] = Form(None),
    event_date: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    location_name: Optional[str] = Form(None),
    location_address: Optional[str] = Form(None),
    location_capacity: Optional[int] = Form(None),
    location_latitude: Optional[float] = Form(None),
    location_longitude: Optional[float] = Form(None),
    attachment: Optional[UploadFile] = File(None),
    user_id: int = Depends(get_current_user)
):
    print("📦 Data Masuk:", {
        "title": title,
        "description": description,
        "forum_text": forum_text,
        "subject_id": subject_id,
        "event_name": event_name,
        "event_date": event_date,
        "start_date": start_date,
        "end_date": end_date,
        "location_name": location_name,
        "location_address": location_address,
        "location_capacity": location_capacity,
        "location_latitude": location_latitude,
        "location_longitude": location_longitude
    })
    now = datetime.utcnow().isoformat()

    try:
        # Validate required fields
        if not title or not description:
            raise HTTPException(status_code=400, detail="Title and description are required")

        # Handle attachment upload if provided
        attachment_url = None
        if attachment:
            try:
                upload_result = cloudinary.uploader.upload(attachment.file)
                attachment_url = upload_result.get("secure_url")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to upload attachment: {str(e)}")

        # Handle location
        location_id = None
        if location_name and location_capacity and location_latitude and location_longitude:
            location_lookup = {
                "location_name": location_name,
                "address": location_address,
                "capacity": location_capacity,
                "latitude": location_latitude,
                "longitude": location_longitude
            }
            location = supabase_client.table("mslocation").select("location_id") \
                .eq("location_name", location_name) \
                .eq("address", location_address) \
                .eq("capacity", location_capacity) \
                .eq("latitude", location_latitude) \
                .eq("longitude", location_longitude) \
                .execute()

            if not location.data:
                new_location = supabase_client.table("mslocation").insert(
                    to_dict_wo_none(location_lookup)
                ).execute()
                location_id = new_location.data[0]['location_id']
            else:
                location_id = location.data[0]['location_id']

        # Insert forum
        forum_data = {
            "user_id": user_id,
            "created_at": now,
            "description": description,
            "title": title,
            "event_id": None,
            "subject_id": subject_id
        }
        new_forum = supabase_client.table("msforum").insert(
            to_dict_wo_none(forum_data)
        ).execute()
        post_id = new_forum.data[0]['post_id']

        # Handle event if provided
        event_id = None
        if event_name and event_date:
            def wib_to_utc(date_str, time_str):
                local = pytz.timezone('Asia/Jakarta')
                dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                local_dt = local.localize(dt)
                utc_dt = local_dt.astimezone(pytz.utc)
                return utc_dt.isoformat().replace('+00:00', 'Z')
            
            start_datetime = wib_to_utc(event_date, start_date) if start_date else None
            end_datetime = wib_to_utc(event_date, end_date) if end_date else None

            event_data = {
                "event_name": event_name,
                "event_date": event_date,
                "start_date": start_datetime,
                "end_date": end_datetime,
                "related_post_id": post_id,
                "created_at": now,
                "location_id": location_id,
                "created_by": user_id
            }
            new_event = supabase_client.table("msevent").insert(
                to_dict_wo_none(event_data)
            ).execute()
            event_id = new_event.data[0]['event_id']

            # Update forum with event_id
            if event_id:
                supabase_client.table("msforum").update({"event_id": event_id}).eq("post_id", post_id).execute()

        # Insert forum content if provided
        if forum_text:
            msisi_forum_data = {
                "forum_text": forum_text,
                "user_id": user_id,
                "post_id": post_id,
                "attachment": attachment_url or ""
            }
            supabase_client.table("msisi_forum").insert(
                to_dict_wo_none(msisi_forum_data)
            ).execute()

        return {"message": "Forum created successfully", "post_id": post_id}

    except HTTPException as he:
        raise he
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
        ),
        msisi_forum(forum_text, attachment)
        """).order("created_at", desc=True).range(offset, offset + limit - 1).execute()

        forum_data = response.data

        return {"data": forum_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.get("/forum/{post_id}")
async def get_forum(post_id: int):
    try:
        # Validate post_id
        if not post_id or post_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid post_id")

        response = supabase_client.table("msforum").select("""
        *,
        msuser(username, profile_picture),
        mssubject(subject_name),
        msevent!fk_forum_event(
            event_name,
            event_date,
            start_date,
            end_date,
            location:mslocation(location_name, address, capacity, latitude, longitude)
        ),
        msisi_forum(forum_text, attachment)
        """).eq("post_id", post_id).maybe_single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Forum tidak ditemukan")

        # Clean up None values in the response
        def clean_none_values(data):
            if isinstance(data, dict):
                return {k: clean_none_values(v) for k, v in data.items() if v is not None}
            elif isinstance(data, list):
                return [clean_none_values(item) for item in data if item is not None]
            return data

        cleaned_data = clean_none_values(response.data)
        return {"data": cleaned_data}

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
    
class ReplyInput(BaseModel):
    # No longer needed as we're using Form and File directly
    pass

@router.post("/reply_forum")
async def reply_forum(
    post_id: int = Form(...),
    reply_text: str = Form(...),
    parent_reply_id: Optional[int] = Form(None),
    attachment: Optional[UploadFile] = File(None),
    user_id: int = Depends(get_current_user)
):
    try:
        # Validate required fields (post_id and reply_text are already validated by Form(...))

        forum_check = supabase_client.table("msforum").select("post_id").eq("post_id", post_id).execute()
        
        if not forum_check.data:
            raise HTTPException(status_code=404, detail="Forum not found with the given post_id")

        # Determine the actual parent_reply_id to insert (use None for top-level replies, assuming 0 indicates top-level)
        parent_id_to_insert = parent_reply_id if parent_reply_id is not None and parent_reply_id != 0 else None

        # Handle attachment upload if provided
        attachment_url = None
        if attachment:
            try:
                upload_result = cloudinary.uploader.upload(attachment.file)
                attachment_url = upload_result.get("secure_url")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to upload attachment: {str(e)}")

        new_reply = supabase_client.table("msforum_reply").insert({
            "post_id": post_id,
            "user_id": user_id,
            "reply_text": reply_text,
            "parent_reply_id": parent_id_to_insert,
            "attachment": attachment_url or ""
        }).execute()

        return {"message": "Reply inserted", "reply_id": new_reply.data[0]["reply_id"]}

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.get("/forum_replies/{post_id}")
async def get_forum_replies(post_id: int):
    try:
        result = supabase_client.table("msforum_reply") \
            .select("""
                reply_id, 
                parent_reply_id, 
                reply_text, 
                created_at, 
                user_id,
                attachment,
                msuser(username, profile_picture)
            """) \
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
            related_post_id,
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

