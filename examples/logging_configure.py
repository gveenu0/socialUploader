import asyncio
import yt_upload as yt
import datetime as dt


async def main():
    channel = yt.Channel(
        user_data_dir=r"../data",
        google_profile="Profile1",
        cookies_path=r"../cookies.json"
    )
    video = yt.Video(
        video_path="../data\\abc1.mp4",
        title="Funny video",
        made_for_kids=False,
        category=yt.category.PETS_ANIMALS,
        visibility=yt.visibility.PUBLIC,
        tags=["animals", "cats",  "funny"],
        schedule=dt.datetime.now() + dt.timedelta(days=1)
    )
    
    logging_config = {
        "filename": "yt_log.jsonl",
        "maxBytes": 10000,
        "backupCount": 3,
    }


    async with channel("Profile1", enable_logging=True, **logging_config) as upload:
        await upload.upload_video(video)


asyncio.run(main())
