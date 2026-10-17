"""Development media server with HTTP Range support (lets browsers seek inside videos).
In production, serve /media/ with nginx or object storage instead."""
import mimetypes
import os
import re

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.utils._os import safe_join


def _chunks(handle, length, size=1 << 20):
    try:
        while length > 0:
            data = handle.read(min(size, length))
            if not data:
                break
            length -= len(data)
            yield data
    finally:
        handle.close()


def serve_media(request, path):
    try:
        full = safe_join(settings.MEDIA_ROOT, path)
    except Exception:
        raise Http404
    if not os.path.isfile(full):
        raise Http404
    total = os.path.getsize(full)
    content_type = mimetypes.guess_type(full)[0] or "application/octet-stream"

    match = re.match(r"^bytes=(\d*)-(\d*)$", request.headers.get("Range", ""))
    if match and (match.group(1) or match.group(2)):
        if match.group(1):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else total - 1
        else:
            start, end = max(total - int(match.group(2)), 0), total - 1
        end = min(end, total - 1)
        if start > end:
            return HttpResponse(status=416, headers={"Content-Range": f"bytes */{total}"})
        handle = open(full, "rb")
        handle.seek(start)
        response = StreamingHttpResponse(_chunks(handle, end - start + 1), status=206, content_type=content_type)
        response["Content-Range"] = f"bytes {start}-{end}/{total}"
        response["Content-Length"] = str(end - start + 1)
    else:
        response = FileResponse(open(full, "rb"), content_type=content_type)
        response["Content-Length"] = str(total)
    response["Accept-Ranges"] = "bytes"
    return response
