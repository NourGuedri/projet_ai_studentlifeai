"""Private storage of the meeting recordings.

The files live in settings.MEETINGS_AUDIO_ROOT, outside MEDIA_ROOT: the public /media/ route never serves them.
They are read only through GET /api/meetings/<id>/audio/, which checks that the user is the organizer or a
participant of the meeting.
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.functional import cached_property


@deconstructible(path="meetings.storage.PrivateAudioStorage")
class PrivateAudioStorage(FileSystemStorage):
    @cached_property
    def base_location(self):
        return settings.MEETINGS_AUDIO_ROOT

    @cached_property
    def location(self):
        return os.path.abspath(self.base_location)

    @cached_property
    def base_url(self):
        return None  # no public URL: storage.url() raises ValueError

    def _clear_cached_properties(self, setting, **kwargs):
        super()._clear_cached_properties(setting, **kwargs)
        if setting == "MEETINGS_AUDIO_ROOT":  # override_settings in the tests
            self.__dict__.pop("base_location", None)
            self.__dict__.pop("location", None)


audio_storage = PrivateAudioStorage()
