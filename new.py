import os
import re
import asyncio
import logging
from fastapi import FastAPI, HTTPException, status, Request, WebSocket, Depends
from fastapi.responses import JSONResponse
from pytube import Playlist
from pytube.exceptions import PytubeError
from typing import List

from main import make_alpha_numeric

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variable to store WebSocket clients
clients = []


class VideoDownloader:
    def __init__(self, folder_name: str):
        self.folder_name = folder_name

    async def download_video(self, video_url: str, websocket: WebSocket):
        try:
            playlist = Playlist(video_url)
            folder_name = self.folder_name

            for video in playlist.videos:
                video_path = os.path.join(
                    folder_name, self.make_alpha_numeric(video.title) + ".mp4"
                )
                if os.path.exists(video_path):
                    logger.info(
                        "Skipping download for %s (already exists)", video.title
                    )
                    await websocket.send_text(
                        f"Skipping download for {video.title} (already exists)"
                    )
                    continue

                logger.info("Downloading: %s", video.title)
                await websocket.send_text(f"Downloading: {video.title}")

                try:
                    stream = video.streams.get_highest_resolution()
                    if stream:
                        logger.info("Size: %s MB", stream.filesize // (1024**2))
                        await websocket.send_text(
                            f"Size: {stream.filesize // (1024**2)} MB"
                        )
                        await asyncio.to_thread(
                            stream.download,
                            output_path=folder_name,
                            filename=self.make_alpha_numeric(video.title),
                        )
                        logger.info("Downloaded: %s successfully!", video.title)
                        await websocket.send_text(
                            f"Downloaded: {video.title} successfully!"
                        )
                    else:
                        logger.warning("No suitable stream found for: %s", video.title)
                        await websocket.send_text(
                            f"No suitable stream found for: {video.title}"
                        )
                except PytubeError as e:
                    logger.error("Error downloading %s: %s", video.title, str(e))
                    await websocket.send_text(
                        f"Error downloading {video.title}: {str(e)}"
                    )

        except PytubeError as e:
            logger.error("Error processing playlist %s: %s", video_url, str(e))
            await websocket.send_text(
                f"Error processing playlist {video_url}: {str(e)}"
            )

    @staticmethod
    def make_alpha_numeric(string):
        return "".join(char for char in string if char.isalnum())


class WebSocketManager:
    def __init__(self):
        self.clients = []

    async def add_client(self, websocket: WebSocket):
        await websocket.accept()
        self.clients.append(websocket)

    async def remove_client(self, websocket: WebSocket):
        self.clients.remove(websocket)
        await websocket.close()

    async def send_message(self, message: str):
        for client in self.clients:
            await client.send_text(message)


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, ws_manager: WebSocketManager = Depends(WebSocketManager)
):
    await ws_manager.add_client(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received message from client: {data}")

            # Check if the received message indicates a playlist download should be started
            if data == "start_playlist_download":
                # Trigger the playlist download task
                await download_playlist_task(websocket)

                # Send a response to acknowledge that the download task has started
                await websocket.send_text("Playlist download task has started.")
            else:
                # Respond to the client with a message indicating that the server received the message
                await websocket.send_text(f"Server received message: {data}")
    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
        await ws_manager.remove_client(websocket)


async def download_playlist_task(websocket: WebSocket, playlist_url: str):
    try:
        # Placeholder implementation of playlist download logic
        playlist = Playlist(playlist_url)
        folder_name = make_alpha_numeric(playlist.title())
        await websocket.send_text(f"Starting playlist download: {playlist.title()}")

        for video in playlist.videos:
            video_path = os.path.join(
                folder_name, make_alpha_numeric(video.title) + ".mp4"
            )
            if os.path.exists(video_path):
                logger.info("Skipping download for %s (already exists)", video.title)
                await websocket.send_text(
                    f"Skipping download for {video.title} (already exists)"
                )
                continue

            logger.info("Downloading: %s", video.title)
            await websocket.send_text(f"Downloading: {video.title}")
            try:
                stream = video.streams.get_highest_resolution()
                if stream:
                    logger.info("Size: %s MB", stream.filesize // (1024**2))
                    await websocket.send_text(
                        f"Size: {stream.filesize // (1024**2)} MB"
                    )
                    await asyncio.to_thread(
                        stream.download,
                        output_path=folder_name,
                        filename=make_alpha_numeric(video.title),
                    )
                    logger.info("Downloaded: %s successfully!", video.title)
                    await websocket.send_text(
                        f"Downloaded: {video.title} successfully!"
                    )
                else:
                    logger.warning("No suitable stream found for: %s", video.title)
                    await websocket.send_text(
                        f"No suitable stream found for: {video.title}"
                    )
            except PytubeError as e:
                logger.error("Error downloading %s: %s", video.title, str(e))
                await websocket.send_text(f"Error downloading {video.title}: {str(e)}")

        # Inform the client that the playlist download has completed
        await websocket.send_text("Playlist download completed successfully.")
    except Exception as e:
        logger.error(f"Error during playlist download task: {str(e)}")
        await websocket.send_text(f"Error during playlist download task: {str(e)}")


@app.post("/download-playlist/")
async def download_playlist(
    request: Request,
    video_downloader: VideoDownloader = Depends(VideoDownloader),
    ws_manager: WebSocketManager = Depends(WebSocketManager),
):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload."
        )

    if not data or "urls" not in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No URLs provided."
        )

    urls = data["urls"]

    # Remove empty or malformed URLs
    valid_urls = [
        url.strip()
        for url in urls
        if url.strip() and re.match(r"^https?://", url.strip())
    ]

    if not valid_urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No valid URLs provided."
        )

    try:
        # Execute download tasks in parallel using ThreadPoolExecutor
        for url in valid_urls:
            await video_downloader.download_video(url, ws_manager)
    except HTTPException as e:
        raise e
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        )

    return {"message": "Download completed successfully."}


@app.exception_handler(405)
async def method_not_allowed_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code, content={"message": "Method Not Allowed"}
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"message": "Not Found"})


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"message": "Forbidden"})


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code, content={"message": "Unauthorized"}
    )
