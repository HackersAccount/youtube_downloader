import asyncio
import websockets
import json


async def download_playlist():
    async with websockets.connect("ws://localhost:8000/ws") as websocket:
        # URL of the playlist to download
        playlist_url = "https://www.youtube.com/playlist?list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj"

        # Send the playlist URL to the server along with the message to start the download task
        await websocket.send(
            json.dumps(
                {"message": "start_playlist_download", "playlist_url": playlist_url}
            )
        )
        await websocket.send("start_playlist_download")

        while True:
            message = await websocket.recv()
            print(message)


asyncio.run(download_playlist())
