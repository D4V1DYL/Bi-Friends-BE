from fastapi import APIRouter, HTTPException, Depends, status, Query, UploadFile, File, Form
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime
from config import supabase_client
from typing import Optional
import jwt
import cloudinary
import cloudinary.uploader

router = APIRouter()

SECRET_KEY = "27aa6d1a-519c-4d88-b265-cda5808c0fe5"
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

cloudinary.config(
    cloud_name = "dr3k8ac6l", 
    api_key = "812158745664199",  
    api_secret="IbFLS26_PFtihZHnm_QkLWTy9ww"
)

def get_current_user_id(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("user_id")
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak valid",
        )

@router.get("/profile-page/{user_id}")
async def get_user_profile(user_id: int): 
    try:
        response = supabase_client.table("msuser").select("""
            user_id,
            username,
            profile_picture,
            gender
        """).eq("user_id", user_id).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")

        return {"data": response.data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.put("/profile-page/update/{user_id}")
async def update_user_profile(
    user_id: int,
    username: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    profile_picture: Optional[UploadFile] = File(None),
    current_user_id: int = Depends(get_current_user_id)
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Tidak diizinkan mengedit profil orang lain.")

    update_data = {}

    if username:
        update_data["username"] = username
    if gender:
        update_data["gender"] = gender
    if profile_picture:
        upload_result = cloudinary.uploader.upload(profile_picture.file)
        update_data["profile_picture"] = upload_result.get("secure_url")

    if not update_data:
        raise HTTPException(status_code=400, detail="Tidak ada data yang diubah")

    try:
        response = supabase_client.table("msuser").update(update_data).eq("user_id", user_id).execute()
        print("📦 Supabase Response:", response)
        
        if response.data is None or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Gagal mengupdate profil")

        user = response.data[0]
        filtered_user = {
            "nim": user["nim"].strip(),
            "username": user["username"],
            "gender": user["gender"],
            "profile_picture": user["profile_picture"]
        }
        return {"message": "Profil berhasil diperbarui", "data": filtered_user}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan: {str(e)}")
    
@router.post("/add-friend/{target_user_id}")
async def send_friend_request(
    target_user_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    if current_user_id == target_user_id:
        raise HTTPException(status_code=400, detail="Tidak bisa menambahkan diri sendiri sebagai teman.")

    # Cek apakah sudah ada permintaan yang sama
    existing = supabase_client.table("msstatus_request").select("*")\
        .eq("sender_id", current_user_id).eq("receiver_id", target_user_id).maybe_single().execute()

    if existing and existing.data:
        raise HTTPException(status_code=400, detail="Permintaan pertemanan sudah dikirim.")

    # Masukkan permintaan baru
    result = supabase_client.table("msstatus_request").insert({
        "sender_id": current_user_id,
        "receiver_id": target_user_id,
        "status": "pending",
        "request_date": datetime.utcnow().isoformat()
    }).execute()

    return {"message": "Permintaan pertemanan telah dikirim."}

@router.get("/friends")
async def get_friend_list(current_user_id: int = Depends(get_current_user_id)):
    response = supabase_client.table("msfriend_list").select("""
        *,
        msuser!msfriend_list_user_id_2_fkey(username, profile_picture)
    """).eq("user_id_1", current_user_id).order("added_at", desc=True).execute()

    if not response.data:
        return {"message": "Tidak ada teman ditemukan.", "friends": []}
    # Format hasil

    friends = [
        {
            "user_id": friend["user_id_2"],
            "username": friend["msuser"]["username"],
            "profile_picture": friend["msuser"]["profile_picture"],
            "added_at": friend["added_at"]
        }
        for friend in response.data
    ]

    return {"friends": friends}


@router.post("/accept-friend-request/{request_id}")
async def accept_friend_request(request_id: int, current_user_id: int = Depends(get_current_user_id)):
    # Ambil permintaan
    request_data = supabase_client.table("msstatus_request").select("*")\
        .eq("request_id", request_id).maybe_single().execute()

    # ❗Tambahkan pengecekan if request_data is None
    if request_data is None or not request_data.data or request_data.data["receiver_id"] != current_user_id:
        raise HTTPException(status_code=404, detail="Permintaan tidak ditemukan atau tidak sesuai.")

    sender_id = request_data.data["sender_id"]

    # Tambahkan ke daftar teman dua arah
    supabase_client.table("msfriend_list").insert([
        {"user_id_1": current_user_id, "user_id_2": sender_id},
        {"user_id_1": sender_id, "user_id_2": current_user_id}
    ]).execute()

    # Perbarui status permintaan
    supabase_client.table("msstatus_request").update({"status": "accepted"}).eq("request_id", request_id).execute()

    return {"message": "Permintaan pertemanan diterima."}

@router.get("/friend-requests/incoming")
async def list_incoming_requests(current_user_id: int = Depends(get_current_user_id)):
    result = supabase_client.table("msstatus_request").select("request_id, sender_id, status, request_date")\
        .eq("receiver_id", current_user_id)\
        .eq("status", "pending")\
        .order("request_date", desc=True).execute()
    
    return {"requests": result.data}
