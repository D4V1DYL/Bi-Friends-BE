from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Depends,HTTPException,Query
import jwt
from config import supabase_client
from datetime import datetime
import cloudinary.uploader
from typing import Dict, Optional,Any
from Profile import get_current_user_id

router = APIRouter()

# JWT settings (sesuaikan dengan auth.py)
SECRET_KEY = "27aa6d1a-519c-4d88-b265-cda5808c0fe5"
ALGORITHM = "HS256"

class ConnectionManager:
    def __init__(self):
        # map user_id ke koneksi WebSocket
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        self.active_connections.pop(user_id, None)

    async def send_personal_message(self, message: dict, user_id: int):
        websocket = self.active_connections.get(user_id)
        if websocket:
            await websocket.send_json(message)

manager = ConnectionManager()

async def get_current_user_id_ws(token: str) -> Optional[int]:
    """
    Dekode JWT token dari query parameter
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("user_id")
    except jwt.PyJWTError:
        return None
    
@router.get("/history/{with_user_id}")
async def get_chat_history(
    with_user_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    Ambil seluruh pesan antara current_user_id dan with_user_id,
    diurutkan berdasarkan created_at (ascending).
    """
    # Build OR‐filter: A→B atau B→A
    or_filter = (
        f"and(sender_id.eq.{current_user_id},receiver_id.eq.{with_user_id}),"
        f"and(sender_id.eq.{with_user_id},receiver_id.eq.{current_user_id})"
    )

    # Jalankan query
    resp = (
        supabase_client
        .table("mschat")
        .select("chat_id, sender_id, receiver_id, message, attachment, created_at")
        .or_(or_filter)
        .order("created_at", desc=False)
        .execute()
    )

    # Cek data
    data = getattr(resp, "data", None)
    if data is None:
        return {"history": []}

    return {"history": data}


@router.websocket("/ws/chat/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: int, token: str):
    """
    Real-time chat endpoint via WebSocket.

    - token diambil dari query param: ws://.../ws/chat/{user_id}?token=...
    """
    current_user_id = await get_current_user_id_ws(token)
    if current_user_id != user_id:
        # token tidak valid atau tidak sesuai user_id
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            receiver_id = data.get("receiver_id")
            message_text = data.get("message")
            attachment_data = data.get("attachment")  # misal URL/base64

            # Prepare record untuk DB
            record = {
                "sender_id": user_id,
                "receiver_id": receiver_id,
                "message": message_text or "",
                "created_at": datetime.utcnow().isoformat()
            }

            # Jika ada attachment, upload ke Cloudinary
            if attachment_data:
                upload_res = cloudinary.uploader.upload(attachment_data)
                record["attachment"] = upload_res.get("secure_url")

            # Simpan ke Supabase
            res = supabase_client.table("mschat").insert(record).execute()
            saved = None
            if res and res.data:
                # Ambil data chat tercipta
                saved = res.data[0]

            # Kirim balik ke sender (ack)
            if saved:
                await manager.send_personal_message({**saved, "own": True}, user_id)
            
            # Kirim ke receiver jika online
            if saved and receiver_id in manager.active_connections:
                await manager.send_personal_message({**saved, "own": False}, receiver_id)

    except WebSocketDisconnect:
        manager.disconnect(user_id)

@router.get("/search-users")
async def search_users(
    q: str = Query(..., min_length=1),
    current_user_id: int = Query(...)
):
    try:
        # Ambil semua ID teman dari msfriend_list
        friends_1 = supabase_client.table("msfriend_list")\
            .select("user_id_2")\
            .eq("user_id_1", current_user_id).execute()

        friends_2 = supabase_client.table("msfriend_list")\
            .select("user_id_1")\
            .eq("user_id_2", current_user_id).execute()

        friend_ids = set()

        for f in friends_1.data:
            friend_ids.add(f['user_id_2'])
        for f in friends_2.data:
            friend_ids.add(f['user_id_1'])

        if not friend_ids:
            return {"data": []}

        # Query msuser yang termasuk friend_ids dan ILIKE nama
        # Supabase Python SDK tidak support `.in_()` dengan list langsung,
        # jadi kita bisa filter di Python setelah ambil username ILIKE

        response = supabase_client.table("msuser")\
            .select("user_id, username, profile_picture")\
            .ilike("username", f"%{q}%").execute()

        # Filter hasil supaya hanya friend_ids yang masuk
        result = [user for user in response.data if user["user_id"] in friend_ids]

        return {"data": result[:10]}  # limit 10

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
