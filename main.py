import os
from fastapi import FastAPI, WebSocket, HTTPException
from pytube import YouTube
from pytube.exceptions import PytubeError

app = FastAPI()


def make_alpha_numeric(string):
    return "".join(char for char in string if char.isalnum())


class YouTubeVideoDownloader:
    async def download_video(self, video_url: str, websocket: WebSocket):
        try:
            # Create a YouTube object with the provided video URL
            youtube = YouTube(video_url)

            # Get the highest resolution video stream
            stream = youtube.streams.get_highest_resolution()

            # Check if the stream is available
            if stream:
                # Send initial message to WebSocket client
                await websocket.send_text(f"Downloading video: {youtube.title}")

                # Create folder if not exists
                folder_name = make_alpha_numeric(youtube.title)
                os.makedirs(folder_name, exist_ok=True)

                # Start downloading the video
                stream.download(output_path=folder_name)

                # Send completion message to WebSocket client
                await websocket.send_text(f"Download completed: {youtube.title}")
            else:
                await websocket.send_text("No suitable stream found for this video.")

        except PytubeError as e:
            await websocket.send_text(f"Error downloading video: {str(e)}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            if data.startswith("download:"):
                video_url = data.split(":", 1)[1].strip()
                downloader = YouTubeVideoDownloader()
                await downloader.download_video(video_url, websocket)
    except Exception as e:
        await websocket.send_text(f"WebSocket connection error: {str(e)}")
        await websocket.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
