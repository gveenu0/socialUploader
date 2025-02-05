import os
import json
import asyncio
import logging
import logging.handlers
import warnings
import traceback

from typing import OrderedDict, Optional
from playwright.async_api import async_playwright

from .loggers import logadapter, setup_logging
from .models import Cookies, Video
from .utils import to_abs_path, remove_indexddb_cache_files
from .exceptions import YTError
from .pages import  (
    YTStudioPage, 
    YTDetailsPage, 
    YTVisibilityPage, 
)
from .states import (
    YTStudioStateGroup,
    YTVisibilityStateGroup, 
    YTDetailsStateGroup
)


class Channel:
    studio_url = "https://studio.youtube.com/"
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

    def __init__(
        self,
        user_data_dir: str,
        google_profile: str,
        cookies_path: str,
    ) -> None:
        self.user_data_dir = to_abs_path(user_data_dir)
        self.profile_path = to_abs_path(os.path.join(self.user_data_dir, google_profile))
        self.cookies_path = to_abs_path(cookies_path)

        with open(self.cookies_path, encoding="utf-8") as f:
            self.yt_cookies = Cookies(cookies=json.loads(f.read()))

        self.profile = google_profile

    async def start(self):
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.firefox.launch_persistent_context(
            user_data_dir=os.path.join(self.user_data_dir, self.profile),
            channel="firefox",
            headless=self.headless,
            proxy=self.proxy,
            user_agent=self.user_agent,
            args=[
                "--no-sandbox",
                "--allow-profiles-outside-user-dir",
            ],
        )
        await self.context.add_cookies(self.yt_cookies.model_dump())
        
        self.logger.info("Start playwright", extra=logadapter(
            playwright_settings = (
                self.context._impl_obj._options 
                | {"executable_path": self.context._impl_obj._parent.executable_path, }
            ),
            youtube_channel=self.youtube_channel
        ))
    
        page = await self.context.new_page()
        studio_page = YTStudioPage(page)
        
        language = await studio_page.get_language()

        if not (self.change_language_to_eng or language == "en"):
            msg = (f"YouTube language is '{language}', "
                   "need to change YouTube language to English. "
                   "Use either set change_language_to_eng = True "
                   "or do it manually in YouTube settings.")
            raise YTError(msg)
        elif self.change_language_to_eng and not language == "en":
            await studio_page.change_language_to_eng()
        
        await page.close()

    async def stop(self):
        self.logger.info("Clear YouTube local cache", extra=logadapter(
            youtube_channel=self.youtube_channel
        ))
        remove_indexddb_cache_files(self.profile_path)

        await self.context.close()
        await self.playwright.stop()

    async def _update_cookies(self):
        cookies = await self.context.cookies(self.studio_url)
        self.logger.info("Update YouTube cookies", extra=logadapter(
            youtube_channel=self.youtube_channel
        ))
        self.yt_cookies.update_cookies(cookies)
        self.yt_cookies.save_cookies(self.cookies_path)
    
    async def upload_video(self, video: Video):
        page = await self.context.new_page()
        
        self.logger.info("Start upload video", extra=logadapter(
            youtube_channel=self.youtube_channel, 
            youtube_video_settigns=video.model_dump(),
        ))
        self.log_data = {
            "youtube_channel": self.youtube_channel,
            "video": {
                "path": video.video_path,
                "title": video.title
            }
        }

        await YTStudioStateGroup.start(YTStudioPage(page), video, self.log_data)
        await YTDetailsStateGroup.start(YTDetailsPage(page), video, self.log_data)
        await YTVisibilityStateGroup.start(YTVisibilityPage(page), video, self.log_data)
        await page.close()
    
    async def __upload_video_call(self, video):
        log_data = {
            "youtube_channel": self.youtube_channel,
            "video": {
                "path": video.video_path,
                "title": video.title
            }
        }

        try:
            await self.upload_video(video)
        except Exception as exc:
                exc_type = exc.__class__
                exc_val = exc.args[0]
                self.logger.error("%s: %s" % (exc_type.__name__, exc_val), 
                    extra=logadapter(
                        log_data,
                        error_type = exc_type.__name__,
                        error_message = exc_val
                ))
                print(traceback.format_exc())

    async def upload_videos(self, videos: list[Video]):
        tasks = [self.__upload_video_call(video) for video in videos]

        for task in asyncio.as_completed(tasks):
                await task

    # i hate fucking Google for this verification
    # thats why the decision is just as fucking fuck
    # mb later (never) i'll fix it
    # noqa
    async def verification(self):
        page = await self.context.new_page()
        studio_page = YTStudioPage(page)
        await studio_page.load_page()

        while input("Enter 'exit' after passing verification: ") != "exit":
            await page.wait_for_timeout(100)
        
        await page.close()


    def __call__(
        self,
        youtube_channel: str, 
        headless: bool = False, 
        proxy: Optional[OrderedDict[str, str]] = None,
        change_language_to_eng: bool = True,
        enable_logging: bool = True,
        **log_file_handler_kwargs
    ):
        self.youtube_channel = youtube_channel
        self.headless = headless
        self.proxy = proxy
        self.change_language_to_eng = change_language_to_eng

        if enable_logging:            
            warnings.filterwarnings("error")
            self.logger = setup_logging(**log_file_handler_kwargs)
        else:
            self.logger = logging.getLogger('null')
            self.logger.addHandler(logging.NullHandler())

        return self

    async def __aenter__(self):
        try:
            await self.start()
        except Exception as exc:
            exc_type = exc.__class__
            exc_val = exc.args[0]
            self.logger.error("%s: %s" % (exc_type.__name__, exc_val), 
                extra=logadapter(
                    youtube_channel=self.youtube_channel,
                    error_type = exc_type.__name__,
                    error_message = exc_val
            ))
            raise
            
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            await self._update_cookies()
            await self.stop()
            return None
        
        self.logger.error("%s: %s" % (exc_type.__name__, exc_val), 
            extra=logadapter(
                self.log_data,
                error_type = exc_type.__name__,
                error_message = exc_val
            ))
        
        await self.stop()
