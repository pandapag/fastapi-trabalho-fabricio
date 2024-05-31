from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
import redis.asyncio as redis
import json
import random
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')

async def get_redis_connection():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True
    )

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.client_names: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        name = random.choice(["João", "Gabriel", "Cleyton", "Lopes"])
        self.client_names[websocket] = name
        redis_conn = await get_redis_connection()
        await redis_conn.set(f"client:{id(websocket)}", name)
        return name

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        asyncio.create_task(self.remove_client_from_redis(websocket))

    async def remove_client_from_redis(self, websocket: WebSocket):
        redis_conn = await get_redis_connection()
        await redis_conn.delete(f"client:{id(websocket)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    async def get_client_name(self, websocket: WebSocket):
        redis_conn = await get_redis_connection()
        name = await redis_conn.get(f"client:{id(websocket)}")
        return name if name else "Unknown"

manager = ConnectionManager()

html = 'templates/index.html'

@app.get("/", response_class=FileResponse)
async def get():
    return FileResponse(html)

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    client_name = await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = f"{client_name} says: {data}"
            await save_message_to_redis(client_name, data)
            await manager.broadcast(message)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"{client_name} left the chat")

async def save_message_to_redis(client_name: str, message: str):
    redis_conn = await get_redis_connection()
    chat_message = {"client_name": client_name, "message": message}
    await redis_conn.rpush("chat_messages", json.dumps(chat_message))

@app.get("/history")
async def get_chat_history():
    redis_conn = await get_redis_connection()
    messages = await redis_conn.lrange("chat_messages", 0, -1)
    return [json.loads(message) for message in messages]